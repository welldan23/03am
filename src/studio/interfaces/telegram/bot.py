"""Bot Studio (async): gerbang keamanan + jembatan ke inti sinkron.

Urutan untuk setiap update:
1. hanya chat pribadi; grup/channel diabaikan;
2. identitas = `from_user.id` (bukan username) → harus owner di allowlist; selain itu ditolak
   dan dicatat di audit log (dibatasi supaya log tidak dibanjiri);
3. update yang sudah pernah diproses (dikirim ulang Telegram) diabaikan;
4. `ConversationEngine` dijalankan di thread inti (satu thread untuk semua akses database);
5. hasilnya dikirim lewat `Transport` (di luar transaksi apa pun).

Error tidak terduga tidak pernah diteruskan ke user (tanpa traceback / detail internal).
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, TypeVar

from studio.interfaces.telegram import render, texts
from studio.interfaces.telegram.engine import CHANNEL, ConversationEngine
from studio.interfaces.telegram.transport import Transport, TransportError
from studio.interfaces.telegram.types import (
    AnswerCallback,
    EditKeyboard,
    EditMessage,
    Inbound,
    Reply,
    Screen,
    SendMessage,
)
from studio.modules.audit import AuditLog
from studio.modules.controller import StudioController, UpdateLog
from studio.shared.logging import get_logger

T = TypeVar("T")

_log = get_logger("studio.telegram")


def is_busy(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).lower() for marker in ("locked", "busy")
    )


class CoreRunner:
    """Satu thread untuk semua pemanggilan inti sinkron.

    Koneksi SQLite & penghitung transaksi `Database` tidak thread-safe, jadi semua akses dari
    proses bot diserialkan di sini. Worker job memakai koneksinya sendiri di thread lain.
    "database is locked" (penulis lain memegang lock lebih lama dari busy_timeout) dicoba
    ulang beberapa kali dengan jeda.
    """

    def __init__(self, *, busy_retries: int = 3, busy_delay_s: float = 0.2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studio-core")
        self._busy_retries = busy_retries
        self._busy_delay = busy_delay_s

    def _with_retry(self, fn: Callable[..., T], *args: Any) -> T:
        for attempt in range(self._busy_retries + 1):
            try:
                return fn(*args)
            except sqlite3.OperationalError as exc:
                if not is_busy(exc) or attempt == self._busy_retries:
                    raise
                time.sleep(self._busy_delay * (2**attempt))
        raise AssertionError("unreachable")  # pragma: no cover

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(self._with_retry, fn, *args))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


class StudioBot:
    UNAUTHORIZED_THROTTLE_S = 600.0

    def __init__(
        self,
        *,
        controller: StudioController,
        engine: ConversationEngine,
        updates: UpdateLog,
        audit: AuditLog,
        transport: Transport,
        core: CoreRunner,
        on_activity: Callable[[], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._updates = updates
        self._audit = audit
        self._transport = transport
        self._core = core
        self._on_activity = on_activity
        self._monotonic = monotonic
        self._last_rejection: dict[int, float] = {}

    async def handle(self, inbound: Inbound) -> None:
        if inbound.chat_type != "private" or inbound.user_id is None:
            await self._reject_non_private(inbound)
            return
        actor = self._controller.actor_for(CHANNEL, inbound.user_id)
        if not self._controller.is_owner(actor):
            await self._reject_stranger(inbound)
            return
        try:
            fresh = await self._core.run(self._updates.register, CHANNEL, inbound.update_id)
        except sqlite3.Error:
            _log.warning("telegram.dedupe_failed", update_id=inbound.update_id)
            await self._deliver(self._error_reply(inbound, texts.DB_BUSY))
            return
        if not fresh:
            _log.info("telegram.duplicate_update", update_id=inbound.update_id)
            if inbound.callback_id:
                await self._safe_answer(inbound.callback_id, "")
            return
        try:
            reply = await self._core.run(self._engine.handle, inbound, actor)
        except sqlite3.Error as exc:
            _log.warning("telegram.db_error", update_id=inbound.update_id, busy=is_busy(exc))
            reply = self._error_reply(inbound, texts.DB_BUSY)
        except Exception:
            _log.exception("telegram.handler_failed", update_id=inbound.update_id)
            reply = self._error_reply(inbound, texts.INTERNAL_ERROR)
        await self._deliver(reply)
        if self._on_activity is not None:
            self._on_activity()

    # --- penolakan ---------------------------------------------------------------

    async def _reject_non_private(self, inbound: Inbound) -> None:
        # Grup/channel: tidak membalas pesan (bot privat), hanya menghentikan spinner tombol.
        if inbound.callback_id:
            await self._safe_answer(inbound.callback_id, texts.NOT_PRIVATE)

    async def _reject_stranger(self, inbound: Inbound) -> None:
        user_id = inbound.user_id or 0
        now = self._monotonic()
        first = now - self._last_rejection.get(user_id, -1e12) > self.UNAUTHORIZED_THROTTLE_S
        if first:
            if len(self._last_rejection) > 10_000:  # batasi memori kalau dibanjiri akun asing
                self._last_rejection.clear()
            self._last_rejection[user_id] = now
            actor = self._controller.actor_for(CHANNEL, user_id)
            try:
                await self._core.run(
                    partial(
                        self._audit.record,
                        actor=actor,
                        action="telegram.unauthorized",
                        entity_type="telegram_user",
                        entity_id=str(user_id),
                        data={
                            "kind": "callback" if inbound.callback_id else "message",
                            "chat_type": inbound.chat_type,
                        },
                    )
                )
            except sqlite3.Error:
                _log.warning("telegram.audit_failed", user_id=user_id)
            _log.warning("telegram.unauthorized", user_id=user_id)
        if inbound.callback_id:
            await self._safe_answer(inbound.callback_id, texts.NOT_OWNER)
        elif first:
            await self._safe_send(inbound.chat_id, Screen(texts.NOT_OWNER))

    def _error_reply(self, inbound: Inbound, message: str) -> Reply:
        reply = Reply()
        if inbound.callback_id:
            reply.answer(inbound.callback_id, message, alert=True)
        else:
            reply.send(inbound.chat_id, Screen(message, render.rows(render.menu_row())))
        return reply

    # --- pengiriman ------------------------------------------------------------------

    async def _deliver(self, reply: Reply) -> None:
        for action in reply.actions:
            try:
                await deliver_action(self._transport, action)
            except TransportError as exc:
                _log.warning("telegram.send_failed", error=str(exc), retryable=exc.retryable)

    async def _safe_answer(self, callback_id: str, text: str) -> None:
        try:
            await self._transport.answer(callback_id, text, alert=False)
        except TransportError:
            return

    async def _safe_send(self, chat_id: int, screen: Screen) -> None:
        try:
            await self._transport.send(chat_id, screen)
        except TransportError:
            return


async def deliver_action(transport: Transport, action: object) -> None:
    """Kirim satu aksi keluar, memecah teks yang melebihi 4096 karakter."""
    if isinstance(action, AnswerCallback):
        await transport.answer(action.callback_id, action.text, alert=action.alert)
    elif isinstance(action, EditKeyboard):
        await transport.edit_keyboard(action.chat_id, action.message_id, action.keyboard)
    elif isinstance(action, SendMessage):
        await send_screen(transport, action.chat_id, action.screen)
    elif isinstance(action, EditMessage):
        chunks = render.split_text(action.screen.text)
        first_keyboard = action.screen.keyboard if len(chunks) == 1 else ()
        await transport.edit(action.chat_id, action.message_id, Screen(chunks[0], first_keyboard))
        if len(chunks) > 1:
            await send_screen(
                transport, action.chat_id, Screen("\n".join(chunks[1:]), action.screen.keyboard)
            )


async def send_screen(transport: Transport, chat_id: int, screen: Screen) -> int:
    chunks = render.split_text(screen.text)
    message_id = 0
    for index, chunk in enumerate(chunks):
        keyboard = screen.keyboard if index == len(chunks) - 1 else ()
        message_id = await transport.send(chat_id, Screen(chunk, keyboard))
    return message_id
