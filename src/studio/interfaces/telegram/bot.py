"""Bot Studio (async): gerbang keamanan di depan pemrosesan update yang tahan crash.

Urutan untuk setiap update:
1. hanya chat pribadi; grup/channel diabaikan;
2. identitas = `from_user.id` (bukan username) → harus owner di allowlist; selain itu ditolak
   dan dicatat di audit log (dibatasi supaya log tidak dibanjiri). Update orang asing tidak
   pernah disimpan;
3. sisanya diserahkan ke `UpdateProcessor` (ADR-0013): simpan → klaim → aksi bisnis + commit
   dalam satu transaksi → kirim balasan dari outbox persisten.

Error tidak terduga tidak pernah diteruskan ke user (tanpa traceback / detail internal).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from functools import partial

from studio.interfaces.telegram import render, texts
from studio.interfaces.telegram.core import CoreRunner, is_busy
from studio.interfaces.telegram.engine import CHANNEL
from studio.interfaces.telegram.processor import UpdateProcessor, error_reply
from studio.interfaces.telegram.transport import Transport, TransportError
from studio.interfaces.telegram.types import (
    AnswerCallback,
    EditKeyboard,
    EditMessage,
    Inbound,
    Screen,
    SendMessage,
)
from studio.modules.audit import AuditLog
from studio.modules.controller import StudioController
from studio.shared.logging import get_logger

__all__ = ["CoreRunner", "StudioBot", "deliver_action", "is_busy", "send_screen"]

_log = get_logger("studio.telegram")


class StudioBot:
    UNAUTHORIZED_THROTTLE_S = 600.0

    def __init__(
        self,
        *,
        controller: StudioController,
        processor: UpdateProcessor,
        audit: AuditLog,
        transport: Transport,
        core: CoreRunner,
        on_activity: Callable[[], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._controller = controller
        self._processor = processor
        self._audit = audit
        self._transport = transport
        self._core = core
        self._on_activity = on_activity
        self._monotonic = monotonic
        self._last_rejection: dict[int, float] = {}

    @property
    def processor(self) -> UpdateProcessor:
        return self._processor

    async def handle(self, inbound: Inbound) -> None:
        if inbound.chat_type != "private" or inbound.user_id is None:
            await self._reject_non_private(inbound)
            return
        actor = self._controller.actor_for(CHANNEL, inbound.user_id)
        if not self._controller.is_owner(actor):
            await self._reject_stranger(inbound)
            return
        try:
            await self._processor.submit(inbound, actor)
        except sqlite3.Error as exc:
            # Gagal menyimpan update (DB sibuk lama): belum ada yang tercatat, jadi minta
            # owner mengulang. Kalau update sudah tersimpan, pemulihan yang melanjutkan.
            _log.warning("telegram.receive_failed", update_id=inbound.update_id, busy=is_busy(exc))
            for action in error_reply(inbound, texts.DB_BUSY).actions:
                try:
                    await deliver_action(self._transport, action)
                except TransportError:
                    break
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

    # --- pengiriman ------------------------------------------------------------------

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
