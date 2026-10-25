"""Port pengiriman pesan + adapter aiogram dengan penanganan error Telegram.

- `TelegramRetryAfter` (rate limit): tunggu `retry_after` kalau singkat, selain itu
  dikembalikan sebagai `TransportError(retry_after=…)` supaya outbox menjadwalkan ulang.
- Timeout / jaringan putus / error server: dicoba ulang dengan backoff, lalu menyerah
  sebagai error yang bisa diulang.
- Diblokir user / chat tidak ada: error permanen.
- "message is not modified": diabaikan; pesan yang tidak bisa diedit → dikirim baru.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

from studio.interfaces.telegram.types import Keyboard, Screen

T = TypeVar("T")


class TransportError(Exception):
    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class Transport(Protocol):
    async def send(self, chat_id: int, screen: Screen) -> int: ...

    async def edit(self, chat_id: int, message_id: int, screen: Screen) -> None: ...

    async def edit_keyboard(self, chat_id: int, message_id: int, keyboard: Keyboard) -> None: ...

    async def answer(self, callback_id: str, text: str, *, alert: bool) -> None: ...


def _markup(keyboard: Keyboard) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if not keyboard:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=b.text, callback_data=b.data) for b in row]
            for row in keyboard
        ]
    )


class AiogramTransport:
    def __init__(
        self,
        bot: Any,
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
        max_inline_wait_seconds: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._bot = bot
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._max_inline_wait = max_inline_wait_seconds
        self._sleep = sleep

    async def _call(self, factory: Callable[[], Awaitable[T]]) -> T | None:
        from aiogram.exceptions import (
            TelegramBadRequest,
            TelegramForbiddenError,
            TelegramNetworkError,
            TelegramNotFound,
            TelegramRetryAfter,
            TelegramServerError,
            TelegramUnauthorizedError,
        )

        for attempt in range(1, self._max_attempts + 1):
            last = attempt == self._max_attempts
            try:
                return await factory()
            except TelegramRetryAfter as exc:
                if exc.retry_after > self._max_inline_wait or last:
                    raise TransportError(
                        "rate limit Telegram", retryable=True, retry_after=float(exc.retry_after)
                    ) from exc
                await self._sleep(float(exc.retry_after))
            except (TelegramNetworkError, TelegramServerError, TimeoutError) as exc:
                if last:
                    raise TransportError(
                        f"Telegram tidak bisa dihubungi ({type(exc).__name__})", retryable=True
                    ) from exc
                await self._sleep(self._backoff * (2 ** (attempt - 1)))
            except (TelegramForbiddenError, TelegramNotFound, TelegramUnauthorizedError) as exc:
                raise TransportError(
                    f"Telegram menolak ({type(exc).__name__})", retryable=False
                ) from exc
            except TelegramBadRequest as exc:
                if "message is not modified" in exc.message:
                    return None
                raise TransportError(f"permintaan ditolak: {exc.message}", retryable=False) from exc
        return None  # pragma: no cover - loop selalu return/raise

    async def send(self, chat_id: int, screen: Screen) -> int:
        message = await self._call(
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=screen.text,
                reply_markup=_markup(screen.keyboard),
            )
        )
        return int(message.message_id) if message is not None else 0

    async def edit(self, chat_id: int, message_id: int, screen: Screen) -> None:
        try:
            await self._call(
                lambda: self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=screen.text,
                    reply_markup=_markup(screen.keyboard),
                )
            )
        except TransportError as exc:
            # Pesan terlalu lama / sudah dihapus / bukan teks → kirim pesan baru saja.
            if exc.retryable:
                raise
            await self.send(chat_id, screen)

    async def edit_keyboard(self, chat_id: int, message_id: int, keyboard: Keyboard) -> None:
        try:
            await self._call(
                lambda: self._bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup=_markup(keyboard)
                )
            )
        except TransportError as exc:
            if exc.retryable:
                raise

    async def answer(self, callback_id: str, text: str, *, alert: bool) -> None:
        try:
            await self._call(
                lambda: self._bot.answer_callback_query(
                    callback_query_id=callback_id, text=text or None, show_alert=alert
                )
            )
        except TransportError:
            # Callback yang sudah terlalu lama tidak bisa dijawab; tidak mengubah apa pun.
            return
