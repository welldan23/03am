"""Format `callback_data` (maksimum 64 byte, ditegakkan saat encode).

Dua jenis:
- navigasi baca-saja (`m:`, `l:`, `v:`, `n:`, `ap:`): hanya ID publik (ULID episode/approval),
  tidak pernah token. Tetap diproses hanya untuk owner.
- aksi (`a:<kode>`): kode acak sekali pakai; isinya ada di server (`ui_action_codes`).

Payload callback tidak pernah dianggap bukti otorisasi.
"""

from __future__ import annotations

from dataclasses import dataclass

from studio.interfaces.telegram.types import MAX_CALLBACK_BYTES, Button
from studio.shared.errors import StudioError


class CallbackError(StudioError):
    pass


@dataclass(frozen=True)
class Callback:
    kind: str
    parts: tuple[str, ...]

    def part(self, index: int, default: str = "") -> str:
        return self.parts[index] if index < len(self.parts) else default

    def number(self, index: int, default: int = 0) -> int:
        value = self.part(index)
        return int(value) if value.isdigit() else default


def encode(kind: str, *parts: str | int) -> str:
    values = [kind, *(str(p) for p in parts)]
    if any(":" in v for v in values[1:]):
        raise CallbackError("bagian callback tidak boleh mengandung ':'")
    data = ":".join(values)
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError(f"callback_data {len(data.encode())} byte > {MAX_CALLBACK_BYTES}")
    return data


def decode(data: str) -> Callback:
    if not data or len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError("callback_data tidak valid")
    kind, *parts = data.split(":")
    return Callback(kind, tuple(parts))


def button(text: str, kind: str, *parts: str | int) -> Button:
    return Button(text, encode(kind, *parts))


def action(text: str, code: str) -> Button:
    return Button(text, encode("a", code))
