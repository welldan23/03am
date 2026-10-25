"""JSON kanonik + SHA-256 untuk versi konten dan subjek approval."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


def _default(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Decimal | date | datetime):
        return str(value)
    raise TypeError(f"tipe {type(value).__name__} tidak bisa diserialisasi")


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(value: object) -> str:
    return sha256_hex(canonical_json(value))
