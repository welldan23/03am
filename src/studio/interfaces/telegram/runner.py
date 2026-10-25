"""Menjalankan bot dengan long polling (development lokal; siap dipindah ke VPS).

Satu proses berisi:
- event loop aiogram (long polling);
- thread inti (`CoreRunner`) untuk semua akses database dari bot;
- dispatcher notifikasi (task asyncio);
- opsional: worker job di thread sendiri dengan koneksi database sendiri.

Shutdown (SIGINT/SIGTERM): polling berhenti → dispatcher & worker diberi sinyal berhenti →
job yang sedang jalan dibiarkan selesai (atau lease-nya habis & diambil ulang nanti) →
koneksi database & sesi HTTP ditutup. Untuk webhook di VPS, cukup ganti sumber update;
`StudioBot.handle` tidak berubah.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO

from studio.bootstrap import App, build_app
from studio.interfaces.telegram.bot import CoreRunner, StudioBot
from studio.interfaces.telegram.engine import ConversationEngine
from studio.interfaces.telegram.notifier import NotificationDispatcher
from studio.interfaces.telegram.transport import AiogramTransport
from studio.shared.config import Settings
from studio.shared.errors import ConfigError
from studio.shared.logging import configure_logging, get_logger

_log = get_logger("studio.telegram.runner")


def check_bot_settings(settings: Settings) -> list[str]:
    """Masalah konfigurasi yang membuat bot tidak boleh start (tanpa menyentuh jaringan)."""
    problems = []
    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else ""
    if not token:
        problems.append("STUDIO_TELEGRAM_BOT_TOKEN belum diisi (di environment atau .env)")
    elif ":" not in token:
        problems.append("format STUDIO_TELEGRAM_BOT_TOKEN tidak valid (harus <angka>:<rahasia>)")
    if not settings.telegram_owner_ids:
        problems.append(
            "STUDIO_OWNER_IDS belum berisi user ID Telegram, contoh: telegram:123456789"
        )
    return problems


class PollerLock:
    """Pastikan hanya SATU proses yang long polling token bot ini (ADR-0005).

    Dua poller untuk token yang sama membuat Telegram membalas 409 Conflict dan update bisa
    terbagi acak. Kunci file di folder data dilepas otomatis oleh OS kalau proses mati.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: IO[str] | None = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise ConfigError(
                f"bot lain sudah berjalan memakai data yang sama ({self._path}); hentikan dulu"
            ) from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


class WorkerThread:
    """Worker job di thread terpisah (koneksi DB sendiri). Berhenti dengan rapi."""

    def __init__(
        self,
        settings: Settings,
        *,
        on_job: Callable[[], None],
        idle_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._on_job = on_job
        self._idle = idle_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="studio-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def _run(self) -> None:
        app = build_app(self._settings)
        worker = app.worker()
        try:
            while not self._stop.is_set():
                try:
                    job = worker.run_once()
                except Exception:
                    _log.exception("worker.cycle_failed")
                    job = None
                if job is not None:
                    self._on_job()
                else:
                    self._stop.wait(self._idle)
        finally:
            app.close()


async def run_polling(settings: Settings) -> None:
    problems = check_bot_settings(settings)
    if problems:
        raise ConfigError("bot Telegram tidak bisa start: " + "; ".join(problems))
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from studio.interfaces.telegram.adapter import build_router

    if settings.telegram_bot_token is None:  # pragma: no cover - dijaga check_bot_settings
        raise ConfigError("token bot belum diisi")
    token = settings.telegram_bot_token.get_secret_value()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    configure_logging(settings.log_level, extra_secrets=frozenset({token}))

    lock = PollerLock(settings.data_dir / "telegram-poller.lock")
    lock.acquire()
    core = CoreRunner()
    app: App = await core.run(build_app, settings)
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    transport = AiogramTransport(bot)
    engine = ConversationEngine(app.controller, app.conversations)
    notifier = NotificationDispatcher(
        controller=app.controller,
        engine=engine,
        outbox=app.outbox,
        transport=transport,
        core=core,
        clock=app.clock,
        actions=app.actions,
        updates=app.updates,
        idle_seconds=settings.notify_idle_seconds,
    )
    studio_bot = StudioBot(
        controller=app.controller,
        engine=engine,
        updates=app.updates,
        audit=app.audit,
        transport=transport,
        core=core,
        on_activity=notifier.wake,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(studio_bot))

    stop = asyncio.Event()
    notifier_task = asyncio.create_task(notifier.run(stop), name="studio-notifier")
    worker = (
        WorkerThread(settings, on_job=notifier.wake_threadsafe)
        if settings.telegram_run_worker
        else None
    )
    if worker is not None:
        worker.start()
    _log.info("telegram.started", worker=worker is not None)
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=["message", "callback_query"],
            handle_signals=True,
            close_bot_session=True,
        )
    finally:
        stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(notifier_task, timeout=10)
        if worker is not None:
            await asyncio.to_thread(worker.stop)
        await core.run(app.close)
        core.shutdown()
        lock.release()
        _log.info("telegram.stopped")


def main(settings: Settings | None = None) -> int:
    settings = settings or Settings()
    try:
        asyncio.run(run_polling(settings))
    except ConfigError as exc:
        print(f"Gagal: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0
