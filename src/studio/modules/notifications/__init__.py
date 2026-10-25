"""Outbox notifikasi persisten (ADR-0012).

Baris outbox dibuat oleh trigger database di transaksi yang sama dengan kejadiannya
(migrasi 0005). Modul ini hanya mengklaim, menandai terkirim, dan menjadwalkan ulang.
Pengiriman (I/O ke Telegram) dilakukan pemanggil di LUAR transaksi.

Jaminan: *at-least-once* per penerima. `delivered_to` mencegah penerima yang sudah menerima
dikirimi ulang saat notifikasi yang sama dicoba lagi; duplikat hanya mungkin kalau proses mati
tepat di antara "terkirim" dan "dicatat terkirim".
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from studio.infra.db import Database
from studio.shared.clock import Clock, from_iso, to_iso


class NotificationKind(StrEnum):
    APPROVAL_REQUESTED = "approval.requested"
    RESEARCH_STARTED = "research.started"
    RESEARCH_BRIEF_READY = "research.brief_ready"
    SCRIPT_READY = "script.ready"
    EPISODE_FAILED = "episode.failed"
    EPISODE_COMPLETED = "episode.completed"
    EPISODE_CLOSED = "episode.closed"
    JOB_RETRY = "job.retry"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DEAD = "dead"


@dataclass(frozen=True)
class Notification:
    id: int
    event_key: str
    kind: NotificationKind
    episode_id: str | None
    ref_id: str | None
    data: dict[str, Any]
    status: NotificationStatus
    attempts: int
    next_attempt_at: datetime
    delivered_to: tuple[str, ...]
    last_error: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Notification:
        return cls(
            id=row["id"],
            event_key=row["event_key"],
            kind=NotificationKind(row["kind"]),
            episode_id=row["episode_id"],
            ref_id=row["ref_id"],
            data=json.loads(row["data"]),
            status=NotificationStatus(row["status"]),
            attempts=row["attempts"],
            next_attempt_at=from_iso(row["next_attempt_at"]),
            delivered_to=tuple(json.loads(row["delivered_to"])),
            last_error=row["last_error"],
            created_at=from_iso(row["created_at"]),
        )


class Outbox:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        *,
        max_attempts: int = 8,
        backoff_base_seconds: int = 5,
        backoff_max_seconds: int = 600,
    ) -> None:
        self._db = db
        self._clock = clock
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds

    def get(self, notification_id: int) -> Notification:
        row = self._db.query_one(
            "SELECT * FROM notification_outbox WHERE id = ?", (notification_id,)
        )
        if row is None:
            raise KeyError(notification_id)
        return Notification.from_row(row)

    def entries(self, status: NotificationStatus | None = None) -> list[Notification]:
        if status is None:
            rows = self._db.query_all("SELECT * FROM notification_outbox ORDER BY id")
        else:
            rows = self._db.query_all(
                "SELECT * FROM notification_outbox WHERE status = ? ORDER BY id", (status.value,)
            )
        return [Notification.from_row(r) for r in rows]

    def claim(
        self, consumer: str, *, limit: int = 20, lease_seconds: int = 60
    ) -> list[Notification]:
        """Klaim notifikasi yang jatuh tempo. Klaim yang lease-nya habis boleh diambil ulang."""
        now_dt = self._clock.now()
        now = to_iso(now_dt)
        until = to_iso(now_dt + timedelta(seconds=lease_seconds))
        with self._db.transaction():
            rows = self._db.query_all(
                "SELECT id FROM notification_outbox WHERE status = 'pending'"
                " AND next_attempt_at <= ? AND (claimed_until IS NULL OR claimed_until <= ?)"
                " ORDER BY id LIMIT ?",
                (now, now, limit),
            )
            ids = [int(r["id"]) for r in rows]
            for notification_id in ids:
                self._db.execute(
                    "UPDATE notification_outbox SET claimed_by = ?, claimed_until = ? WHERE id = ?",
                    (consumer, until, notification_id),
                )
        return [self.get(i) for i in ids]

    def mark_delivered(self, notification_id: int, consumer: str, recipient: str) -> None:
        """Catat satu penerima sudah menerima (dipanggil segera setelah kirim berhasil)."""
        with self._db.transaction():
            current = self.get(notification_id)
            if recipient in current.delivered_to:
                return
            self._db.execute(
                "UPDATE notification_outbox SET delivered_to = ? WHERE id = ? AND claimed_by = ?",
                (json.dumps([*current.delivered_to, recipient]), notification_id, consumer),
            )

    def complete(self, notification_id: int, consumer: str) -> None:
        with self._db.transaction():
            self._db.execute(
                "UPDATE notification_outbox SET status = 'sent', sent_at = ?, claimed_by = NULL,"
                " claimed_until = NULL, last_error = NULL WHERE id = ? AND claimed_by = ?"
                " AND status = 'pending'",
                (to_iso(self._clock.now()), notification_id, consumer),
            )

    def fail(
        self,
        notification_id: int,
        consumer: str,
        error: str,
        *,
        retry_after_s: float | None = None,
        permanent: bool = False,
    ) -> Notification:
        """Jadwalkan ulang dengan backoff (atau hormati `retry_after` dari Telegram)."""
        now_dt = self._clock.now()
        with self._db.transaction():
            current = self.get(notification_id)
            attempts = current.attempts + 1
            if permanent or attempts >= self._max_attempts:
                self._db.execute(
                    "UPDATE notification_outbox SET status = 'dead', attempts = ?,"
                    " last_error = ?, claimed_by = NULL, claimed_until = NULL"
                    " WHERE id = ? AND claimed_by = ?",
                    (attempts, error[:500], notification_id, consumer),
                )
            else:
                delay = min(self._backoff_max, self._backoff_base * (2 ** (attempts - 1)))
                if retry_after_s is not None:
                    delay = max(delay, int(retry_after_s) + 1)
                self._db.execute(
                    "UPDATE notification_outbox SET attempts = ?, last_error = ?,"
                    " next_attempt_at = ?, claimed_by = NULL, claimed_until = NULL"
                    " WHERE id = ? AND claimed_by = ?",
                    (
                        attempts,
                        error[:500],
                        to_iso(now_dt + timedelta(seconds=delay)),
                        notification_id,
                        consumer,
                    ),
                )
        return self.get(notification_id)

    def next_due_at(self) -> datetime | None:
        """Waktu notifikasi pending terdekat (untuk menentukan kapan dispatcher bangun)."""
        value = self._db.scalar(
            "SELECT MIN(next_attempt_at) FROM notification_outbox WHERE status = 'pending'"
        )
        return None if value is None else from_iso(str(value))


__all__ = ["Notification", "NotificationKind", "NotificationStatus", "Outbox"]
