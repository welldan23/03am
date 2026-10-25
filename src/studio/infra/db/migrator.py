"""Migrasi SQL bernomor (`NNNN_nama.sql`) yang dibundel di package.

Checksum disimpan saat migrasi diterapkan. Kalau file yang sudah diterapkan berubah,
migrator menolak jalan: perubahan skema harus lewat file migrasi baru.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from importlib import resources

from studio.infra.db.database import Database
from studio.shared.clock import Clock, SystemClock, to_iso
from studio.shared.errors import StudioError
from studio.shared.hashing import sha256_hex

_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(StudioError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return sha256_hex(self.sql)


def load_migrations(package: str = "studio.infra.db.migrations") -> list[Migration]:
    migrations = []
    for entry in resources.files(package).iterdir():
        match = _FILENAME.match(entry.name)
        if match:
            migrations.append(
                Migration(int(match.group(1)), match.group(2), entry.read_text(encoding="utf-8"))
            )
    migrations.sort(key=lambda m: m.version)
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"nomor migrasi ganda: {versions}")
    return migrations


def _statements(sql: str) -> list[str]:
    """Pecah skrip jadi statement utuh (aman untuk trigger BEGIN…END)."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip() and not all(
        part.strip().startswith("--") or not part.strip() for part in buffer.splitlines()
    ):
        raise MigrationError("statement terakhir tidak lengkap")
    return statements


def migrate(
    db: Database, migrations: list[Migration] | None = None, clock: Clock | None = None
) -> list[int]:
    """Terapkan migrasi yang belum ada. Mengembalikan versi yang baru diterapkan."""
    clock = clock or SystemClock()
    migrations = load_migrations() if migrations is None else migrations
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        " checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    applied = {
        int(row["version"]): str(row["checksum"])
        for row in db.query_all("SELECT version, checksum FROM schema_migrations")
    }
    newly_applied: list[int] = []
    for migration in migrations:
        if migration.version in applied:
            if applied[migration.version] != migration.checksum:
                raise MigrationError(
                    f"migrasi {migration.version:04d}_{migration.name} sudah diterapkan tapi "
                    "isinya berubah; buat file migrasi baru"
                )
            continue
        with db.transaction():
            for statement in _statements(migration.sql):
                db.execute(statement)
            db.execute(
                "INSERT INTO schema_migrations (version, name, checksum, applied_at)"
                " VALUES (?, ?, ?, ?)",
                (migration.version, migration.name, migration.checksum, to_iso(clock.now())),
            )
        newly_applied.append(migration.version)
    return newly_applied
