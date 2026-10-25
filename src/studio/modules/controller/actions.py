"""Kode aksi sekali pakai untuk tombol antarmuka chat.

`callback_data` Telegram hanya membawa kode acak pendek (13 karakter). Yang disimpan di sini
cuma hash kode itu; isi aksinya (approval mana, keputusan apa) ada di server. Sebuah kode:

- terikat ke actor yang menerimanya (owner lain tidak bisa memakainya);
- punya masa berlaku pendek;
- hangus bersama seluruh kodenya dalam satu grup (satu kartu) begitu salah satu dipakai,
  sehingga klik ganda atau tombol dari kartu lama tidak pernah dieksekusi dua kali.

Payload hanya berisi ID (tidak ada rahasia) dan tidak pernah dipercaya sebagai bukti otorisasi:
pemakai tetap diperiksa ulang sebagai owner, dan keputusan approval tetap divalidasi
`ApprovalService` (status pending, kedaluwarsa, versi episode, hash subjek).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from studio.infra.db import Database
from studio.modules.audit import AuditLog
from studio.shared.actors import Actor
from studio.shared.clock import Clock, from_iso, to_iso
from studio.shared.ids import new_id


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def new_code() -> str:
    """64 bit acak → 13 karakter base32 huruf kecil (aman untuk callback_data)."""
    return base64.b32encode(secrets.token_bytes(8)).decode("ascii").rstrip("=").lower()


class ActionCheck(StrEnum):
    OK = "ok"
    UNKNOWN = "unknown"
    WRONG_ACTOR = "wrong_actor"
    USED = "used"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ActionCode:
    id: str
    group_id: str
    actor: str
    action: str
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    used_action: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ActionCode:
        return cls(
            id=row["id"],
            group_id=row["group_id"],
            actor=row["actor"],
            action=row["action"],
            payload=json.loads(row["payload"]),
            created_at=from_iso(row["created_at"]),
            expires_at=from_iso(row["expires_at"]),
            used_at=from_iso(row["used_at"]) if row["used_at"] else None,
            used_action=row["used_action"],
        )


@dataclass(frozen=True)
class IssuedGroup:
    group_id: str
    codes: dict[str, str]  # label → kode (plaintext, hanya untuk dikirim ke chat)
    ids: dict[str, str]  # label → id baris
    expires_at: datetime


@dataclass(frozen=True)
class ActionResult:
    check: ActionCheck
    code: ActionCode | None

    @property
    def ok(self) -> bool:
        return self.check is ActionCheck.OK


class ActionCodes:
    def __init__(self, db: Database, clock: Clock, audit: AuditLog) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit

    def issue(
        self,
        actor: Actor,
        actions: dict[str, tuple[str, dict[str, Any]]],
        *,
        ttl: timedelta,
        expires_at: datetime | None = None,
    ) -> IssuedGroup:
        """Terbitkan satu grup kode. `actions` = label → (nama aksi, payload)."""
        now = self._clock.now()
        until = now + ttl if expires_at is None else min(now + ttl, expires_at)
        group_id = new_id(self._clock)
        codes: dict[str, str] = {}
        ids: dict[str, str] = {}
        with self._db.transaction():
            for label, (action, payload) in actions.items():
                code = new_code()
                row_id = new_id(self._clock)
                self._db.execute(
                    "INSERT INTO ui_action_codes (id, group_id, code_hash, actor, action, payload,"
                    " created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row_id,
                        group_id,
                        _hash(code),
                        actor.label,
                        action,
                        json.dumps(payload, sort_keys=True),
                        to_iso(now),
                        to_iso(until),
                    ),
                )
                codes[label] = code
                ids[label] = row_id
        return IssuedGroup(group_id, codes, ids, until)

    def _row_by_code(self, code: str) -> ActionCode | None:
        row = self._db.query_one(
            "SELECT * FROM ui_action_codes WHERE code_hash = ?", (_hash(code),)
        )
        return None if row is None else ActionCode.from_row(row)

    def _row_by_id(self, row_id: str) -> ActionCode | None:
        row = self._db.query_one("SELECT * FROM ui_action_codes WHERE id = ?", (row_id,))
        return None if row is None else ActionCode.from_row(row)

    def _check(self, code: ActionCode | None, actor: Actor) -> ActionCheck:
        if code is None:
            return ActionCheck.UNKNOWN
        if code.actor != actor.label:
            return ActionCheck.WRONG_ACTOR
        if code.used_at is not None:
            return ActionCheck.USED
        if self._clock.now() >= code.expires_at:
            return ActionCheck.EXPIRED
        return ActionCheck.OK

    def _consume(self, code: ActionCode | None, actor: Actor) -> ActionResult:
        with self._db.transaction():
            # Baca ulang di dalam transaksi tulis: klik ganda dari koneksi lain menunggu di sini.
            if code is not None:
                code = self._row_by_id(code.id)
            check = self._check(code, actor)
            if check is ActionCheck.OK and code is not None:
                cursor = self._db.execute(
                    "UPDATE ui_action_codes SET used_at = ?, used_action = ?"
                    " WHERE group_id = ? AND used_at IS NULL",
                    (to_iso(self._clock.now()), code.action, code.group_id),
                )
                if cursor.rowcount == 0:  # pragma: no cover - dijaga pembacaan ulang di atas
                    check = ActionCheck.USED
            if check is not ActionCheck.OK:
                self._audit.record(
                    actor=actor,
                    action="ui.action_refused",
                    entity_type="ui_action",
                    entity_id=code.id if code else "-",
                    data={"reason": check.value, "action": code.action if code else None},
                )
        return ActionResult(check, code)

    def consume(self, code: str, actor: Actor) -> ActionResult:
        """Pakai kode dari tombol. Seluruh grupnya ikut hangus (atomik)."""
        return self._consume(self._row_by_code(code), actor)

    def consume_by_id(self, row_id: str, actor: Actor) -> ActionResult:
        """Pakai aksi yang kodenya sudah dibuktikan sebelumnya (langkah lanjutan, misal catatan
        revisi yang diketik setelah memilih target revisi)."""
        return self._consume(self._row_by_id(row_id), actor)

    def supersede(self, field: str, value: str, *, actor: Actor, reason: str = "superseded") -> int:
        """Hanguskan kode aktif milik `actor` yang payload-nya menunjuk `field = value`
        (misalnya kartu lama untuk approval yang sama ketika kartu baru diterbitkan)."""
        with self._db.transaction():
            rows = self._db.query_all(
                "SELECT DISTINCT group_id FROM ui_action_codes WHERE used_at IS NULL"
                " AND actor = ? AND json_extract(payload, ?) = ?",
                (actor.label, f"$.{field}", value),
            )
            for row in rows:
                self._db.execute(
                    "UPDATE ui_action_codes SET used_at = ?, used_action = ?"
                    " WHERE group_id = ? AND used_at IS NULL",
                    (to_iso(self._clock.now()), reason, row["group_id"]),
                )
        return len(rows)

    def prune(self, *, older_than: timedelta) -> int:
        """Hapus kode yang sudah lama kedaluwarsa/dipakai (tabel ini bukan jejak audit)."""
        cutoff = to_iso(self._clock.now() - older_than)
        with self._db.transaction():
            cursor = self._db.execute(
                "DELETE FROM ui_action_codes WHERE expires_at <= ? OR used_at <= ?",
                (cutoff, cutoff),
            )
        return cursor.rowcount
