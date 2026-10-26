"""Thread inti: semua akses database dari proses bot diserialkan di satu thread."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, TypeVar

T = TypeVar("T")


def is_busy(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).lower() for marker in ("locked", "busy")
    )


class CoreRunner:
    """Satu thread untuk semua pemanggilan inti sinkron.

    Koneksi SQLite & penghitung transaksi `Database` tidak thread-safe, jadi semua akses dari
    proses bot diserialkan di sini. Worker job memakai koneksinya sendiri di thread lain.
    "database is locked" (penulis lain memegang lock lebih lama dari busy_timeout) dicoba
    ulang beberapa kali dengan jeda.
    """

    def __init__(self, *, busy_retries: int = 3, busy_delay_s: float = 0.2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studio-core")
        self._busy_retries = busy_retries
        self._busy_delay = busy_delay_s

    def _with_retry(self, fn: Callable[..., T], *args: Any) -> T:
        for attempt in range(self._busy_retries + 1):
            try:
                return fn(*args)
            except sqlite3.OperationalError as exc:
                if not is_busy(exc) or attempt == self._busy_retries:
                    raise
                time.sleep(self._busy_delay * (2**attempt))
        raise AssertionError("unreachable")  # pragma: no cover

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(self._with_retry, fn, *args))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)
