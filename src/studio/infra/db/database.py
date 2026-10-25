"""Koneksi SQLite dengan WAL dan transaksi reentrant.

Transaksi terluar memakai `BEGIN IMMEDIATE` sehingga penulis lain menunggu (busy_timeout)
alih-alih membaca data setengah jadi. Transaksi bersarang memakai SAVEPOINT.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

Params = Sequence[Any] | dict[str, Any]


class Database:
    def __init__(self, path: Path | str, *, busy_timeout_ms: int = 5000) -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._depth = 0
        self._conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")

    @property
    def path(self) -> str:
        return self._path

    @property
    def in_transaction(self) -> bool:
        return self._depth > 0

    def execute(self, sql: str, params: Params = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def query_one(self, sql: str, params: Params = ()) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(sql, params).fetchone()
        return row

    def query_all(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params).fetchall())

    def scalar(self, sql: str, params: Params = ()) -> Any:
        row = self._conn.execute(sql, params).fetchone()
        return None if row is None else row[0]

    def pragma(self, name: str) -> Any:
        return self.scalar(f"PRAGMA {name}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._depth == 0:
            self._conn.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                yield
            except BaseException:
                self._depth = 0
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth = 0
                self._conn.execute("COMMIT")
            return

        savepoint = f"sp_{self._depth}"
        self._conn.execute(f"SAVEPOINT {savepoint}")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            self._conn.execute(f"ROLLBACK TO {savepoint}")
            self._conn.execute(f"RELEASE {savepoint}")
            raise
        else:
            self._depth -= 1
            self._conn.execute(f"RELEASE {savepoint}")

    def close(self) -> None:
        self._conn.close()
