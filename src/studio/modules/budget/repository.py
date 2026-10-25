"""Akses tabel milik modul budget. Hanya dipakai dari dalam modul ini."""

from __future__ import annotations

from typing import Any

from studio.infra.db import Database
from studio.modules.budget.models import (
    AuthorizationKind,
    BudgetPeriod,
    Category,
    LedgerEntry,
    Mode,
    SpendAuthorization,
)
from studio.shared.errors import NotFoundError

_USED = (
    "COALESCE(SUM(CASE status WHEN 'reserved' THEN reserved_idr"
    " WHEN 'committed' THEN actual_idr ELSE 0 END), 0)"
)


class BudgetRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- periode -----------------------------------------------------------

    def get_period(self, period: str) -> BudgetPeriod | None:
        row = self._db.query_one("SELECT * FROM budget_periods WHERE period = ?", (period,))
        return None if row is None else BudgetPeriod.from_row(row)

    def upsert_period(
        self, *, period: str, plan: str, plan_hash: str, fx: str, activated_by: str, at: str
    ) -> None:
        self._db.execute(
            "INSERT INTO budget_periods (period, status, plan, plan_hash, fx_usd_idr,"
            " activated_by, activated_at) VALUES (?, 'active', ?, ?, ?, ?, ?)"
            " ON CONFLICT (period) DO UPDATE SET status = 'active', plan = excluded.plan,"
            " plan_hash = excluded.plan_hash, fx_usd_idr = excluded.fx_usd_idr,"
            " activated_by = excluded.activated_by, activated_at = excluded.activated_at",
            (period, plan, plan_hash, fx, activated_by, at),
        )

    # --- otorisasi ---------------------------------------------------------

    def get_authorization(self, authorization_id: str) -> SpendAuthorization:
        row = self._db.query_one(
            "SELECT * FROM spend_authorizations WHERE id = ?", (authorization_id,)
        )
        if row is None:
            raise NotFoundError(f"otorisasi {authorization_id} tidak ditemukan")
        return SpendAuthorization.from_row(row)

    def operational_for_period(self, period: str) -> SpendAuthorization | None:
        row = self._db.query_one(
            "SELECT * FROM spend_authorizations WHERE kind = 'operational' AND period = ?",
            (period,),
        )
        return None if row is None else SpendAuthorization.from_row(row)

    def active_for_episode(
        self, episode_id: str, kind: AuthorizationKind
    ) -> SpendAuthorization | None:
        row = self._db.query_one(
            "SELECT * FROM spend_authorizations"
            " WHERE episode_id = ? AND kind = ? AND status = 'active'",
            (episode_id, kind.value),
        )
        return None if row is None else SpendAuthorization.from_row(row)

    def authorizations(
        self, *, episode_id: str | None = None, approval_ids: list[str] | None = None
    ) -> list[SpendAuthorization]:
        sql = "SELECT * FROM spend_authorizations WHERE status = 'active'"
        params: list[Any] = []
        if episode_id is not None:
            sql += " AND episode_id = ?"
            params.append(episode_id)
        if approval_ids is not None:
            if not approval_ids:
                return []
            sql += f" AND approval_id IN ({','.join('?' * len(approval_ids))})"
            params.extend(approval_ids)
        return [SpendAuthorization.from_row(r) for r in self._db.query_all(sql, params)]

    def insert_authorization(
        self,
        *,
        authorization_id: str,
        kind: AuthorizationKind,
        period: str | None,
        episode_id: str | None,
        approval_id: str | None,
        max_idr: int,
        created_by: str,
        at: str,
    ) -> None:
        self._db.execute(
            "INSERT INTO spend_authorizations (id, kind, period, episode_id, approval_id,"
            " max_idr, status, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                authorization_id,
                kind.value,
                period,
                episode_id,
                approval_id,
                max_idr,
                created_by,
                at,
            ),
        )

    def update_authorization_max(self, authorization_id: str, max_idr: int) -> None:
        self._db.execute(
            "UPDATE spend_authorizations SET max_idr = ?, status = 'active',"
            " revoked_at = NULL, revoke_reason = NULL WHERE id = ?",
            (max_idr, authorization_id),
        )

    def revoke_authorization(self, authorization_id: str, reason: str, at: str) -> None:
        self._db.execute(
            "UPDATE spend_authorizations SET status = 'revoked', revoked_at = ?,"
            " revoke_reason = ? WHERE id = ? AND status = 'active'",
            (at, reason, authorization_id),
        )

    # --- ledger ------------------------------------------------------------

    def ledger_by_key(self, idempotency_key: str) -> LedgerEntry | None:
        row = self._db.query_one(
            "SELECT * FROM ledger_entries WHERE idempotency_key = ?", (idempotency_key,)
        )
        return None if row is None else LedgerEntry.from_row(row)

    def ledger_get(self, entry_id: str) -> LedgerEntry:
        row = self._db.query_one("SELECT * FROM ledger_entries WHERE id = ?", (entry_id,))
        if row is None:
            raise NotFoundError(f"entri ledger {entry_id} tidak ditemukan")
        return LedgerEntry.from_row(row)

    def insert_ledger(self, values: dict[str, Any]) -> None:
        columns = ", ".join(values)
        placeholders = ", ".join("?" * len(values))
        self._db.execute(
            f"INSERT INTO ledger_entries ({columns}) VALUES ({placeholders})",  # noqa: S608
            tuple(values.values()),
        )

    def mark_committed(
        self, entry_id: str, *, usd_micros: int, idr: int, overrun: bool, at: str
    ) -> int:
        cursor = self._db.execute(
            "UPDATE ledger_entries SET status = 'committed', actual_usd_micros = ?,"
            " actual_idr = ?, overrun = ?, updated_at = ? WHERE id = ? AND status = 'reserved'",
            (usd_micros, idr, int(overrun), at, entry_id),
        )
        return cursor.rowcount

    def mark_released(self, entry_id: str, at: str) -> int:
        cursor = self._db.execute(
            "UPDATE ledger_entries SET status = 'released', updated_at = ?"
            " WHERE id = ? AND status = 'reserved'",
            (at, entry_id),
        )
        return cursor.rowcount

    def ledger(
        self, *, period: str | None = None, episode_id: str | None = None
    ) -> list[LedgerEntry]:
        sql = "SELECT * FROM ledger_entries WHERE 1 = 1"
        params: list[Any] = []
        if period is not None:
            sql += " AND period = ?"
            params.append(period)
        if episode_id is not None:
            sql += " AND episode_id = ?"
            params.append(episode_id)
        rows = self._db.query_all(sql + " ORDER BY created_at, id", params)
        return [LedgerEntry.from_row(r) for r in rows]

    # --- pemakaian ---------------------------------------------------------

    def category_usage(self, period: str, mode: Mode, category: Category) -> tuple[int, int]:
        row = self._db.query_one(
            "SELECT"
            " COALESCE(SUM(CASE WHEN status = 'committed' THEN actual_idr END), 0) AS committed,"
            " COALESCE(SUM(CASE WHEN status = 'reserved' THEN reserved_idr END), 0) AS reserved"
            " FROM ledger_entries WHERE period = ? AND mode = ? AND category = ?",
            (period, mode.value, category.value),
        )
        if row is None:  # pragma: no cover - agregat selalu mengembalikan satu baris
            return 0, 0
        return int(row["committed"]), int(row["reserved"])

    def total_usage(self, period: str, mode: Mode) -> int:
        return int(
            self._db.scalar(
                f"SELECT {_USED} FROM ledger_entries WHERE period = ? AND mode = ?",  # noqa: S608
                (period, mode.value),
            )
        )

    def authorization_usage(self, authorization_id: str, mode: Mode) -> int:
        return int(
            self._db.scalar(
                f"SELECT {_USED} FROM ledger_entries"  # noqa: S608
                " WHERE authorization_id = ? AND mode = ?",
                (authorization_id, mode.value),
            )
        )

    def usage_by_source(self, period: str, mode: Mode) -> dict[str, int]:
        rows = self._db.query_all(
            f"SELECT source, {_USED} AS used FROM ledger_entries"  # noqa: S608
            " WHERE period = ? AND mode = ? GROUP BY source",
            (period, mode.value),
        )
        return {r["source"]: int(r["used"]) for r in rows}
