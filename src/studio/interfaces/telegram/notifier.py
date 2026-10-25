"""Dispatcher outbox notifikasi → Telegram (ADR-0012).

- Baris outbox dibuat trigger DB di transaksi kejadiannya; di sini hanya dibaca & dikirim.
- Pengiriman di luar transaksi. Setiap penerima yang sudah menerima dicatat (`delivered_to`),
  jadi retry tidak mengirim ulang ke penerima yang sama.
- Tidak polling agresif: bangun saat ada aktivitas (aksi di bot / job selesai di worker
  yang sama) atau saat notifikasi tertunda jatuh tempo; selain itu cek setiap
  `idle_seconds`.
- Setelah restart, notifikasi yang belum terkirim (termasuk klaim yang lease-nya habis)
  diambil lagi.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from functools import partial

from studio.interfaces.telegram.bot import CoreRunner, send_screen
from studio.interfaces.telegram.engine import CHANNEL, ConversationEngine
from studio.interfaces.telegram.transport import Transport, TransportError
from studio.modules.controller import ActionCodes, StudioController, UpdateLog
from studio.modules.notifications import Notification, Outbox
from studio.shared.clock import Clock
from studio.shared.logging import get_logger

_log = get_logger("studio.telegram.notifier")


class NotificationDispatcher:
    def __init__(
        self,
        *,
        controller: StudioController,
        engine: ConversationEngine,
        outbox: Outbox,
        transport: Transport,
        core: CoreRunner,
        clock: Clock,
        actions: ActionCodes | None = None,
        updates: UpdateLog | None = None,
        consumer: str = "telegram-notifier",
        idle_seconds: float = 10.0,
        batch_size: int = 20,
        lease_seconds: int = 120,
    ) -> None:
        self._controller = controller
        self._engine = engine
        self._outbox = outbox
        self._transport = transport
        self._core = core
        self._clock = clock
        self._actions = actions
        self._updates = updates
        self._consumer = consumer
        self._idle = idle_seconds
        self._batch = batch_size
        self._lease = lease_seconds
        self._event: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_prune: datetime | None = None

    # --- bangunkan ---------------------------------------------------------------

    def wake(self) -> None:
        """Dipanggil dari event loop (misalnya setelah owner menekan tombol)."""
        if self._event is not None:
            self._event.set()

    def wake_threadsafe(self) -> None:
        """Dipanggil dari thread lain (worker job di proses yang sama)."""
        if self._loop is not None and self._event is not None:
            self._loop.call_soon_threadsafe(self._event.set)

    # --- loop --------------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        self._loop = asyncio.get_running_loop()
        self._event = asyncio.Event()
        while not stop.is_set():
            try:
                await self.dispatch_once()
                await self._maybe_prune()
            except Exception:
                _log.exception("notifier.cycle_failed")
            timeout = await self._sleep_seconds()
            waiter = asyncio.ensure_future(self._event.wait())
            stopper = asyncio.ensure_future(stop.wait())
            await asyncio.wait(
                {waiter, stopper}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            for task in (waiter, stopper):
                task.cancel()
            self._event.clear()

    async def _sleep_seconds(self) -> float:
        due = await self._core.run(self._outbox.next_due_at)
        if due is None:
            return self._idle
        seconds = (due - self._clock.now()).total_seconds()
        return min(self._idle, max(0.5, seconds))

    async def dispatch_once(self) -> int:
        """Kirim semua notifikasi yang jatuh tempo. Mengembalikan jumlah yang diproses."""
        claimed = await self._core.run(
            partial(
                self._outbox.claim, self._consumer, limit=self._batch, lease_seconds=self._lease
            )
        )
        for notification in claimed:
            await self._deliver(notification)
        return len(claimed)

    async def _deliver(self, notification: Notification) -> None:
        for recipient in self._controller.notification_recipients():
            if recipient in notification.delivered_to:
                continue
            actor = self._controller.actor_for(CHANNEL, recipient)
            try:
                screen = await self._core.run(self._engine.render_notification, notification, actor)
            except Exception as exc:
                _log.exception("notifier.render_failed", notification_id=notification.id)
                await self._fail(notification, f"render: {type(exc).__name__}")
                return
            if screen is not None:
                try:
                    await send_screen(self._transport, int(recipient), screen)
                except TransportError as exc:
                    _log.warning(
                        "notifier.send_failed",
                        notification_id=notification.id,
                        retryable=exc.retryable,
                        retry_after=exc.retry_after,
                    )
                    await self._fail(
                        notification,
                        str(exc),
                        retry_after_s=exc.retry_after,
                        permanent=not exc.retryable,
                    )
                    return
            await self._core.run(
                self._outbox.mark_delivered, notification.id, self._consumer, recipient
            )
        await self._core.run(self._outbox.complete, notification.id, self._consumer)

    async def _fail(
        self,
        notification: Notification,
        error: str,
        *,
        retry_after_s: float | None = None,
        permanent: bool = False,
    ) -> None:
        await self._core.run(
            partial(
                self._outbox.fail,
                notification.id,
                self._consumer,
                error,
                retry_after_s=retry_after_s,
                permanent=permanent,
            )
        )

    async def _maybe_prune(self) -> None:
        """Bersihkan data antarmuka yang sudah lama (bukan jejak audit) sekali sehari."""
        now = self._clock.now()
        if self._last_prune is not None and now - self._last_prune < timedelta(days=1):
            return
        self._last_prune = now
        if self._actions is not None:
            await self._core.run(partial(self._actions.prune, older_than=timedelta(days=7)))
        if self._updates is not None:
            await self._core.run(partial(self._updates.prune, older_than=timedelta(days=30)))
