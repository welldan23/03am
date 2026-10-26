"""Pemrosesan update chat yang tahan crash (ADR-0013).

Lifecycle satu update::

    received ──claim──▶ processing ──commit (1 transaksi dengan aksi bisnis)──▶ committed
        ▲                    │                                                     │
        └──release/backoff───┘ (error sementara / crash: lease habis)       semua balasan
                             │                                               terkirim
                             └── jatah percobaan habis ──▶ failed            ▼
                                                                          delivered

- Isi update disimpan saat diterima. Telegram (lewat aiogram) sudah menganggap update
  diterima sebelum handler selesai, jadi pemulihan setelah crash harus dari tabel ini.
- `commit()` dipanggil di DALAM transaksi yang sama dengan aksi bisnis. Kalau transaksi
  di-rollback (crash/error), update tetap `processing` dan akan diproses ulang setelah lease
  habis — aksi bisnisnya belum pernah terjadi.
- Setiap klaim menaikkan fencing token. Pemroses yang lease-nya sudah diambil alih tidak bisa
  meng-commit (dicek di dalam transaksi tulis, jadi tanpa celah check-then-act).
- Trigger database melarang update `committed`/`delivered`/`failed` kembali diproses.

Pengiriman balasan (`ReplyOutbox`) bersifat *at-least-once*: satu baris = satu panggilan Bot API.
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
from studio.shared.errors import StudioError


class InboxStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    COMMITTED = "committed"
    DELIVERED = "delivered"
    FAILED = "failed"


class ReplyStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DEAD = "dead"


class UpdateLeaseLostError(StudioError):
    """Lease update sudah diambil pemroses lain (atau update sudah di-commit)."""


@dataclass(frozen=True)
class InboxItem:
    channel: str
    update_id: int
    chat_id: str
    user_id: str | None
    payload: dict[str, Any]
    status: InboxStatus
    attempts: int
    lease_owner: str | None
    lease_token: int
    lease_until: datetime | None
    next_attempt_at: datetime
    last_error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> InboxItem:
        return cls(
            channel=row["channel"],
            update_id=row["update_id"],
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            payload=json.loads(row["payload"]),
            status=InboxStatus(row["status"]),
            attempts=row["attempts"],
            lease_owner=row["lease_owner"],
            lease_token=row["lease_token"],
            lease_until=from_iso(row["lease_until"]) if row["lease_until"] else None,
            next_attempt_at=from_iso(row["next_attempt_at"]),
            last_error=row["last_error"],
        )


@dataclass(frozen=True)
class Receipt:
    item: InboxItem
    claimed: bool  # True → pemanggil memegang lease (item.lease_token)


@dataclass(frozen=True)
class ReplyRow:
    id: int
    channel: str
    update_id: int
    seq: int
    kind: str
    payload: dict[str, Any]
    status: ReplyStatus
    attempts: int
    message_id: int | None
    last_error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ReplyRow:
        return cls(
            id=row["id"],
            channel=row["channel"],
            update_id=row["update_id"],
            seq=row["seq"],
            kind=row["kind"],
            payload=json.loads(row["payload"]),
            status=ReplyStatus(row["status"]),
            attempts=row["attempts"],
            message_id=row["message_id"],
            last_error=row["last_error"],
        )


def _backoff(attempts: int, base: float, cap: float) -> timedelta:
    return timedelta(seconds=min(cap, base * (2 ** max(attempts - 1, 0))))


class UpdateInbox:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        *,
        lease_seconds: int = 30,
        max_attempts: int = 5,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 60.0,
    ) -> None:
        self._db = db
        self._clock = clock
        self._lease = timedelta(seconds=lease_seconds)
        self.max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds

    # --- baca --------------------------------------------------------------------

    def get(self, channel: str, update_id: int) -> InboxItem | None:
        row = self._db.query_one(
            "SELECT * FROM ui_inbox WHERE channel = ? AND update_id = ?", (channel, update_id)
        )
        return None if row is None else InboxItem.from_row(row)

    def entries(self, status: InboxStatus | None = None) -> list[InboxItem]:
        sql = "SELECT * FROM ui_inbox"
        params: tuple[str, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status.value,)
        return [
            InboxItem.from_row(r) for r in self._db.query_all(sql + " ORDER BY update_id", params)
        ]

    def owns(self, channel: str, update_id: int, owner: str, token: int) -> bool:
        return bool(
            self._db.scalar(
                "SELECT 1 FROM ui_inbox WHERE channel = ? AND update_id = ? AND status = ?"
                " AND lease_owner = ? AND lease_token = ?",
                (channel, update_id, InboxStatus.PROCESSING.value, owner, token),
            )
        )

    # --- terima & klaim -------------------------------------------------------------

    def receive(
        self,
        channel: str,
        update_id: int,
        *,
        chat_id: str,
        user_id: str | None,
        payload: dict[str, Any],
        owner: str,
    ) -> Receipt:
        """Simpan update baru dan langsung klaim. Update yang sudah ada hanya diklaim ulang
        kalau belum di-commit DAN lease sebelumnya sudah habis (pemrosesnya mati)."""
        now = self._clock.now()
        with self._db.transaction():
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO ui_inbox (channel, update_id, chat_id, user_id, payload,"
                " status, attempts, lease_owner, lease_token, lease_until, next_attempt_at,"
                " received_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?)",
                (
                    channel,
                    update_id,
                    chat_id,
                    user_id,
                    json.dumps(payload, sort_keys=True),
                    InboxStatus.PROCESSING.value,
                    owner,
                    to_iso(now + self._lease),
                    to_iso(now),
                    to_iso(now),
                    to_iso(now),
                ),
            )
            claimed = cursor.rowcount == 1 or self._claim(channel, update_id, owner)
            item = self.get(channel, update_id)
        if item is None:  # pragma: no cover - baru saja di-insert / sudah ada
            raise StudioError(f"update {channel}:{update_id} hilang dari inbox")
        return Receipt(item, claimed=claimed)

    def _claim(self, channel: str, update_id: int, owner: str) -> bool:
        now = self._clock.now()
        cursor = self._db.execute(
            "UPDATE ui_inbox SET status = ?, attempts = attempts + 1, lease_owner = ?,"
            " lease_token = lease_token + 1, lease_until = ?, updated_at = ?"
            " WHERE channel = ? AND update_id = ? AND status IN (?, ?)"
            " AND next_attempt_at <= ? AND (lease_until IS NULL OR lease_until <= ?)",
            (
                InboxStatus.PROCESSING.value,
                owner,
                to_iso(now + self._lease),
                to_iso(now),
                channel,
                update_id,
                InboxStatus.RECEIVED.value,
                InboxStatus.PROCESSING.value,
                to_iso(now),
                to_iso(now),
            ),
        )
        return cursor.rowcount == 1

    def claim_due(self, owner: str, *, limit: int = 20) -> list[InboxItem]:
        """Klaim update yang belum di-commit dan siap diproses ulang (crash / error sementara)."""
        now = to_iso(self._clock.now())
        with self._db.transaction():
            rows = self._db.query_all(
                "SELECT channel, update_id FROM ui_inbox WHERE status IN (?, ?)"
                " AND next_attempt_at <= ? AND (lease_until IS NULL OR lease_until <= ?)"
                " ORDER BY update_id LIMIT ?",
                (InboxStatus.RECEIVED.value, InboxStatus.PROCESSING.value, now, now, limit),
            )
            claimed = [
                (r["channel"], r["update_id"])
                for r in rows
                if self._claim(r["channel"], r["update_id"], owner)
            ]
        items = [self.get(c, u) for c, u in claimed]
        return [i for i in items if i is not None]

    # --- hasil ------------------------------------------------------------------------

    def commit(
        self,
        channel: str,
        update_id: int,
        owner: str,
        token: int,
        replies: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Tandai `committed` + simpan balasan. WAJIB di dalam transaksi aksi bisnisnya."""
        self._finish(channel, update_id, owner, token, InboxStatus.COMMITTED, replies, None)

    def give_up(
        self,
        channel: str,
        update_id: int,
        owner: str,
        token: int,
        error: str,
        replies: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Jatah percobaan habis: tidak ada aksi bisnis; kirim pesan error saja."""
        self._finish(channel, update_id, owner, token, InboxStatus.FAILED, replies, error)

    def _finish(
        self,
        channel: str,
        update_id: int,
        owner: str,
        token: int,
        status: InboxStatus,
        replies: list[tuple[str, dict[str, Any]]],
        error: str | None,
    ) -> None:
        now = to_iso(self._clock.now())
        with self._db.transaction():
            cursor = self._db.execute(
                "UPDATE ui_inbox SET status = ?, lease_owner = NULL, lease_until = NULL,"
                " committed_at = ?, last_error = COALESCE(?, last_error), updated_at = ?"
                " WHERE channel = ? AND update_id = ? AND status = ? AND lease_owner = ?"
                " AND lease_token = ?",
                (
                    status.value,
                    now,
                    error,
                    now,
                    channel,
                    update_id,
                    InboxStatus.PROCESSING.value,
                    owner,
                    token,
                ),
            )
            if cursor.rowcount != 1:
                raise UpdateLeaseLostError(
                    f"update {channel}:{update_id} tidak lagi dipegang {owner} (token {token})"
                )
            for seq, (kind, payload) in enumerate(replies):
                self._db.execute(
                    "INSERT INTO ui_reply_outbox (channel, update_id, seq, kind, payload,"
                    " next_attempt_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (channel, update_id, seq, kind, json.dumps(payload, sort_keys=True), now, now),
                )
            if not replies and status is InboxStatus.COMMITTED:
                self._db.execute(
                    "UPDATE ui_inbox SET status = ?, delivered_at = ? WHERE channel = ?"
                    " AND update_id = ?",
                    (InboxStatus.DELIVERED.value, now, channel, update_id),
                )

    def release(self, channel: str, update_id: int, owner: str, token: int, error: str) -> bool:
        """Percobaan gagal sementara (misal SQLite busy): lepas lease, coba lagi nanti.
        Mengembalikan False kalau lease sudah bukan milik pemanggil."""
        now = self._clock.now()
        with self._db.transaction():
            item = self.get(channel, update_id)
            if item is None:
                return False
            cursor = self._db.execute(
                "UPDATE ui_inbox SET status = ?, lease_owner = NULL, lease_until = NULL,"
                " next_attempt_at = ?, last_error = ?, updated_at = ?"
                " WHERE channel = ? AND update_id = ? AND status = ? AND lease_owner = ?"
                " AND lease_token = ?",
                (
                    InboxStatus.RECEIVED.value,
                    to_iso(now + _backoff(item.attempts, self._backoff_base, self._backoff_max)),
                    error[:500],
                    to_iso(now),
                    channel,
                    update_id,
                    InboxStatus.PROCESSING.value,
                    owner,
                    token,
                ),
            )
        return cursor.rowcount == 1

    def mark_delivered(self, channel: str, update_id: int) -> bool:
        """`committed` → `delivered` kalau semua balasan sudah terkirim (atau mati)."""
        now = to_iso(self._clock.now())
        with self._db.transaction():
            pending = self._db.scalar(
                "SELECT COUNT(*) FROM ui_reply_outbox WHERE channel = ? AND update_id = ?"
                " AND status = ?",
                (channel, update_id, ReplyStatus.PENDING.value),
            )
            if pending:
                return False
            cursor = self._db.execute(
                "UPDATE ui_inbox SET status = ?, delivered_at = ?, updated_at = ?"
                " WHERE channel = ? AND update_id = ? AND status = ?",
                (
                    InboxStatus.DELIVERED.value,
                    now,
                    now,
                    channel,
                    update_id,
                    InboxStatus.COMMITTED.value,
                ),
            )
        return cursor.rowcount == 1

    def settle_delivered(self) -> int:
        """`committed` tanpa balasan tertunda → `delivered` (pemulihan setelah crash)."""
        now = to_iso(self._clock.now())
        with self._db.transaction():
            cursor = self._db.execute(
                "UPDATE ui_inbox SET status = ?, delivered_at = ?, updated_at = ?"
                " WHERE status = ? AND NOT EXISTS (SELECT 1 FROM ui_reply_outbox r"
                " WHERE r.channel = ui_inbox.channel AND r.update_id = ui_inbox.update_id"
                " AND r.status = ?)",
                (
                    InboxStatus.DELIVERED.value,
                    now,
                    now,
                    InboxStatus.COMMITTED.value,
                    ReplyStatus.PENDING.value,
                ),
            )
        return cursor.rowcount

    def next_due_at(self) -> datetime | None:
        """Kapan pemulihan berikutnya perlu jalan (update tertunda atau balasan tertunda)."""
        values = [
            self._db.scalar(
                "SELECT MIN(MAX(next_attempt_at, COALESCE(lease_until, next_attempt_at)))"
                " FROM ui_inbox WHERE status IN (?, ?)",
                (InboxStatus.RECEIVED.value, InboxStatus.PROCESSING.value),
            ),
            self._db.scalar(
                "SELECT MIN(MAX(next_attempt_at, COALESCE(claimed_until, next_attempt_at)))"
                " FROM ui_reply_outbox WHERE status = ?",
                (ReplyStatus.PENDING.value,),
            ),
        ]
        due = [from_iso(str(v)) for v in values if v is not None]
        return min(due) if due else None

    def prune(self, *, older_than: timedelta) -> int:
        """Hapus jejak update yang sudah tuntas (bukan jejak audit)."""
        cutoff = to_iso(self._clock.now() - older_than)
        done = (InboxStatus.DELIVERED.value, InboxStatus.FAILED.value)
        with self._db.transaction():
            self._db.execute(
                "DELETE FROM ui_reply_outbox WHERE (channel, update_id) IN ("
                " SELECT channel, update_id FROM ui_inbox WHERE status IN (?, ?)"
                " AND updated_at <= ?) AND status != ?",
                (*done, cutoff, ReplyStatus.PENDING.value),
            )
            cursor = self._db.execute(
                "DELETE FROM ui_inbox WHERE status IN (?, ?) AND updated_at <= ?"
                " AND NOT EXISTS (SELECT 1 FROM ui_reply_outbox r WHERE r.channel ="
                " ui_inbox.channel AND r.update_id = ui_inbox.update_id)",
                (*done, cutoff),
            )
        return cursor.rowcount


class ReplyOutbox:
    """Balasan yang menunggu dikirim ke Telegram, berurutan per update."""

    def __init__(
        self,
        db: Database,
        clock: Clock,
        *,
        lease_seconds: int = 30,
        max_attempts: int = 6,
        backoff_base_seconds: float = 2.0,
        backoff_max_seconds: float = 300.0,
    ) -> None:
        self._db = db
        self._clock = clock
        self._lease = timedelta(seconds=lease_seconds)
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds

    def for_update(self, channel: str, update_id: int) -> list[ReplyRow]:
        rows = self._db.query_all(
            "SELECT * FROM ui_reply_outbox WHERE channel = ? AND update_id = ? ORDER BY seq",
            (channel, update_id),
        )
        return [ReplyRow.from_row(r) for r in rows]

    def entries(self, status: ReplyStatus | None = None) -> list[ReplyRow]:
        sql = "SELECT * FROM ui_reply_outbox"
        params: tuple[str, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status.value,)
        return [ReplyRow.from_row(r) for r in self._db.query_all(sql + " ORDER BY id", params)]

    def claim(self, channel: str, update_id: int, owner: str) -> list[ReplyRow]:
        """Klaim balasan tertunda satu update (urut). Kosong kalau sedang dikirim pemroses lain
        atau balasan pertama belum jatuh tempo (urutan pesan dijaga)."""
        now_dt = self._clock.now()
        now = to_iso(now_dt)
        with self._db.transaction():
            rows = [
                r for r in self.for_update(channel, update_id) if r.status is ReplyStatus.PENDING
            ]
            if not rows:
                return []
            first = self._db.query_one(
                "SELECT next_attempt_at, claimed_until FROM ui_reply_outbox WHERE id = ?",
                (rows[0].id,),
            )
            if first is None:  # pragma: no cover - baru saja dibaca dalam transaksi yang sama
                return []
            busy = first["claimed_until"] is not None and first["claimed_until"] > now
            if busy or first["next_attempt_at"] > now:
                return []
            for row in rows:
                self._db.execute(
                    "UPDATE ui_reply_outbox SET claimed_by = ?, claimed_until = ? WHERE id = ?",
                    (owner, to_iso(now_dt + self._lease), row.id),
                )
        return rows

    def due_updates(self, *, limit: int = 20) -> list[tuple[str, int]]:
        now = to_iso(self._clock.now())
        rows = self._db.query_all(
            "SELECT channel, update_id, MIN(seq) FROM ui_reply_outbox WHERE status = ?"
            " AND next_attempt_at <= ? AND (claimed_until IS NULL OR claimed_until <= ?)"
            " GROUP BY channel, update_id ORDER BY MIN(id) LIMIT ?",
            (ReplyStatus.PENDING.value, now, now, limit),
        )
        return [(r["channel"], int(r["update_id"])) for r in rows]

    def mark_sent(self, row_id: int, owner: str, message_id: int | None) -> None:
        with self._db.transaction():
            self._db.execute(
                "UPDATE ui_reply_outbox SET status = ?, message_id = ?, sent_at = ?,"
                " attempts = attempts + 1, claimed_by = NULL, claimed_until = NULL"
                " WHERE id = ? AND status = ? AND claimed_by = ?",
                (
                    ReplyStatus.SENT.value,
                    message_id,
                    to_iso(self._clock.now()),
                    row_id,
                    ReplyStatus.PENDING.value,
                    owner,
                ),
            )

    def fail(
        self,
        row_id: int,
        owner: str,
        error: str,
        *,
        retry_after_s: float | None = None,
        permanent: bool = False,
    ) -> ReplyStatus:
        """Gagal kirim. Sementara → jadwal ulang (balasan berikutnya ikut menunggu supaya
        urutannya terjaga). Permanen / jatah habis → `dead`, balasan berikutnya lanjut."""
        now = self._clock.now()
        with self._db.transaction():
            row = self._db.query_one(
                "SELECT channel, update_id, attempts FROM ui_reply_outbox WHERE id = ?",
                (row_id,),
            )
            if row is None:
                return ReplyStatus.DEAD
            attempts = int(row["attempts"]) + 1
            dead = permanent or attempts >= self._max_attempts
            delay = _backoff(attempts, self._backoff_base, self._backoff_max)
            if retry_after_s is not None:
                delay = max(delay, timedelta(seconds=retry_after_s + 1))
            self._db.execute(
                "UPDATE ui_reply_outbox SET status = ?, attempts = ?, last_error = ?,"
                " next_attempt_at = ?, claimed_by = NULL, claimed_until = NULL"
                " WHERE id = ? AND claimed_by = ?",
                (
                    (ReplyStatus.DEAD if dead else ReplyStatus.PENDING).value,
                    attempts,
                    error[:500],
                    to_iso(now + delay),
                    row_id,
                    owner,
                ),
            )
            # Lepas klaim baris berikutnya milik pemroses ini (mereka menunggu giliran).
            self._db.execute(
                "UPDATE ui_reply_outbox SET claimed_by = NULL, claimed_until = NULL"
                " WHERE channel = ? AND update_id = ? AND status = ? AND claimed_by = ?",
                (row["channel"], row["update_id"], ReplyStatus.PENDING.value, owner),
            )
        return ReplyStatus.DEAD if dead else ReplyStatus.PENDING
