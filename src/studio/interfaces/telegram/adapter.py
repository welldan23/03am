"""Adaptor aiogram → `Inbound`. Satu-satunya tempat yang tahu bentuk objek aiogram."""

from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.types import CallbackQuery, Message, Update

from studio.interfaces.telegram.bot import StudioBot
from studio.interfaces.telegram.types import Inbound


def inbound_from_message(message: Message, update_id: int) -> Inbound:
    return Inbound(
        update_id=update_id,
        user_id=message.from_user.id if message.from_user else None,
        chat_id=message.chat.id,
        chat_type=str(message.chat.type),
        text=message.text,
    )


def inbound_from_callback(query: CallbackQuery, update_id: int) -> Inbound:
    message: Any = query.message
    chat = getattr(message, "chat", None)
    return Inbound(
        update_id=update_id,
        user_id=query.from_user.id,
        # Tanpa pesan (inline mode / pesan terlalu lama) → bukan chat pribadi yang dikenal.
        chat_id=chat.id if chat is not None else query.from_user.id,
        chat_type=str(chat.type) if chat is not None else "unknown",
        callback_id=query.id,
        callback_data=query.data,
        message_id=getattr(message, "message_id", None),
    )


def build_router(bot: StudioBot) -> Router:
    router = Router(name="studio-03am")

    @router.message()
    async def on_message(message: Message, event_update: Update) -> None:
        await bot.handle(inbound_from_message(message, event_update.update_id))

    @router.callback_query()
    async def on_callback(query: CallbackQuery, event_update: Update) -> None:
        await bot.handle(inbound_from_callback(query, event_update.update_id))

    return router
