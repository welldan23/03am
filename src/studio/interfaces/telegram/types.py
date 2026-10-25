"""Tipe pesan masuk/keluar yang tidak bergantung aiogram (supaya inti bot bisa dites offline)."""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_MESSAGE_CHARS = 4096
MAX_CALLBACK_BYTES = 64


@dataclass(frozen=True)
class Button:
    text: str
    data: str


Keyboard = tuple[tuple[Button, ...], ...]


@dataclass(frozen=True)
class Inbound:
    update_id: int
    user_id: int | None
    chat_id: int
    chat_type: str
    text: str | None = None
    callback_id: str | None = None
    callback_data: str | None = None
    message_id: int | None = None  # pesan yang tombolnya ditekan

    @property
    def is_callback(self) -> bool:
        return self.callback_id is not None


@dataclass(frozen=True)
class Screen:
    text: str
    keyboard: Keyboard = ()


@dataclass(frozen=True)
class SendMessage:
    chat_id: int
    screen: Screen


@dataclass(frozen=True)
class EditMessage:
    chat_id: int
    message_id: int
    screen: Screen


@dataclass(frozen=True)
class EditKeyboard:
    """Ganti/hapus tombol pesan lama (misalnya kartu yang tombolnya sudah tidak berlaku)."""

    chat_id: int
    message_id: int
    keyboard: Keyboard = ()


@dataclass(frozen=True)
class AnswerCallback:
    callback_id: str
    text: str = ""
    alert: bool = False


Outbound = SendMessage | EditMessage | EditKeyboard | AnswerCallback


@dataclass
class Reply:
    """Kumpulan aksi keluar untuk satu update."""

    actions: list[Outbound] = field(default_factory=list)

    def send(self, chat_id: int, screen: Screen) -> None:
        self.actions.append(SendMessage(chat_id, screen))

    def edit(self, chat_id: int, message_id: int, screen: Screen) -> None:
        self.actions.append(EditMessage(chat_id, message_id, screen))

    def clear_keyboard(self, chat_id: int, message_id: int) -> None:
        self.actions.append(EditKeyboard(chat_id, message_id))

    def answer(self, callback_id: str, text: str = "", *, alert: bool = False) -> None:
        self.actions.append(AnswerCallback(callback_id, text, alert))
