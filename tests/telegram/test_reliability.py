"""Reliability: error Telegram (rate limit, timeout, jaringan, diblokir), batas 4096 karakter,
error internal tanpa traceback, SQLite busy, konversi update aiogram, worker berhenti rapi."""

import asyncio
import sqlite3
from typing import Any

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage as SendMessageMethod
from aiogram.types import CallbackQuery, Chat, Message, User

from studio.interfaces.telegram import texts
from studio.interfaces.telegram.adapter import inbound_from_callback, inbound_from_message
from studio.interfaces.telegram.bot import CoreRunner, send_screen
from studio.interfaces.telegram.transport import AiogramTransport, TransportError
from studio.interfaces.telegram.types import Button, Screen
from tests.telegram.fakes import OWNER_TG, Harness

METHOD = SendMessageMethod(chat_id=1, text="x")


class FakeBot:
    """Pengganti aiogram.Bot: melempar exception aiogram asli sesuai skenario."""

    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _do(self, name: str, **kwargs: Any) -> Any:
        self.calls.append((name, kwargs))
        if self.failures:
            raise self.failures.pop(0)
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def send_message(self, **kwargs: Any) -> Any:
        return await self._do("send_message", **kwargs)

    async def edit_message_text(self, **kwargs: Any) -> Any:
        return await self._do("edit_message_text", **kwargs)

    async def edit_message_reply_markup(self, **kwargs: Any) -> Any:
        return await self._do("edit_message_reply_markup", **kwargs)

    async def answer_callback_query(self, **kwargs: Any) -> Any:
        return await self._do("answer_callback_query", **kwargs)


def _transport(failures: list[Exception]) -> tuple[AiogramTransport, FakeBot, list[float]]:
    bot = FakeBot(failures)
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    return AiogramTransport(bot, sleep=sleep), bot, slept


def test_short_retry_after_is_waited_out() -> None:
    transport, bot, slept = _transport([TelegramRetryAfter(METHOD, "flood", 2)])
    assert asyncio.run(transport.send(1, Screen("halo"))) == 2
    assert slept == [2.0] and len(bot.calls) == 2


def test_long_retry_after_is_returned_to_caller() -> None:
    transport, _, slept = _transport([TelegramRetryAfter(METHOD, "flood", 60)])
    with pytest.raises(TransportError) as info:
        asyncio.run(transport.send(1, Screen("halo")))
    assert info.value.retryable and info.value.retry_after == 60 and slept == []


def test_network_errors_and_timeouts_are_retried_with_backoff() -> None:
    transport, bot, slept = _transport([TelegramNetworkError(METHOD, "putus"), TimeoutError()])
    assert asyncio.run(transport.send(1, Screen("halo")))
    assert slept == [1.0, 2.0] and len(bot.calls) == 3
    transport, _, _ = _transport([TelegramNetworkError(METHOD, "putus")] * 3)
    with pytest.raises(TransportError) as info:
        asyncio.run(transport.send(1, Screen("halo")))
    assert info.value.retryable


def test_blocked_user_is_permanent() -> None:
    transport, bot, _ = _transport([TelegramForbiddenError(METHOD, "bot was blocked by the user")])
    with pytest.raises(TransportError) as info:
        asyncio.run(transport.send(1, Screen("halo")))
    assert not info.value.retryable and len(bot.calls) == 1


def test_unmodified_edit_is_ignored_and_missing_message_is_resent() -> None:
    transport, bot, _ = _transport(
        [TelegramBadRequest(METHOD, "Bad Request: message is not modified")]
    )
    asyncio.run(transport.edit(1, 5, Screen("sama")))
    assert [c[0] for c in bot.calls] == ["edit_message_text"]
    transport, bot, _ = _transport(
        [TelegramBadRequest(METHOD, "Bad Request: message to edit not found")]
    )
    asyncio.run(transport.edit(1, 5, Screen("baru", ((Button("ok", "m:main"),),))))
    assert [c[0] for c in bot.calls] == ["edit_message_text", "send_message"]
    assert bot.calls[1][1]["reply_markup"].inline_keyboard[0][0].callback_data == "m:main"


def test_stale_callback_answer_does_not_raise() -> None:
    transport, _, _ = _transport([TelegramBadRequest(METHOD, "query is too old")])
    asyncio.run(transport.answer("cb", "x", alert=False))


def test_long_screens_are_split_and_keyboard_goes_last() -> None:
    transport, bot, _ = _transport([])
    text = "\n".join("baris " + "x" * 100 for _ in range(120))
    asyncio.run(send_screen(transport, 1, Screen(text, ((Button("ok", "m:main"),),))))
    sends = [c[1] for c in bot.calls]
    assert len(sends) >= 3 and all(len(s["text"]) <= 4096 for s in sends)
    assert (
        all(s["reply_markup"] is None for s in sends[:-1]) and sends[-1]["reply_markup"] is not None
    )


def test_internal_errors_never_leak_details(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("SELECT * FROM secret_table; Traceback /home/user/03am")

    monkeypatch.setattr(harness.engine, "handle", boom)
    harness.say("/start")
    text = harness.transport.last().text
    assert text == texts.INTERNAL_ERROR
    assert "SELECT" not in text and "Traceback" not in text


def test_sqlite_busy_gets_friendly_message_and_retry(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    original = harness.engine.handle

    def locked(*args: Any) -> Any:
        calls["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(harness.engine, "handle", locked)
    harness.say("/start")
    assert harness.transport.last().text == texts.DB_BUSY
    # CoreRunner mencoba ulang error "locked" sebelum menyerah.
    runner = CoreRunner(busy_retries=2, busy_delay_s=0)
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    try:
        assert asyncio.run(runner.run(flaky)) == "ok" and attempts["n"] == 3
    finally:
        runner.shutdown()
    monkeypatch.setattr(harness.engine, "handle", original)


def test_transport_failure_while_replying_does_not_crash(harness: Harness) -> None:
    harness.transport.fail_next.append(TransportError("putus", retryable=True))
    harness.say("/start")  # gagal kirim → dicatat, tidak melempar
    harness.say("/menu")
    assert "Menu" in harness.transport.last().text or "03:AM" in harness.transport.last().text


def test_aiogram_updates_are_converted_by_numeric_id() -> None:
    user = User(id=OWNER_TG, is_bot=False, first_name="Owner", username="ganti_nama_bebas")
    chat = Chat(id=OWNER_TG, type="private")
    message = Message(message_id=7, date=0, chat=chat, from_user=user, text="halo")
    inbound = inbound_from_message(message, 42)
    assert (inbound.update_id, inbound.user_id, inbound.chat_type, inbound.text) == (
        42,
        OWNER_TG,
        "private",
        "halo",
    )
    query = CallbackQuery(
        id="q1", from_user=user, chat_instance="x", data="m:main", message=message
    )
    cb = inbound_from_callback(query, 43)
    assert cb.callback_data == "m:main" and cb.message_id == 7 and cb.is_callback
    orphan = CallbackQuery(id="q2", from_user=user, chat_instance="x", data="m:main")
    assert inbound_from_callback(orphan, 44).chat_type == "unknown"  # ditolak sebagai non-private
    group = Message(
        message_id=8, date=0, chat=Chat(id=-5, type="group"), from_user=user, text="hai"
    )
    assert inbound_from_message(group, 45).chat_type == "group"


def test_router_wires_message_and_callback_handlers(harness: Harness) -> None:
    from studio.interfaces.telegram.adapter import build_router

    router = build_router(harness.bot)
    assert len(router.message.handlers) == 1 and len(router.callback_query.handlers) == 1


def test_worker_thread_stops_gracefully(tg_app: Any) -> None:
    from studio.interfaces.telegram.runner import WorkerThread

    events: list[str] = []
    worker = WorkerThread(tg_app.settings, on_job=lambda: events.append("job"), idle_seconds=0.05)
    worker.start()
    worker.stop(timeout=5)
    assert not worker._thread.is_alive()


def test_cli_bot_check_reports_missing_config(tg_app: Any) -> None:
    import io

    from studio.interfaces.cli.main import main

    out = io.StringIO()
    assert main(["bot", "check"], app=tg_app, out=out) == 1
    assert "STUDIO_TELEGRAM_BOT_TOKEN belum diisi" in out.getvalue()
    assert "1001" in out.getvalue()


def test_callbacks_never_reach_the_text_intent_parser(tg_app: Any) -> None:
    """Tombol diproses deterministik oleh router callback; parser teks (calon Hermes di
    Fase 5) tidak pernah melihat callback, apalagi keputusan approval."""
    from studio.interfaces.telegram.engine import ConversationEngine
    from studio.interfaces.telegram.intents import Intent, IntentName

    seen: list[str] = []

    class SpyParser:
        def parse(self, text: str) -> Intent:
            seen.append(text)
            return Intent(IntentName.MENU)

    h = Harness(tg_app)
    h.engine = ConversationEngine(tg_app.controller, tg_app.conversations, parser=SpyParser())
    h.bot._engine = h.engine
    try:
        h.say("halo")
        h.press("Buat Dokumenter")
        h.press("Quick Files")
        h.press("Sejarah")
        h.press("Ya, lanjutkan")
        assert seen == ["halo"]
        assert tg_app.episodes.list_episodes()
    finally:
        h.close()


def test_only_one_poller_per_data_dir(tmp_path: Any) -> None:
    from studio.interfaces.telegram.runner import PollerLock
    from studio.shared.errors import ConfigError

    first = PollerLock(tmp_path / "telegram-poller.lock")
    second = PollerLock(tmp_path / "telegram-poller.lock")
    first.acquire()
    try:
        with pytest.raises(ConfigError, match="bot lain sudah berjalan"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_bot_stays_responsive_while_worker_runs_a_long_job(make_app: Any) -> None:
    """Worker (thread + koneksi sendiri) sedang menunggu provider; bot tetap menjawab cepat
    karena tidak ada lock SQLite yang ditahan selama I/O (eksekusi dua fase)."""
    import threading
    import time

    from studio.providers.llm.mock import MockLLMProvider
    from studio.shared.actors import Actor

    release = threading.Event()
    entered = threading.Event()

    class SlowProvider(MockLLMProvider):
        def complete(self, request: Any, ticket: Any) -> Any:
            entered.set()
            release.wait(10)
            return super().complete(request, ticket)

    owner = Actor.owner(f"telegram:{OWNER_TG}")
    bot_app = make_app(owner_ids=f"telegram:{OWNER_TG}")
    bot_app.budget.activate_period(owner)
    worker_app = make_app(
        owner_ids=f"telegram:{OWNER_TG}", llm_provider_factory=lambda t: SlowProvider(t)
    )
    h = Harness(bot_app)
    try:
        h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
        h.press("Ya, lanjutkan")
        worker = threading.Thread(target=lambda: worker_app.worker("slow").run_once())
        worker.start()
        assert entered.wait(5)
        started = time.monotonic()
        h.say("/status")
        h.say("/budget")
        h.say("Buat dokumenter tentang Voynich, format 40 detik, kategori misteri")
        h.press("Ya, lanjutkan")  # menulis ke DB juga lancar
        elapsed = time.monotonic() - started
        assert elapsed < 2.0, elapsed
        assert "Budget" in "\n".join(h.transport.texts())
        assert len(bot_app.episodes.list_episodes()) == 2
    finally:
        release.set()
        worker.join(10)
        h.close()
