"""Orkestrator produksi: menghubungkan episode, artefak, approval, anggaran, dan job.

Ini satu-satunya modul yang boleh memakai beberapa modul domain sekaligus.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from studio.infra.db import Database
from studio.infra.jobs import Handler, Job, JobOutcome, JobQueue
from studio.modules.approvals import (
    Approval,
    ApprovalExpiredError,
    ApprovalNotPendingError,
    ApprovalService,
    Decision,
    DecisionOutcome,
    DecisionResult,
    InvalidApprovalTokenError,
    StaleApprovalError,
    compute_subject_hash,
)
from studio.modules.artifacts import Artifact, ArtifactKind, ArtifactStore
from studio.modules.audit import AuditLog
from studio.modules.budget import (
    AuthorizationKind,
    BudgetExceededError,
    BudgetGuard,
    BudgetPlan,
    BudgetService,
    CostEstimate,
    EstimateLine,
    Mode,
    PricingTable,
    Source,
    SpendRequest,
    estimate,
)
from studio.modules.episodes import Category, Episode, EpisodeService, EpisodeStatus, Trigger, state
from studio.modules.workflow.placeholders import PLACEHOLDER_STAGES
from studio.shared.actors import Actor, ActorKind, OwnerPolicy
from studio.shared.errors import NotAuthorizedError, NotFoundError, StudioError
from studio.shared.gates import Gate

STAGE_JOB = "episode.stage"

GATE_SUBJECT: Mapping[Gate, tuple[ArtifactKind, ...]] = {
    Gate.TOPIC: (ArtifactKind.TOPICS,),
    Gate.EDITORIAL: (
        ArtifactKind.RESEARCH,
        ArtifactKind.FACTCHECK,
        ArtifactKind.SCRIPT,
        ArtifactKind.STORYBOARD,
    ),
    Gate.COST: (ArtifactKind.SCRIPT, ArtifactKind.STORYBOARD, ArtifactKind.COST_ESTIMATE),
    Gate.FINAL: (
        ArtifactKind.SCRIPT,
        ArtifactKind.STORYBOARD,
        ArtifactKind.COST_ESTIMATE,
        ArtifactKind.RENDER,
    ),
}

_SYSTEM = Actor.system("workflow")


class WorkflowError(StudioError):
    pass


@dataclass
class _Stage:
    """Konteks yang diberikan ke handler tahap (lihat `placeholders.StageContext`)."""

    workflow: WorkflowService
    episode: Episode
    job: Job
    notes: str | None

    def put(self, kind: ArtifactKind, content: dict[str, Any]) -> Artifact:
        return self.workflow._artifacts.put(self.episode.id, kind, content, _SYSTEM)

    def latest(self, kind: ArtifactKind) -> Artifact:
        artifact = self.workflow._artifacts.latest(self.episode.id, kind)
        if artifact is None:
            raise WorkflowError(f"artefak {kind.value} belum ada untuk episode {self.episode.id}")
        return artifact

    def spend_llm(
        self,
        label: str,
        *,
        tier: str,
        input_tokens: int,
        output_tokens: int,
        authorization: AuthorizationKind,
    ) -> None:
        usd = self.workflow._pricing.llm_call_usd_micros(tier, input_tokens, output_tokens)
        self.workflow._spend(
            self.episode,
            self.job,
            label,
            authorization=authorization,
            usd_micros=usd,
            price_ref=self.workflow._pricing.ref(f"openai.{tier}"),
            category_key=f"openai.{tier}.input",
            meta={"tier": tier, "input_tokens": input_tokens, "output_tokens": output_tokens},
        )

    def spend_units(
        self, label: str, *, price_key: str, quantity: int, authorization: AuthorizationKind
    ) -> None:
        usd = self.workflow._pricing.cost_usd_micros(price_key, quantity)
        self.workflow._spend(
            self.episode,
            self.job,
            label,
            authorization=authorization,
            usd_micros=usd,
            price_ref=self.workflow._pricing.ref(price_key),
            category_key=price_key,
            meta={"quantity": quantity},
        )

    def estimate(self, lines: list[EstimateLine]) -> CostEstimate:
        period = self.workflow._budget.period()
        if period is None:
            raise BudgetExceededError("periode anggaran belum diaktifkan; tidak bisa estimasi")
        return estimate(
            self.workflow._pricing,
            lines,
            fx=period.fx_rate,
            margin_pct=self.workflow._plan.limits.production_margin_pct,
        )


class WorkflowService:
    # Fase 1: semua provider adalah mock, jadi semua belanja bermode simulasi.
    MODE = Mode.SIMULATED

    def __init__(
        self,
        *,
        db: Database,
        audit: AuditLog,
        owners: OwnerPolicy,
        episodes: EpisodeService,
        artifacts: ArtifactStore,
        approvals: ApprovalService,
        budget: BudgetService,
        guard: BudgetGuard,
        queue: JobQueue,
        pricing: PricingTable,
        plan: BudgetPlan,
    ) -> None:
        self._db = db
        self._audit = audit
        self._owners = owners
        self._episodes = episodes
        self._artifacts = artifacts
        self._approvals = approvals
        self._budget = budget
        self._guard = guard
        self._queue = queue
        self._pricing = pricing
        self._plan = plan

    # --- perintah ----------------------------------------------------------

    def _require_owner_or_director(self, actor: Actor, action: str) -> None:
        if actor.kind is ActorKind.DIRECTOR or self._owners.is_owner(actor):
            return
        raise NotAuthorizedError(f"{actor.label} tidak berhak '{action}'")

    def create_episode(
        self, *, category: Category, target_duration_s: int, idea: str | None, actor: Actor
    ) -> Episode:
        self._require_owner_or_director(actor, "membuat episode")
        return self._episodes.create(
            category=category, target_duration_s=target_duration_s, idea=idea, actor=actor
        )

    def start(self, episode_id: str, actor: Actor) -> Episode:
        self._require_owner_or_director(actor, "memulai episode")
        with self._db.transaction():
            episode = self._episodes.get(episode_id)
            updated = self._episodes.transition(
                episode_id,
                trigger=Trigger.START,
                target=EpisodeStatus.DISCOVERING,
                actor=actor,
                expected_version=episode.version,
            )
            self._enqueue_stage(updated)
        return updated

    def decide(
        self,
        approval_id: str,
        decision: Decision,
        *,
        actor: Actor,
        notes: str | None = None,
        choice: int | None = None,
        revise_to: EpisodeStatus | None = None,
        token: str | None = None,
    ) -> Episode:
        """Keputusan manusia di gate. Hanya owner di allowlist yang diterima."""
        failure: Exception | None = None
        with self._db.transaction():
            approval = self._approvals.get(approval_id)
            episode = self._episodes.get(approval.episode_id)
            gate_status = state.GATE_STATUS[approval.gate]
            at_gate = episode.status is gate_status
            is_owner = self._owners.is_owner(actor)

            data: dict[str, Any] = {}
            if decision is Decision.REVISE:
                if revise_to not in state.REVISION_TARGETS[gate_status]:
                    allowed = ", ".join(
                        sorted(s.value for s in state.REVISION_TARGETS[gate_status])
                    )
                    raise WorkflowError(f"target revisi harus salah satu dari: {allowed}")
                data["revise_to"] = revise_to.value
            if decision is Decision.APPROVE and approval.gate is Gate.TOPIC and at_gate:
                data["choice"] = self._validate_topic_choice(episode, choice)
            if decision is Decision.APPROVE and approval.gate is Gate.COST and at_gate and is_owner:
                try:
                    self._budget.check_affordable(
                        CostEstimate.from_dict(
                            self._latest(episode, ArtifactKind.COST_ESTIMATE).content
                        ),
                        self.MODE,
                    )
                except BudgetExceededError as exc:
                    # Dicatat lalu di-raise SETELAH commit supaya jejak penolakannya tersimpan.
                    self._audit.record(
                        actor=actor,
                        action="budget.denied",
                        entity_type="approval",
                        entity_id=approval_id,
                        episode_id=episode.id,
                        data={"gate": approval.gate.value, "reason": exc.reason},
                    )
                    failure = exc

            if failure is None:
                current_hash = (
                    self._current_subject_hash(episode, approval.gate) if at_gate else "-"
                )
                result = self._approvals.decide(
                    approval_id,
                    decision,
                    actor=actor,
                    current_subject_hash=current_hash,
                    current_episode_version=episode.version,
                    token=token,
                    notes=notes,
                    data=data,
                )
                if result.accepted:
                    self._apply_decision(episode, result.approval, decision, actor, notes, data)
                else:
                    failure = self._decision_failure(result)
                    if result.outcome is DecisionOutcome.STALE and at_gate:
                        replacement = self._request_gate(episode)
                        failure = StaleApprovalError(str(failure), replacement.id)
        if failure is not None:
            raise failure
        return self._episodes.get(approval.episode_id)

    def reissue_approval(self, episode_id: str, actor: Actor) -> Approval:
        """Buat ulang approval (misalnya setelah kedaluwarsa) dengan subjek terbaru."""
        self._owners.require_owner(actor, "membuat ulang approval")
        with self._db.transaction():
            episode = self._episodes.get(episode_id)
            if episode.status not in state.STATUS_GATE:
                raise WorkflowError(f"episode {episode_id} tidak sedang menunggu approval")
            return self._request_gate(episode)

    def cancel(self, episode_id: str, actor: Actor, reason: str = "dibatalkan owner") -> Episode:
        self._owners.require_owner(actor, "membatalkan episode")
        with self._db.transaction():
            episode = self._episodes.get(episode_id)
            updated = self._episodes.transition(
                episode_id,
                trigger=Trigger.CANCEL,
                target=EpisodeStatus.CANCELLED,
                actor=actor,
                expected_version=episode.version,
                reason=reason,
            )
            self._approvals.supersede(episode_id, list(Gate), actor=actor, reason=reason)
            self._budget.revoke(actor=actor, reason=reason, episode_id=episode_id)
            self._queue.cancel_for_episode(episode_id)
        return updated

    def retry(self, episode_id: str, actor: Actor) -> Episode:
        self._owners.require_owner(actor, "mengulang tahap yang gagal")
        with self._db.transaction():
            episode = self._episodes.get(episode_id)
            if episode.status is not EpisodeStatus.FAILED or episode.failed_from is None:
                raise WorkflowError(f"episode {episode_id} tidak berstatus FAILED")
            updated = self._episodes.transition(
                episode_id,
                trigger=Trigger.RETRY,
                target=episode.failed_from,
                actor=actor,
                expected_version=episode.version,
            )
            self._enqueue_stage(updated)
        return updated

    # --- job ---------------------------------------------------------------

    def handlers(self) -> dict[str, Handler]:
        return {STAGE_JOB: self.handle_stage_job}

    def handle_stage_job(self, job: Job) -> JobOutcome:
        payload = job.payload
        episode = self._episodes.get(payload["episode_id"])
        if (
            episode.status.value != payload["expected_status"]
            or episode.version != payload["expected_version"]
        ):
            self._audit.record(
                actor=_SYSTEM,
                action="job.obsolete",
                entity_type="job",
                entity_id=job.id,
                episode_id=episode.id,
                data={
                    "expected_status": payload["expected_status"],
                    "actual_status": episode.status.value,
                },
            )
            return JobOutcome.OBSOLETE

        stage = PLACEHOLDER_STAGES[episode.status]
        stage(_Stage(self, episode, job, payload.get("notes")))

        next_status = state.NEXT_ON_COMPLETE[episode.status]
        updated = self._episodes.transition(
            episode.id,
            trigger=Trigger.COMPLETE,
            target=next_status,
            actor=_SYSTEM,
            expected_version=episode.version,
        )
        if next_status in state.STATUS_GATE:
            self._request_gate(updated)
        elif next_status in state.WORKING:
            self._enqueue_stage(updated)
        return JobOutcome.DONE

    def on_job_dead(self, job: Job, error: str) -> None:
        """Job gagal permanen → episode FAILED (kalau job itu masih relevan).

        Dipanggil worker di transaksi baru setelah transaksi handler di-rollback, jadi di sinilah
        alasan kegagalan (termasuk penolakan budget di dalam handler) dicatat permanen.
        """
        episode_id = job.payload.get("episode_id")
        self._audit.record(
            actor=_SYSTEM,
            action="job.dead",
            entity_type="job",
            entity_id=job.id,
            episode_id=episode_id,
            data={"type": job.type, "attempts": job.attempts, "error": error},
        )
        if not episode_id:
            return
        try:
            episode = self._episodes.get(episode_id)
        except NotFoundError:
            return
        if episode.status.value == job.payload.get(
            "expected_status"
        ) and episode.version == job.payload.get("expected_version"):
            self._episodes.transition(
                episode.id,
                trigger=Trigger.FAIL,
                target=EpisodeStatus.FAILED,
                actor=_SYSTEM,
                expected_version=episode.version,
                reason=error,
            )

    # --- internal ----------------------------------------------------------

    def _enqueue_stage(self, episode: Episode, notes: str | None = None) -> Job:
        payload: dict[str, Any] = {
            "episode_id": episode.id,
            "expected_status": episode.status.value,
            "expected_version": episode.version,
        }
        if notes:
            payload["notes"] = notes
        return self._queue.enqueue(
            STAGE_JOB,
            payload,
            episode_id=episode.id,
            idempotency_key=f"stage:{episode.id}:{episode.status.value}:{episode.version}",
        )

    def _latest(self, episode: Episode, kind: ArtifactKind) -> Artifact:
        artifact = self._artifacts.latest(episode.id, kind)
        if artifact is None:
            raise WorkflowError(f"artefak {kind.value} belum ada untuk episode {episode.id}")
        return artifact

    def _subject(self, episode: Episode, gate: Gate) -> tuple[dict[str, Any], int | None]:
        subject = {
            kind.value: {"version": a.version, "hash": a.content_hash}
            for kind in GATE_SUBJECT[gate]
            for a in [self._latest(episode, kind)]
        }
        cap: int | None = None
        if gate is Gate.TOPIC:
            cap = self._plan.limits.preproduction_cap_idr
        elif gate is Gate.COST:
            cap = int(self._latest(episode, ArtifactKind.COST_ESTIMATE).content["cap_idr"])
        return subject, cap

    def _current_subject_hash(self, episode: Episode, gate: Gate) -> str:
        subject, cap = self._subject(episode, gate)
        return compute_subject_hash(
            episode_id=episode.id, gate=gate, subject=subject, spend_cap_idr=cap
        )

    def _request_gate(self, episode: Episode) -> Approval:
        gate = state.STATUS_GATE[episode.status]
        subject, cap = self._subject(episode, gate)
        return self._approvals.request(
            episode_id=episode.id,
            gate=gate,
            episode_version=episode.version,
            subject=subject,
            spend_cap_idr=cap,
            actor=_SYSTEM,
        )

    def _validate_topic_choice(self, episode: Episode, choice: int | None) -> int:
        candidates = self._latest(episode, ArtifactKind.TOPICS).content["candidates"]
        if choice is None or not 1 <= choice <= len(candidates):
            raise WorkflowError(f"pilih topik nomor 1–{len(candidates)}")
        return choice

    def _apply_decision(
        self,
        episode: Episode,
        approval: Approval,
        decision: Decision,
        actor: Actor,
        notes: str | None,
        data: dict[str, Any],
    ) -> None:
        gate_status = state.GATE_STATUS[approval.gate]
        if decision is Decision.APPROVE:
            title = None
            if approval.gate is Gate.TOPIC:
                candidates = self._latest(episode, ArtifactKind.TOPICS).content["candidates"]
                title = candidates[data["choice"] - 1]["title"]
                self._authorize(episode, approval, AuthorizationKind.PREPRODUCTION, actor)
            elif approval.gate is Gate.COST:
                self._authorize(episode, approval, AuthorizationKind.PRODUCTION, actor)
            updated = self._episodes.transition(
                episode.id,
                trigger=Trigger.APPROVE,
                target=state.NEXT_ON_APPROVE[gate_status],
                actor=actor,
                expected_version=episode.version,
                title=title,
            )
            self._enqueue_stage(updated)
        elif decision is Decision.REJECT:
            self._episodes.transition(
                episode.id,
                trigger=Trigger.REJECT,
                target=EpisodeStatus.REJECTED,
                actor=actor,
                expected_version=episode.version,
                reason=notes,
            )
            self._budget.revoke(actor=actor, reason="episode ditolak", episode_id=episode.id)
            self._queue.cancel_for_episode(episode.id)
        else:
            target = EpisodeStatus(data["revise_to"])
            invalidated = self._approvals.supersede(
                episode.id,
                state.gates_invalidated_by_revision(target),
                actor=actor,
                reason=f"revisi ke {target.value}",
            )
            self._budget.revoke(
                actor=actor,
                reason=f"approval digantikan revisi ke {target.value}",
                approval_ids=[a.id for a in invalidated],
            )
            updated = self._episodes.transition(
                episode.id,
                trigger=Trigger.REVISE,
                target=target,
                actor=actor,
                expected_version=episode.version,
                reason=notes,
            )
            self._enqueue_stage(updated, notes=notes)

    def _authorize(
        self, episode: Episode, approval: Approval, kind: AuthorizationKind, actor: Actor
    ) -> None:
        if approval.spend_cap_idr is None:
            raise WorkflowError(f"approval {approval.gate.value} tidak punya batas belanja")
        self._budget.authorize_episode(
            episode_id=episode.id,
            kind=kind,
            approval_id=approval.id,
            max_idr=approval.spend_cap_idr,
            actor=actor,
        )

    def _decision_failure(self, result: DecisionResult) -> Exception:
        message = result.message
        match result.outcome:
            case DecisionOutcome.NOT_AUTHORIZED:
                return NotAuthorizedError(message)
            case DecisionOutcome.NOT_PENDING:
                return ApprovalNotPendingError(message)
            case DecisionOutcome.EXPIRED:
                return ApprovalExpiredError(message + "; gunakan `approval reissue`")
            case DecisionOutcome.INVALID_TOKEN:
                return InvalidApprovalTokenError(message)
            case _:
                return StaleApprovalError(message)

    def _spend(
        self,
        episode: Episode,
        job: Job,
        label: str,
        *,
        authorization: AuthorizationKind,
        usd_micros: int,
        price_ref: str,
        category_key: str,
        meta: dict[str, Any],
    ) -> None:
        if authorization is AuthorizationKind.OPERATIONAL:
            auth = self._budget.operational_authorization()
        else:
            auth = self._budget.episode_authorization(episode.id, authorization)
        if auth is None:
            raise BudgetExceededError(f"tidak ada otorisasi {authorization.value} yang aktif")
        self._guard.spend(
            SpendRequest(
                idempotency_key=f"{job.idempotency_key}:{label}",
                category=self._pricing.price(category_key).category,
                source=Source.STUDIO,
                purpose=label,
                mode=self.MODE,
                authorization_id=auth.id,
                usd_micros=usd_micros,
                price_ref=price_ref,
                episode_id=episode.id,
                meta=meta,
            )
        )
