from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from studio.shared.clock import from_iso
from studio.shared.errors import NonRetryableError, StudioError
from studio.shared.gates import Gate


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"


DECISION_STATUS: dict[Decision, ApprovalStatus] = {
    Decision.APPROVE: ApprovalStatus.APPROVED,
    Decision.REJECT: ApprovalStatus.REJECTED,
    Decision.REVISE: ApprovalStatus.REVISION_REQUESTED,
}


class DecisionOutcome(StrEnum):
    ACCEPTED = "accepted"
    NOT_AUTHORIZED = "not_authorized"
    NOT_PENDING = "not_pending"
    EXPIRED = "expired"
    INVALID_TOKEN = "invalid_token"  # noqa: S105 - nama status, bukan secret
    STALE = "stale"


class ApprovalError(NonRetryableError):
    pass


class ApprovalNotPendingError(ApprovalError):
    pass


class ApprovalExpiredError(ApprovalError):
    pass


class InvalidApprovalTokenError(ApprovalError):
    pass


class StaleApprovalError(ApprovalError):
    """Konten berubah sejak approval dibuat. Owner harus melihat kartu baru."""

    def __init__(self, message: str, replacement_id: str | None = None) -> None:
        super().__init__(message)
        self.replacement_id = replacement_id


class ApprovalStateError(StudioError):
    pass


@dataclass(frozen=True)
class Approval:
    id: str
    episode_id: str
    gate: Gate
    episode_version: int
    subject: dict[str, Any]
    subject_hash: str
    spend_cap_idr: int | None
    status: ApprovalStatus
    has_token: bool
    requested_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    notes: str | None
    decision_data: dict[str, Any]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Approval:
        return cls(
            id=row["id"],
            episode_id=row["episode_id"],
            gate=Gate(row["gate"]),
            episode_version=row["episode_version"],
            subject=json.loads(row["subject"]),
            subject_hash=row["subject_hash"],
            spend_cap_idr=row["spend_cap_idr"],
            status=ApprovalStatus(row["status"]),
            has_token=row["token_hash"] is not None,
            requested_at=from_iso(row["requested_at"]),
            expires_at=from_iso(row["expires_at"]),
            decided_at=from_iso(row["decided_at"]) if row["decided_at"] else None,
            decided_by=row["decided_by"],
            notes=row["notes"],
            decision_data=json.loads(row["decision_data"]),
        )


@dataclass(frozen=True)
class DecisionResult:
    outcome: DecisionOutcome
    approval: Approval
    message: str

    @property
    def accepted(self) -> bool:
        return self.outcome is DecisionOutcome.ACCEPTED
