"""Akses tabel `provider_calls` (milik modul calls)."""

from __future__ import annotations

from typing import Any

from studio.infra.db import Database
from studio.modules.calls.models import CallStatus, ProviderCall
from studio.shared.errors import NotFoundError


class ProviderCallRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def by_key(self, key: str) -> ProviderCall | None:
        row = self._db.query_one("SELECT * FROM provider_calls WHERE idempotency_key = ?", (key,))
        return None if row is None else ProviderCall.from_row(row)

    def get(self, call_id: str) -> ProviderCall:
        row = self._db.query_one("SELECT * FROM provider_calls WHERE id = ?", (call_id,))
        if row is None:
            raise NotFoundError(f"panggilan provider {call_id} tidak ditemukan")
        return ProviderCall.from_row(row)

    def for_episode(self, episode_id: str) -> list[ProviderCall]:
        rows = self._db.query_all(
            "SELECT * FROM provider_calls WHERE episode_id = ? ORDER BY created_at, id",
            (episode_id,),
        )
        return [ProviderCall.from_row(r) for r in rows]

    def insert(self, values: dict[str, Any]) -> None:
        columns = ", ".join(values)
        placeholders = ", ".join("?" * len(values))
        self._db.execute(
            f"INSERT INTO provider_calls ({columns}) VALUES ({placeholders})",  # noqa: S608
            tuple(values.values()),
        )

    def restart_failed(
        self, call_id: str, *, attempt: int, ledger_entry_id: str, lease_token: int, at: str
    ) -> int:
        return self._db.execute(
            "UPDATE provider_calls SET status = 'in_flight', attempt = ?, ledger_entry_id = ?,"
            " lease_token = ?, error = NULL, updated_at = ? WHERE id = ? AND status = 'failed'",
            (attempt, ledger_entry_id, lease_token, at, call_id),
        ).rowcount

    def settle(
        self,
        call_id: str,
        *,
        attempt: int,
        status: CallStatus,
        at: str,
        response: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        actual_cost_idr: int | None = None,
        model: str | None = None,
        error: str | None = None,
    ) -> int:
        """Selesaikan panggilan yang MASIH in_flight untuk attempt yang sama."""
        return self._db.execute(
            "UPDATE provider_calls SET status = ?, response = ?, input_tokens = ?,"
            " output_tokens = ?, actual_cost_idr = ?, model = ?, error = ?, updated_at = ?"
            " WHERE id = ? AND status = 'in_flight' AND attempt = ?",
            (
                status.value,
                response,
                input_tokens,
                output_tokens,
                actual_cost_idr,
                model,
                error,
                at,
                call_id,
                attempt,
            ),
        ).rowcount
