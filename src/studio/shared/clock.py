"""Sumber waktu. Semua kode memakai `Clock`, bukan `datetime.now()` langsung."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class Clock(Protocol):
    def now(self) -> datetime:
        """Waktu sekarang dalam UTC (timezone-aware)."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Jam yang bisa dimajukan manual, untuk test dan simulasi."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock butuh datetime dengan timezone")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def to_iso(value: datetime) -> str:
    """Format UTC yang bisa diurutkan sebagai string."""
    if value.tzinfo is None:
        raise ValueError("datetime tanpa timezone tidak boleh disimpan")
    return value.astimezone(UTC).strftime(_ISO_FORMAT)


def from_iso(value: str) -> datetime:
    return datetime.strptime(value, _ISO_FORMAT).replace(tzinfo=UTC)
