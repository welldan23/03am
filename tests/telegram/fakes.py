"""Fake Telegram transport + helper percakapan untuk test offline (tanpa jaringan)."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from studio.bootstrap import App
from studio.interfaces.telegram.bot import CoreRunner, StudioBot
from studio.interfaces.telegram.engine import ConversationEngine
from studio.interfaces.telegram.notifier import NotificationDispatcher
from studio.interfaces.telegram.transport import TransportError
from studio.interfaces.telegram.types import Button, Inbound, Keyboard, Screen

OWNER_TG = 1001
STRANGER_TG = 6666


@dataclass
class Sent:
    chat_id: int
    message_id: int
    text: str
    keyboard: Keyboard

    def buttons(self) -> list[Button]:
        return [b for row in self.keyboard for b in row]

    def button(self, label: str) -> Button:
        matches = [b for b in self.buttons() if label in b.text]
        assert matches, f"tombol {label!r} tidak ada di {[b.text for b in self.buttons()]}"
        return matches[0]


@dataclass
class FakeTransport:
    """Mencatat semua pesan. `fail_next` menyuntikkan error transport berikutnya."""

    messages: dict[int, Sent] = field(default_factory=dict)
    log: list[tuple[str, Any]] = field(default_factory=list)
    answers: list[tuple[str, str, bool]] = field(default_factory=list)
    fail_next: list[TransportError] = field(default_factory=list)
    _ids: Any = field(default_factory=lambda: itertools.count(1))

    def _maybe_fail(self) -> None:
        if self.fail_next:
            raise self.fail_next.pop(0)

    async def send(self, chat_id: int, screen: Screen) -> int:
        self._maybe_fail()
        message_id = next(self._ids)
        self.messages[message_id] = Sent(chat_id, message_id, screen.text, screen.keyboard)
        self.log.append(("send", message_id))
        return message_id

    async def edit(self, chat_id: int, message_id: int, screen: Screen) -> None:
        self._maybe_fail()
        self.messages[message_id] = Sent(chat_id, message_id, screen.text, screen.keyboard)
        self.log.append(("edit", message_id))

    async def edit_keyboard(self, chat_id: int, message_id: int, keyboard: Keyboard) -> None:
        self._maybe_fail()
        old = self.messages[message_id]
        self.messages[message_id] = Sent(chat_id, message_id, old.text, keyboard)
        self.log.append(("edit_keyboard", message_id))

    async def answer(self, callback_id: str, text: str, *, alert: bool) -> None:
        self.answers.append((callback_id, text, alert))

    # --- helper -------------------------------------------------------------------

    def last(self, chat_id: int | None = None) -> Sent:
        items = [m for m in self.messages.values() if chat_id is None or m.chat_id == chat_id]
        assert items, "belum ada pesan"
        # pesan terakhir yang dikirim ATAU diedit
        last_id = next(
            mid
            for kind, mid in reversed(self.log)
            if chat_id is None or self.messages[mid].chat_id == chat_id
        )
        return self.messages[last_id]

    def texts(self, chat_id: int | None = None) -> list[str]:
        return [m.text for m in self.messages.values() if chat_id is None or m.chat_id == chat_id]


class Harness:
    """Satu percakapan Telegram palsu di atas App sungguhan (SQLite + mock provider)."""

    def __init__(
        self,
        app: App,
        *,
        monotonic: Callable[[], float] | None = None,
        first_update_id: int = 1,
    ) -> None:
        self.app = app
        self.transport = FakeTransport()
        self.core = CoreRunner(busy_retries=0)
        self.engine = ConversationEngine(app.controller, app.conversations)
        self.notifier = NotificationDispatcher(
            controller=app.controller,
            engine=self.engine,
            outbox=app.outbox,
            transport=self.transport,
            core=self.core,
            clock=app.clock,
            actions=app.actions,
            updates=app.updates,
        )
        kwargs: dict[str, Any] = {}
        if monotonic is not None:
            kwargs["monotonic"] = monotonic
        self.bot = StudioBot(
            controller=app.controller,
            engine=self.engine,
            updates=app.updates,
            audit=app.audit,
            transport=self.transport,
            core=self.core,
            **kwargs,
        )
        self._update_ids = itertools.count(first_update_id)
        self._callback_ids = itertools.count(1)

    def close(self) -> None:
        self.core.shutdown()

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def say(self, text: str, *, user_id: int = OWNER_TG, chat_type: str = "private") -> Inbound:
        inbound = Inbound(
            update_id=next(self._update_ids),
            user_id=user_id,
            chat_id=user_id if chat_type == "private" else -100,
            chat_type=chat_type,
            text=text,
        )
        self.run(self.bot.handle(inbound))
        return inbound

    def tap(
        self,
        target: Button | str,
        message: Sent | None = None,
        *,
        user_id: int = OWNER_TG,
        chat_type: str = "private",
        update_id: int | None = None,
    ) -> Inbound:
        data = target.data if isinstance(target, Button) else target
        message = message or self.transport.last(user_id if chat_type == "private" else None)
        inbound = Inbound(
            update_id=update_id if update_id is not None else next(self._update_ids),
            user_id=user_id,
            chat_id=message.chat_id if chat_type == "private" else -100,
            chat_type=chat_type,
            callback_id=f"cb{next(self._callback_ids)}",
            callback_data=data,
            message_id=message.message_id,
        )
        self.run(self.bot.handle(inbound))
        return inbound

    def press(self, label: str, message: Sent | None = None, **kwargs: Any) -> Inbound:
        message = message or self.transport.last()
        return self.tap(message.button(label), message, **kwargs)

    def work(self) -> int:
        return self.app.worker("tg-test-worker").run_until_idle()

    def notify(self) -> int:
        return self.run(self.notifier.dispatch_once())

    def work_and_notify(self) -> None:
        for _ in range(10):
            processed = self.work()
            sent = self.notify()
            if not processed and not sent:
                return


# --- skenario umum ---------------------------------------------------------------


def create_episode(
    h: Harness, text: str = "Buat dokumenter tentang Krakatau, format 90 detik"
) -> str:
    """Buat episode lewat chat sampai kartu G0 terkirim. Mengembalikan ID episode."""
    h.say(text)
    if "Pilih format" in h.transport.last().text:
        h.press("The Archives")
    if "Pilih kategori" in h.transport.last().text:
        h.press("Sejarah")
    h.press("Ya, lanjutkan")
    h.work_and_notify()
    episodes = h.app.episodes.list_episodes()
    return episodes[-1].id


def g0_card(h: Harness) -> Sent:
    return next(
        m for m in reversed(list(h.transport.messages.values())) if "G0 · Pilih topik" in m.text
    )


def g1_card(h: Harness) -> Sent:
    return next(
        m
        for m in reversed(list(h.transport.messages.values()))
        if "G1 · Persetujuan editorial" in m.text
    )


def to_editorial(h: Harness, choice: int = 1) -> str:
    episode_id = create_episode(h)
    h.press(f"✅ {choice}", g0_card(h))
    h.work_and_notify()
    return episode_id
