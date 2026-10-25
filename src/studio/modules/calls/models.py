from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from studio.infra.jobs import Lease
from studio.modules.budget import AuthorizationKind, BudgetError
from studio.shared.errors import NonRetryableError, StudioError


class CallStatus(StrEnum):
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ProviderOutcomeUnknownError(NonRetryableError):
    """Request mungkin sudah diproses (dan ditagih) tetapi hasilnya tidak diketahui.

    Tidak di-retry otomatis. Biaya dicatat sebesar reservasi (konservatif). Owner yang
    memutuskan apakah tahap diulang (yang berarti panggilan baru dengan key baru).
    """


class ProviderCallFailedError(StudioError):
    """Provider menolak / tidak tersedia secara pasti — tidak tertagih."""


class NonRetryableProviderCallError(ProviderCallFailedError, NonRetryableError):
    pass


class LLMOutputError(NonRetryableError):
    """Keluaran LLM tidak sesuai skema setelah semua retry."""


class MissingAuthorizationError(BudgetError):
    pass


@dataclass(frozen=True)
class CallScope:
    """Konteks satu rangkaian panggilan: lease job, prefix idempotency key, dan otorisasi."""

    lease: Lease
    key_prefix: str
    episode_id: str | None
    authorization: AuthorizationKind


@dataclass(frozen=True)
class ProviderCall:
    id: str
    idempotency_key: str
    episode_id: str | None
    job_id: str | None
    lease_token: int
    provider: str
    task: str
    purpose: str
    mode: str
    request_fingerprint: str
    status: CallStatus
    attempt: int
    ledger_entry_id: str
    authorization_id: str
    estimated_input_tokens: int
    max_output_tokens: int
    estimated_cost_idr: int
    response: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    actual_cost_idr: int | None
    model: str | None
    error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ProviderCall:
        return cls(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            episode_id=row["episode_id"],
            job_id=row["job_id"],
            lease_token=row["lease_token"],
            provider=row["provider"],
            task=row["task"],
            purpose=row["purpose"],
            mode=row["mode"],
            request_fingerprint=row["request_fingerprint"],
            status=CallStatus(row["status"]),
            attempt=row["attempt"],
            ledger_entry_id=row["ledger_entry_id"],
            authorization_id=row["authorization_id"],
            estimated_input_tokens=row["estimated_input_tokens"],
            max_output_tokens=row["max_output_tokens"],
            estimated_cost_idr=row["estimated_cost_idr"],
            response=json.loads(row["response"]) if row["response"] else None,
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            actual_cost_idr=row["actual_cost_idr"],
            model=row["model"],
            error=row["error"],
        )

    def ref(self, *, reused: bool) -> dict[str, Any]:
        """Jejak biaya untuk disimpan di artefak (estimasi, otorisasi, key, ledger)."""
        return {
            "call_id": self.id,
            "task": self.task,
            "purpose": self.purpose,
            "idempotency_key": self.idempotency_key,
            "authorization_id": self.authorization_id,
            "ledger_entry_id": self.ledger_entry_id,
            "estimated_input_tokens": self.estimated_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "estimated_cost_idr": self.estimated_cost_idr,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "actual_cost_idr": self.actual_cost_idr,
            "mode": self.mode,
            "reused": reused,
        }
