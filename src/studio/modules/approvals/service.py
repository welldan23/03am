"""Approval gate G0–G3 yang terikat versi konten.

`decide` tidak melempar exception untuk hasil yang mengubah state (stale/expired) supaya
perubahan itu tetap tersimpan walau dipanggil di dalam transaksi pemanggil. Pemanggil
(`workflow`) yang mengubah `DecisionResult` menjadi exception setelah commit.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any

from studio.infra.db import Database
from studio.modules.approvals.models import (
    DECISION_STATUS,
    Approval,
    ApprovalStateError,
    ApprovalStatus,
    Decision,
    DecisionOutcome,
    DecisionResult,
)
from studio.modules.audit import AuditLog
from studio.shared.actors import Actor, OwnerPolicy
from studio.shared.clock import Clock, to_iso
from studio.shared.errors import NotFoundError
from studio.shared.gates import Gate
from studio.shared.hashing import canonical_json, content_hash
from studio.shared.ids import new_id


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compute_subject_hash(
    *, episode_id: str, gate: Gate, subject: Mapping[str, Any], spend_cap_idr: int | None
) -> str:
    return content_hash(
        {
            "episode_id": episode_id,
            "gate": gate.value,
            "subject": dict(subject),
            "spend_cap_idr": spend_cap_idr,
        }
    )


class ApprovalService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        audit: AuditLog,
        owners: OwnerPolicy,
        *,
        ttl: timedelta,
    ) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit
        self._owners = owners
        self._ttl = ttl

    # --- baca --------------------------------------------------------------

    def get(self, approval_id: str) -> Approval:
        row = self._db.query_one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        if row is None:
            raise NotFoundError(f"approval {approval_id} tidak ditemukan")
        return Approval.from_row(row)

    def pending(self, episode_id: str | None = None) -> list[Approval]:
        sql = "SELECT * FROM approvals WHERE status = 'pending'"
        params: tuple[str, ...] = ()
        if episode_id is not None:
            sql += " AND episode_id = ?"
            params = (episode_id,)
        return [
            Approval.from_row(r) for r in self._db.query_all(sql + " ORDER BY requested_at", params)
        ]

    def for_episode(self, episode_id: str) -> list[Approval]:
        rows = self._db.query_all(
            "SELECT * FROM approvals WHERE episode_id = ? ORDER BY requested_at", (episode_id,)
        )
        return [Approval.from_row(r) for r in rows]

    def latest_approved(self, episode_id: str, gate: Gate) -> Approval | None:
        row = self._db.query_one(
            "SELECT * FROM approvals WHERE episode_id = ? AND gate = ? AND status = 'approved'"
            " ORDER BY decided_at DESC LIMIT 1",
            (episode_id, gate.value),
        )
        return None if row is None else Approval.from_row(row)

    def find_by_token(self, token: str) -> Approval | None:
        row = self._db.query_one(
            "SELECT * FROM approvals WHERE token_hash = ? AND status = 'pending'",
            (_hash_token(token),),
        )
        return None if row is None else Approval.from_row(row)

    # --- tulis -------------------------------------------------------------

    def request(
        self,
        *,
        episode_id: str,
        gate: Gate,
        episode_version: int,
        subject: Mapping[str, Any],
        spend_cap_idr: int | None,
        actor: Actor,
    ) -> Approval:
        """Buka approval baru. Approval `pending` lama untuk gate yang sama digantikan."""
        now = self._clock.now()
        with self._db.transaction():
            for old in self._db.query_all(
                "SELECT id FROM approvals WHERE episode_id = ? AND gate = ? AND status = 'pending'",
                (episode_id, gate.value),
            ):
                self._set_status(
                    old["id"], ApprovalStatus.SUPERSEDED, actor, "diganti approval baru"
                )
            approval_id = new_id(self._clock)
            subject_hash = compute_subject_hash(
                episode_id=episode_id, gate=gate, subject=subject, spend_cap_idr=spend_cap_idr
            )
            self._db.execute(
                "INSERT INTO approvals (id, episode_id, gate, episode_version, subject,"
                " subject_hash, spend_cap_idr, status, requested_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    approval_id,
                    episode_id,
                    gate.value,
                    episode_version,
                    canonical_json(dict(subject)),
                    subject_hash,
                    spend_cap_idr,
                    to_iso(now),
                    to_iso(now + self._ttl),
                ),
            )
            self._audit.record(
                actor=actor,
                action="approval.requested",
                entity_type="approval",
                entity_id=approval_id,
                episode_id=episode_id,
                data={
                    "gate": gate.value,
                    "subject_hash": subject_hash,
                    "spend_cap_idr": spend_cap_idr,
                    "episode_version": episode_version,
                },
            )
        return self.get(approval_id)

    def issue_token(self, approval_id: str, actor: Actor) -> str:
        """Buat token sekali pakai untuk tombol. Token lama otomatis tidak berlaku."""
        token = secrets.token_urlsafe(24)
        with self._db.transaction():
            cursor = self._db.execute(
                "UPDATE approvals SET token_hash = ? WHERE id = ? AND status = 'pending'",
                (_hash_token(token), approval_id),
            )
            if cursor.rowcount != 1:
                raise ApprovalStateError(f"approval {approval_id} tidak pending")
            self._audit.record(
                actor=actor,
                action="approval.token_issued",
                entity_type="approval",
                entity_id=approval_id,
                episode_id=self.get(approval_id).episode_id,
            )
        return token

    def decide(
        self,
        approval_id: str,
        decision: Decision,
        *,
        actor: Actor,
        current_subject_hash: str,
        current_episode_version: int,
        token: str | None = None,
        notes: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> DecisionResult:
        with self._db.transaction():
            approval = self.get(approval_id)

            def refuse(outcome: DecisionOutcome, message: str) -> DecisionResult:
                self._audit.record(
                    actor=actor,
                    action="approval.refused",
                    entity_type="approval",
                    entity_id=approval_id,
                    episode_id=approval.episode_id,
                    data={"decision": decision.value, "outcome": outcome.value, "message": message},
                )
                return DecisionResult(outcome, self.get(approval_id), message)

            if not self._owners.is_owner(actor):
                return refuse(
                    DecisionOutcome.NOT_AUTHORIZED,
                    f"{actor.label} tidak berhak memutuskan approval",
                )
            if approval.status is not ApprovalStatus.PENDING:
                return refuse(
                    DecisionOutcome.NOT_PENDING, f"approval sudah berstatus {approval.status.value}"
                )
            if self._clock.now() >= approval.expires_at:
                self._set_status(approval_id, ApprovalStatus.EXPIRED, actor, "kedaluwarsa")
                return refuse(DecisionOutcome.EXPIRED, "approval sudah kedaluwarsa")
            if token is not None:
                row = self._db.query_one(
                    "SELECT token_hash FROM approvals WHERE id = ?", (approval_id,)
                )
                stored = row["token_hash"] if row else None
                if stored is None or not hmac.compare_digest(stored, _hash_token(token)):
                    return refuse(
                        DecisionOutcome.INVALID_TOKEN, "token tidak valid atau sudah diganti"
                    )
            if (
                current_subject_hash != approval.subject_hash
                or current_episode_version != approval.episode_version
            ):
                self._set_status(
                    approval_id,
                    ApprovalStatus.SUPERSEDED,
                    actor,
                    "konten berubah sejak approval dibuat",
                )
                return refuse(DecisionOutcome.STALE, "konten berubah sejak approval dibuat")

            cursor = self._db.execute(
                "UPDATE approvals SET status = ?, decided_at = ?, decided_by = ?, notes = ?,"
                " decision_data = ?, token_hash = NULL WHERE id = ? AND status = 'pending'",
                (
                    DECISION_STATUS[decision].value,
                    to_iso(self._clock.now()),
                    actor.label,
                    notes,
                    canonical_json(dict(data or {})),
                    approval_id,
                ),
            )
            if cursor.rowcount != 1:
                return refuse(DecisionOutcome.NOT_PENDING, "approval sudah diputuskan")
            self._audit.record(
                actor=actor,
                action="approval.decided",
                entity_type="approval",
                entity_id=approval_id,
                episode_id=approval.episode_id,
                data={
                    "gate": approval.gate.value,
                    "decision": decision.value,
                    "notes": notes,
                    "data": dict(data or {}),
                },
            )
            return DecisionResult(DecisionOutcome.ACCEPTED, self.get(approval_id), "diterima")

    def supersede(
        self, episode_id: str, gates: Iterable[Gate], *, actor: Actor, reason: str
    ) -> list[Approval]:
        """Gantikan approval pending/approved di gate tertentu; kembalikan yang tadinya approved."""
        gate_values = [g.value for g in gates]
        if not gate_values:
            return []
        superseded_approved: list[Approval] = []
        placeholders = ",".join("?" * len(gate_values))
        with self._db.transaction():
            rows = self._db.query_all(
                f"SELECT * FROM approvals WHERE episode_id = ? AND gate IN ({placeholders})"  # noqa: S608
                " AND status IN ('pending', 'approved')",
                (episode_id, *gate_values),
            )
            for row in rows:
                approval = Approval.from_row(row)
                self._set_status(approval.id, ApprovalStatus.SUPERSEDED, actor, reason)
                if approval.status is ApprovalStatus.APPROVED:
                    superseded_approved.append(approval)
        return superseded_approved

    def _set_status(
        self, approval_id: str, status: ApprovalStatus, actor: Actor, reason: str
    ) -> None:
        self._db.execute(
            "UPDATE approvals SET status = ?, token_hash = NULL WHERE id = ?",
            (status.value, approval_id),
        )
        self._audit.record(
            actor=actor,
            action=f"approval.{status.value}",
            entity_type="approval",
            entity_id=approval_id,
            episode_id=self.get(approval_id).episode_id,
            data={"reason": reason},
        )
