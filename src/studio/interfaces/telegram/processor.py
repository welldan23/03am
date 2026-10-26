"""Pemrosesan update Telegram yang tahan crash (ADR-0013).

Alur satu update (setelah lolos cek chat pribadi + allowlist di `StudioBot`):

1. **receive** (transaksi singkat): isi update disimpan di `ui_inbox` dan langsung diklaim
   (lease + fencing token). Update yang sama datang lagi → tidak diproses dua kali.
2. **commit** (SATU transaksi): cek lease masih milik kita → `ConversationEngine.handle`
   (semua aksi bisnis: kode tombol, keputusan approval, job, state percakapan) → status
   `committed` + balasan ke `ui_reply_outbox`. Crash/error sebelum commit = rollback total,
   update diproses ulang nanti. Setelah commit, aksi bisnis tidak pernah dijalankan ulang.
3. **flush** (di luar transaksi): balasan dikirim berurutan, satu baris = satu panggilan
   Bot API, dicatat `sent` satu per satu. Gagal sementara → dijadwal ulang.
4. **recover** (saat start + berkala): update yang tertinggal di `received/processing`
   (lease habis) diproses ulang; balasan yang tertunda dikirim ulang.

Semantik: efek bisnis *exactly-once* (dijamin transaksi + fencing + kode sekali pakai);
pengiriman Telegram *at-least-once*. Bot API tidak punya idempotency key untuk
`sendMessage`, jadi crash tepat setelah Telegram menerima pesan tapi sebelum `sent` tercatat
membuat pesan itu terkirim lagi saat pemulihan. Edit pesan & jawaban callback aman diulang.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from functools import partial
from typing import Any

from studio.infra.db import Database
from studio.interfaces.telegram import render, texts
from studio.interfaces.telegram.core import CoreRunner, is_busy
from studio.interfaces.telegram.engine import CHANNEL, ConversationEngine
from studio.interfaces.telegram.transport import Transport, TransportError
from studio.interfaces.telegram.types import (
    AnswerCallback,
    Button,
    EditKeyboard,
    EditMessage,
    Inbound,
    Keyboard,
    Reply,
    Screen,
    SendMessage,
)
from studio.modules.controller import (
    InboxItem,
    InboxStatus,
    ReplyOutbox,
    ReplyStatus,
    StudioController,
    UpdateInbox,
)
from studio.shared.actors import Actor
from studio.shared.clock import Clock
from studio.shared.logging import get_logger

_log = get_logger("studio.telegram.updates")

Fault = Callable[[str], None]

# Titik fault injection (dipakai test crash recovery; di produksi tidak melakukan apa pun).
AFTER_RECEIVE = "after_receive"
BEFORE_COMMIT = "before_commit"
AFTER_COMMIT = "after_commit"
BEFORE_SEND = "before_send"
AFTER_SEND = "after_send"


def _no_fault(point: str) -> None:
    return None


# --- serialisasi ---------------------------------------------------------------------


def inbound_to_payload(inbound: Inbound) -> dict[str, Any]:
    return asdict(inbound)


def inbound_from_payload(payload: dict[str, Any]) -> Inbound:
    return Inbound(**payload)


def _keyboard_to_json(keyboard: Keyboard) -> list[list[dict[str, str]]]:
    return [[{"text": b.text, "data": b.data} for b in row] for row in keyboard]


def _keyboard_from_json(data: list[list[dict[str, str]]]) -> Keyboard:
    return tuple(tuple(Button(b["text"], b["data"]) for b in row) for row in data)


def reply_rows(reply: Reply) -> list[tuple[str, dict[str, Any]]]:
    """Ubah balasan engine menjadi baris outbox; satu baris = satu panggilan Bot API."""
    rows: list[tuple[str, dict[str, Any]]] = []

    def sends(chat_id: int, text: str, keyboard: Keyboard) -> None:
        chunks = render.split_text(text)
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            rows.append(
                (
                    "send",
                    {
                        "chat_id": chat_id,
                        "text": chunk,
                        "keyboard": _keyboard_to_json(keyboard if last else ()),
                    },
                )
            )

    for action in reply.actions:
        if isinstance(action, AnswerCallback):
            rows.append(
                (
                    "answer",
                    {"callback_id": action.callback_id, "text": action.text, "alert": action.alert},
                )
            )
        elif isinstance(action, EditKeyboard):
            rows.append(
                (
                    "edit_keyboard",
                    {
                        "chat_id": action.chat_id,
                        "message_id": action.message_id,
                        "keyboard": _keyboard_to_json(action.keyboard),
                    },
                )
            )
        elif isinstance(action, SendMessage):
            sends(action.chat_id, action.screen.text, action.screen.keyboard)
        elif isinstance(action, EditMessage):
            chunks = render.split_text(action.screen.text)
            rows.append(
                (
                    "edit",
                    {
                        "chat_id": action.chat_id,
                        "message_id": action.message_id,
                        "text": chunks[0],
                        "keyboard": _keyboard_to_json(
                            action.screen.keyboard if len(chunks) == 1 else ()
                        ),
                    },
                )
            )
            if len(chunks) > 1:
                sends(action.chat_id, "\n".join(chunks[1:]), action.screen.keyboard)
    return rows


async def perform(transport: Transport, kind: str, payload: dict[str, Any]) -> int | None:
    """Jalankan satu baris outbox. Mengembalikan message_id untuk `send`."""
    if kind == "send":
        screen = Screen(payload["text"], _keyboard_from_json(payload["keyboard"]))
        return await transport.send(int(payload["chat_id"]), screen)
    if kind == "edit":
        screen = Screen(payload["text"], _keyboard_from_json(payload["keyboard"]))
        await transport.edit(int(payload["chat_id"]), int(payload["message_id"]), screen)
        return None
    if kind == "edit_keyboard":
        await transport.edit_keyboard(
            int(payload["chat_id"]),
            int(payload["message_id"]),
            _keyboard_from_json(payload["keyboard"]),
        )
        return None
    if kind == "answer":
        await transport.answer(payload["callback_id"], payload["text"], alert=payload["alert"])
        return None
    raise ValueError(f"jenis balasan tidak dikenal: {kind}")


def error_reply(inbound: Inbound, message: str) -> Reply:
    reply = Reply()
    if inbound.callback_id:
        reply.answer(inbound.callback_id, message, alert=True)
    else:
        reply.send(inbound.chat_id, Screen(message, render.rows(render.menu_row())))
    return reply


# --- pemroses --------------------------------------------------------------------------


class UpdateProcessor:
    def __init__(
        self,
        *,
        db: Database,
        clock: Clock,
        controller: StudioController,
        engine: ConversationEngine,
        inbox: UpdateInbox,
        replies: ReplyOutbox,
        transport: Transport,
        core: CoreRunner,
        owner: str,
        fault: Fault = _no_fault,
        idle_seconds: float = 10.0,
    ) -> None:
        self._db = db
        self._clock = clock
        self._controller = controller
        self._engine = engine
        self._inbox = inbox
        self._replies = replies
        self._transport = transport
        self._core = core
        self.owner = owner
        self._fault = fault
        self._idle = idle_seconds
        self._event: asyncio.Event | None = None

    # --- jalur utama ---------------------------------------------------------------

    async def submit(self, inbound: Inbound, actor: Actor) -> None:
        receipt = await self._core.run(
            partial(
                self._inbox.receive,
                CHANNEL,
                inbound.update_id,
                chat_id=str(inbound.chat_id),
                user_id=str(inbound.user_id) if inbound.user_id is not None else None,
                payload=inbound_to_payload(inbound),
                owner=self.owner,
            )
        )
        if receipt.claimed:
            await self._process(receipt.item, inbound, actor)
            return
        status = receipt.item.status
        _log.info("telegram.duplicate_update", update_id=inbound.update_id, status=status.value)
        if status is InboxStatus.COMMITTED:
            # Sudah di-commit tapi balasannya mungkin belum terkirim: kirim, jangan proses ulang.
            await self.flush(CHANNEL, inbound.update_id)
        # Duplikat callback TIDAK dijawab: callback_id-nya sama dengan aslinya, dan jawaban
        # kedua akan merebut slot jawaban (pop-up) milik pemrosesan asli.

    async def _process(self, item: InboxItem, inbound: Inbound, actor: Actor) -> None:
        token = item.lease_token
        self._fault(AFTER_RECEIVE)
        if item.attempts > self._inbox.max_attempts:
            await self._give_up(inbound, token, "jatah percobaan habis", busy=False)
            return
        try:
            committed = await self._core.run(self._commit, inbound, actor, token)
        except Exception as exc:  # error tak terduga / SQLite busy: tidak ada yang di-commit
            busy = is_busy(exc)
            _log.warning(
                "telegram.update_attempt_failed",
                update_id=inbound.update_id,
                attempt=item.attempts,
                busy=busy,
                error=type(exc).__name__,
            )
            if item.attempts >= self._inbox.max_attempts:
                await self._give_up(inbound, token, f"{type(exc).__name__}: {exc}", busy=busy)
            else:
                await self._release(inbound, token, f"{type(exc).__name__}: {exc}")
            return
        if not committed:
            _log.warning("telegram.update_lease_lost", update_id=inbound.update_id)
            return
        self._fault(AFTER_COMMIT)
        await self.flush(CHANNEL, inbound.update_id)

    def _commit(self, inbound: Inbound, actor: Actor, token: int) -> bool:
        """Aksi bisnis + status `committed` + balasan dalam SATU transaksi (thread inti)."""
        with self._db.transaction():
            if not self._inbox.owns(CHANNEL, inbound.update_id, self.owner, token):
                return False
            reply = self._engine.handle(inbound, actor)
            self._fault(BEFORE_COMMIT)
            self._inbox.commit(CHANNEL, inbound.update_id, self.owner, token, reply_rows(reply))
        return True

    async def _release(self, inbound: Inbound, token: int, error: str) -> None:
        try:
            await self._core.run(
                self._inbox.release, CHANNEL, inbound.update_id, self.owner, token, error
            )
        except Exception:
            # Lease tetap habis sendiri; pemulihan akan mengambilnya.
            _log.warning("telegram.update_release_failed", update_id=inbound.update_id)
        self.wake()

    async def _give_up(self, inbound: Inbound, token: int, error: str, *, busy: bool) -> None:
        message = texts.DB_BUSY if busy else texts.INTERNAL_ERROR
        try:
            await self._core.run(
                partial(
                    self._inbox.give_up,
                    CHANNEL,
                    inbound.update_id,
                    self.owner,
                    token,
                    error[:500],
                    reply_rows(error_reply(inbound, message)),
                )
            )
        except Exception:
            _log.exception("telegram.update_give_up_failed", update_id=inbound.update_id)
            return
        _log.error("telegram.update_failed", update_id=inbound.update_id)
        await self.flush(CHANNEL, inbound.update_id)

    # --- pengiriman -----------------------------------------------------------------

    async def flush(self, channel: str, update_id: int) -> None:
        rows = await self._core.run(self._replies.claim, channel, update_id, self.owner)
        for row in rows:
            self._fault(BEFORE_SEND)
            try:
                message_id = await perform(self._transport, row.kind, row.payload)
            except TransportError as exc:
                status = await self._core.run(
                    partial(
                        self._replies.fail,
                        row.id,
                        self.owner,
                        str(exc),
                        retry_after_s=exc.retry_after,
                        permanent=not exc.retryable,
                    )
                )
                _log.warning(
                    "telegram.reply_failed",
                    update_id=update_id,
                    seq=row.seq,
                    retryable=exc.retryable,
                    dead=status is ReplyStatus.DEAD,
                )
                if status is ReplyStatus.PENDING:
                    self.wake()
                    return  # balasan berikutnya menunggu supaya urutannya terjaga
                continue
            self._fault(AFTER_SEND)
            await self._core.run(self._replies.mark_sent, row.id, self.owner, message_id)
        await self._core.run(self._inbox.mark_delivered, channel, update_id)

    # --- pemulihan ------------------------------------------------------------------

    async def recover(self) -> int:
        """Proses ulang update yang tertinggal + kirim balasan tertunda. Aman diulang."""
        handled = 0
        items = await self._core.run(partial(self._inbox.claim_due, self.owner, limit=20))
        for item in items:
            inbound = inbound_from_payload(item.payload)
            actor = (
                self._controller.actor_for(CHANNEL, inbound.user_id)
                if inbound.user_id is not None
                else None
            )
            # Keamanan dicek ulang saat pemulihan (allowlist bisa berubah sejak update diterima).
            if (
                actor is None
                or inbound.chat_type != "private"
                or not self._controller.is_owner(actor)
            ):
                await self._core.run(
                    partial(
                        self._inbox.give_up,
                        CHANNEL,
                        item.update_id,
                        self.owner,
                        item.lease_token,
                        "tidak lagi berhak",
                        [],
                    )
                )
                continue
            _log.info("telegram.update_recovered", update_id=item.update_id, attempt=item.attempts)
            await self._process(item, inbound, actor)
            handled += 1
        for channel, update_id in await self._core.run(
            partial(self._replies.due_updates, limit=50)
        ):
            await self.flush(channel, update_id)
            handled += 1
        # Crash setelah balasan terakhir tercatat terkirim tapi sebelum `delivered` disimpan.
        handled += await self._core.run(self._inbox.settle_delivered)
        return handled

    def wake(self) -> None:
        if self._event is not None:
            self._event.set()

    async def run(self, stop: asyncio.Event) -> None:
        """Loop pemulihan: langsung jalan saat start (restart recovery), lalu saat ada yang
        jatuh tempo atau paling lambat setiap `idle_seconds`."""
        self._event = asyncio.Event()
        while not stop.is_set():
            try:
                await self.recover()
            except Exception:
                _log.exception("telegram.recovery_failed")
            due = await self._core.run(self._inbox.next_due_at)
            timeout = self._idle
            if due is not None:
                timeout = min(self._idle, max(0.5, (due - self._clock.now()).total_seconds()))
            waiter = asyncio.ensure_future(self._event.wait())
            stopper = asyncio.ensure_future(stop.wait())
            await asyncio.wait(
                {waiter, stopper}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            for task in (waiter, stopper):
                task.cancel()
            self._event.clear()
