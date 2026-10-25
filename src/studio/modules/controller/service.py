"""Studio Controller: fasad aplikasi untuk antarmuka percakapan (Telegram sekarang, Hermes nanti).

Antarmuka TIDAK menyentuh modul domain langsung. Semua bacaan dan perintah lewat sini, dan
setiap metode memeriksa ulang bahwa actor adalah owner di allowlist — bukan hanya di bot.
Perubahan state selalu lewat `WorkflowService` (state machine, approval version-aware,
BudgetGuard); controller tidak punya jalur pintas.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from studio.infra.db import Database
from studio.infra.jobs import JobQueue, JobStatus
from studio.modules.approvals import (
    Approval,
    ApprovalExpiredError,
    ApprovalNotPendingError,
    ApprovalService,
    ApprovalStatus,
    Decision,
    InvalidApprovalTokenError,
    StaleApprovalError,
)
from studio.modules.artifacts import ArtifactKind, ArtifactStore
from studio.modules.audit import AuditLog
from studio.modules.budget import (
    AuthorizationKind,
    BudgetPlan,
    BudgetService,
    Category,
    CostEstimate,
    Mode,
)
from studio.modules.calls import MeteredCaller
from studio.modules.controller.actions import ActionCheck, ActionCode, ActionCodes
from studio.modules.controller.views import (
    ActionReply,
    ApprovalCard,
    ApprovalSummary,
    BudgetDashboard,
    CategoryLine,
    ClaimSources,
    ConfirmCard,
    EpisodeCost,
    EpisodeDetail,
    EpisodeFilter,
    EpisodeSummary,
    Outcome,
    Page,
    ProductionItem,
    ResearchView,
    ReviseCard,
    ScriptView,
    StudioSettingsView,
)
from studio.modules.episodes import (
    Category as EpisodeCategory,
)
from studio.modules.episodes import (
    DocumentaryFormat,
    Episode,
    EpisodeService,
    EpisodeStatus,
    state,
)
from studio.modules.research import (
    EvidenceRecord,
    ResearchBrief,
    ResearchQualityReport,
    TopicCandidate,
)
from studio.modules.scripting import DocumentaryScript, EditorialReport, ScriptingConfig
from studio.modules.workflow import WorkflowService
from studio.shared.actors import Actor, OwnerPolicy
from studio.shared.clock import Clock
from studio.shared.errors import NotAuthorizedError, NotFoundError, StudioError
from studio.shared.gates import Gate

MAX_NOTES_CHARS = 1000
SIMULATED_GATES = frozenset({Gate.COST, Gate.FINAL})  # G2/G3 masih placeholder Fase 1–2


class NotReadyError(StudioError):
    """Artefak yang diminta belum dibuat (episode belum sampai tahap itu)."""


@dataclass(frozen=True)
class ControllerConfig:
    action_ttl: timedelta = timedelta(hours=6)
    approval_ttl_hours: int = 72
    paid_providers_enabled: bool = False
    notification_recipients: tuple[str, ...] = ()


class StudioController:
    def __init__(
        self,
        *,
        db: Database,
        clock: Clock,
        audit: AuditLog,
        owners: OwnerPolicy,
        episodes: EpisodeService,
        artifacts: ArtifactStore,
        approvals: ApprovalService,
        budget: BudgetService,
        plan: BudgetPlan,
        queue: JobQueue,
        calls: MeteredCaller,
        workflow: WorkflowService,
        scripting: ScriptingConfig,
        actions: ActionCodes,
        config: ControllerConfig,
    ) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit
        self._owners = owners
        self._episodes = episodes
        self._artifacts = artifacts
        self._approvals = approvals
        self._budget = budget
        self._plan = plan
        self._queue = queue
        self._calls = calls
        self._workflow = workflow
        self._scripting = scripting
        self._actions = actions
        self._config = config

    # --- identitas ---------------------------------------------------------------

    @staticmethod
    def actor_for(channel: str, external_id: int | str) -> Actor:
        """Identitas dari ID numerik kanal (Telegram: `from_user.id`), bukan username."""
        return Actor.owner(f"{channel}:{external_id}")

    def is_owner(self, actor: Actor) -> bool:
        return self._owners.is_owner(actor)

    def _owner(self, actor: Actor, what: str) -> None:
        self._owners.require_owner(actor, what)

    @property
    def scripting(self) -> ScriptingConfig:
        return self._scripting

    # --- bacaan ------------------------------------------------------------------

    def episode(self, actor: Actor, episode_id: str) -> Episode:
        self._owner(actor, "melihat episode")
        return self._episodes.get(episode_id)

    def episode_detail(self, actor: Actor, episode_id: str) -> EpisodeDetail:
        episode = self.episode(actor, episode_id)
        ledger = self._budget.ledger(episode_id=episode_id)
        return EpisodeDetail(
            episode=episode,
            pending=self._approvals.pending(episode_id),
            artifact_kinds=[k.value for k in self._artifacts.all_latest(episode_id)],
            spent_simulated_idr=_spent(ledger, Mode.SIMULATED),
            spent_real_idr=_spent(ledger, Mode.REAL),
            jobs=self._queue.list_jobs(episode_id=episode_id),
        )

    def list_episodes(
        self,
        actor: Actor,
        flt: EpisodeFilter,
        *,
        page: int = 0,
        per_page: int = 5,
        with_artifact: ArtifactKind | None = None,
        gate: Gate | None = None,
    ) -> Page[EpisodeSummary]:
        self._owner(actor, "melihat daftar episode")
        pending: dict[str, Approval] = {a.episode_id: a for a in self._approvals.pending()}
        selected = []
        for episode in reversed(self._episodes.list_episodes()):
            keep = {
                EpisodeFilter.ALL: True,
                EpisodeFilter.ACTIVE: episode.status not in state.TERMINAL,
                EpisodeFilter.AWAITING: episode.id in pending,
                EpisodeFilter.WORKING: episode.status in state.WORKING,
            }[flt]
            if keep and gate is not None:
                keep = episode.id in pending and pending[episode.id].gate is gate
            if keep and with_artifact is not None:
                keep = self._artifacts.latest(episode.id, with_artifact) is not None
            if keep:
                selected.append(EpisodeSummary(episode, pending.get(episode.id)))
        return Page.of(selected, page, per_page)

    def find_episodes(self, actor: Actor, query: str) -> list[Episode]:
        """Cari episode dari ID (lengkap/akhiran ≥ 4 karakter), judul, atau ide."""
        self._owner(actor, "mencari episode")
        needle = query.strip().lower()
        if len(needle) < 3:
            return []
        found = []
        for episode in reversed(self._episodes.list_episodes()):
            eid = episode.id.lower()
            haystack = f"{episode.title or ''} {episode.idea or ''}".lower()
            if eid == needle or (len(needle) >= 4 and eid.endswith(needle)) or needle in haystack:
                found.append(episode)
        return found

    def topics(self, actor: Actor, episode_id: str) -> list[TopicCandidate]:
        episode = self.episode(actor, episode_id)
        artifact = self._artifacts.latest(episode.id, ArtifactKind.TOPICS)
        if artifact is None:
            raise NotReadyError("kandidat topik belum tersedia; discovery masih berjalan")
        return [TopicCandidate.model_validate(c) for c in artifact.content["candidates"]]

    def research(self, actor: Actor, episode_id: str) -> ResearchView:
        episode = self.episode(actor, episode_id)
        artifact = self._artifacts.latest(episode.id, ArtifactKind.FACTCHECK)
        if artifact is None:
            raise NotReadyError(
                f"ResearchBrief belum tersedia (status episode: {episode.status.value})"
            )
        return ResearchView(
            episode=episode,
            brief=ResearchBrief.model_validate(artifact.content["brief"]),
            report=ResearchQualityReport.model_validate(artifact.content["quality_report"]),
        )

    def script(self, actor: Actor, episode_id: str) -> ScriptView:
        episode = self.episode(actor, episode_id)
        artifact = self._artifacts.latest(episode.id, ArtifactKind.SCRIPT)
        if artifact is None:
            raise NotReadyError(f"naskah belum tersedia (status episode: {episode.status.value})")
        report = self._artifacts.latest(episode.id, ArtifactKind.EDITORIAL_REPORT)
        return ScriptView(
            episode=episode,
            script=DocumentaryScript.model_validate(
                {k: v for k, v in artifact.content.items() if k != "llm_calls"}
            ),
            report=EditorialReport.model_validate(report.content) if report else None,
        )

    def claim_sources(self, actor: Actor, episode_id: str, claim_id: str) -> ClaimSources:
        view = self.research(actor, episode_id)
        claim = view.brief.claim(claim_id)
        if claim is None:
            raise NotFoundError(f"klaim {claim_id} tidak ada di ResearchBrief episode ini")
        artifact = self._artifacts.latest(episode_id, ArtifactKind.FACTCHECK)
        evidence_rows = artifact.content.get("evidence", []) if artifact else []
        evidence = [
            EvidenceRecord.model_validate(e)
            for e in evidence_rows
            if e["id"] in claim.evidence_ids and e.get("verified")
        ]
        wanted = {*claim.supporting_source_ids, *claim.contradicting_source_ids}
        return ClaimSources(
            episode=view.episode,
            claim=claim,
            sources=[s for s in view.brief.sources if s.id in wanted],
            evidence=evidence,
        )

    def pending_approvals(self, actor: Actor) -> list[ApprovalSummary]:
        self._owner(actor, "melihat approval")
        now = self._clock.now()
        return [
            ApprovalSummary(a, self._episodes.get(a.episode_id), expired=now >= a.expires_at)
            for a in self._approvals.pending()
        ]

    def production_status(self, actor: Actor) -> list[ProductionItem]:
        self._owner(actor, "melihat status produksi")
        items = []
        for episode in reversed(self._episodes.list_episodes()):
            if episode.status in state.WORKING or episode.status is EpisodeStatus.FAILED:
                jobs = [
                    j
                    for j in self._queue.list_jobs(episode_id=episode.id)
                    if j.status in (JobStatus.QUEUED, JobStatus.RUNNING)
                ]
                items.append(ProductionItem(episode, jobs))
        return items

    def budget_dashboard(self, actor: Actor) -> BudgetDashboard:
        self._owner(actor, "melihat anggaran")
        period = self._budget.period()
        simulated = self._budget.status(Mode.SIMULATED)
        real = self._budget.status(Mode.REAL)
        fx = period.fx_rate if period else self._plan.fx_rate
        lines = []
        for category in (Category.OPENAI, Category.HIGGSFIELD, Category.TTS):
            sim = next(c for c in simulated.categories if c.category is category)
            rl = next(c for c in real.categories if c.category is category)
            lines.append(
                CategoryLine(
                    name=category.value,
                    allocation_idr=sim.allocation_idr,
                    used_simulated_idr=sim.used_idr,
                    used_real_idr=rl.used_idr,
                    remaining_idr=sim.remaining_idr,
                    spendable=True,
                )
            )
        reserve = (
            int(period.plan["allocations_idr"]["reserve"])
            if period
            else self._plan.allocations_idr.reserve
        )
        lines.append(CategoryLine("reserve", reserve, 0, 0, reserve, spendable=False))
        return BudgetDashboard(
            period=simulated.period,
            active=simulated.active,
            monthly_budget_idr=self._plan.monthly_budget_idr,
            vps_usd=str(self._plan.vps.planned_usd),
            vps_idr=self._plan.vps_cost_idr,
            fx_usd_idr=fx.as_text,
            fx_as_of=fx.as_of.isoformat(),
            lines=lines,
            simulated=simulated,
            real=real,
            paid_providers_enabled=self._config.paid_providers_enabled,
            by_source_simulated=dict(simulated.by_source),
        )

    def episode_cost(self, actor: Actor, episode_id: str) -> EpisodeCost:
        episode = self.episode(actor, episode_id)
        ledger = self._budget.ledger(episode_id=episode_id)
        auth = self._budget.episode_authorization(episode_id, AuthorizationKind.PREPRODUCTION)
        estimate = self._artifacts.latest(episode_id, ArtifactKind.COST_ESTIMATE)
        return EpisodeCost(
            episode=episode,
            spent_simulated_idr=_spent(ledger, Mode.SIMULATED),
            spent_real_idr=_spent(ledger, Mode.REAL),
            preproduction_cap_idr=(
                auth.max_idr if auth else self._plan.limits.preproduction_cap_idr
            ),
            preproduction_used_idr=(
                self._budget.authorization_used(auth.id, Mode.SIMULATED) if auth else 0
            ),
            production_estimate_idr=int(estimate.content["total_idr"]) if estimate else None,
            production_cap_idr=int(estimate.content["cap_idr"]) if estimate else None,
            llm_calls=len(self._calls.calls_for_episode(episode_id)),
            estimate=CostEstimate.from_dict(estimate.content) if estimate else None,
            remaining_by_category={
                c.category.value: c.remaining_idr
                for c in self._budget.status(Mode.SIMULATED).categories
            },
        )

    def settings_view(self, actor: Actor) -> StudioSettingsView:
        self._owner(actor, "melihat pengaturan")
        return StudioSettingsView(
            owner_label=actor.label,
            approval_ttl_hours=self._config.approval_ttl_hours,
            action_ttl_minutes=int(self._config.action_ttl.total_seconds() // 60),
            words_per_minute=self._scripting.narration.words_per_minute,
            formats=dict(self._scripting.formats),
            paid_providers_enabled=self._config.paid_providers_enabled,
            notification_recipients=len(self._config.notification_recipients),
        )

    def notification_recipients(self) -> tuple[str, ...]:
        return self._config.notification_recipients

    # --- kartu & konfirmasi (menerbitkan kode sekali pakai) ------------------------

    def approval_card(self, actor: Actor, approval_id: str) -> ApprovalCard:
        """Kartu approval dengan tombol sekali pakai. Kartu lama untuk approval yang sama
        (milik actor ini) langsung hangus."""
        self._owner(actor, "membuka kartu approval")
        approval = self._approvals.get(approval_id)
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalNotPendingError(f"approval sudah berstatus {approval.status.value}")
        if self._clock.now() >= approval.expires_at:
            raise ApprovalExpiredError("approval sudah kedaluwarsa; terbitkan ulang dulu")
        episode = self._episodes.get(approval.episode_id)
        topics: list[TopicCandidate] = []
        base = {"approval_id": approval.id, "episode_id": episode.id}
        actions: dict[str, tuple[str, dict[str, Any]]] = {}
        if approval.gate is Gate.TOPIC:
            topics = self.topics(actor, episode.id)
            for number in range(1, len(topics) + 1):
                actions[f"choose:{number}"] = ("approval.approve", {**base, "choice": number})
        else:
            actions["approve"] = ("approval.approve", base)
        actions["reject"] = ("approval.reject", base)
        actions["revise"] = ("approval.revise_menu", base)
        with self._db.transaction():
            self._actions.supersede("approval_id", approval.id, actor=actor)
            issued = self._actions.issue(
                actor, actions, ttl=self._config.action_ttl, expires_at=approval.expires_at
            )
        return ApprovalCard(
            approval=approval,
            episode=episode,
            codes=issued.codes,
            expires_at=issued.expires_at,
            topics=topics,
            simulated=approval.gate in SIMULATED_GATES,
            editorial=self._editorial_summary(actor, episode)
            if approval.gate is Gate.EDITORIAL
            else "",
        )

    def _editorial_summary(self, actor: Actor, episode: Episode) -> str:
        try:
            view = self.script(actor, episode.id)
        except NotReadyError:
            return ""
        report = view.report
        if report is None:
            verdict = "belum diperiksa"
        elif report.overridden:
            verdict = "OVERRIDE OWNER (tidak lulus, dilanjutkan dengan alasan tercatat)"
        else:
            verdict = "LULUS" if report.passed else "TIDAK LULUS"
        warnings = len(report.issues) if report else 0
        return (
            f"Naskah: {view.script.title} · {view.script.estimated_duration_s:.1f} dtk "
            f"(target {view.script.target_duration_s}) · editorial gate {verdict} · "
            f"{warnings} catatan"
        )

    def _confirm(
        self,
        actor: Actor,
        action: str,
        payload: dict[str, Any],
        summary: str,
        episode: Episode | None = None,
    ) -> ConfirmCard:
        issued = self._actions.issue(
            actor,
            {"yes": (action, payload), "no": ("dismiss", {})},
            ttl=self._config.action_ttl,
        )
        return ConfirmCard(action=action, summary=summary, codes=issued.codes, episode=episode)

    def confirm_create(
        self,
        actor: Actor,
        *,
        format: DocumentaryFormat,
        category: EpisodeCategory,
        idea: str | None,
        target_duration_s: int | None = None,
    ) -> ConfirmCard:
        self._owner(actor, "membuat episode")
        spec = self._scripting.format_spec(format.value)
        duration = spec.default_s if target_duration_s is None else target_duration_s
        if not spec.contains(duration):
            raise StudioError(
                f"durasi {duration} detik di luar rentang {spec.label} ({spec.min_s}–{spec.max_s})"
            )
        idea = (idea or "").strip()[:200] or None
        summary = f"{spec.label} · {duration} detik · kategori {category.value}" + (
            f" · ide: {idea}" if idea else ""
        )
        return self._confirm(
            actor,
            "episode.create",
            {
                "format": format.value,
                "category": category.value,
                "idea": idea,
                "duration": duration,
            },
            summary,
        )

    def confirm_script_revision(self, actor: Actor, episode_id: str, notes: str) -> ConfirmCard:
        """Siapkan revisi naskah lewat jalur workflow yang sah (bukan edit langsung).

        - Menunggu G1 → keputusan REVISE ke SCRIPTING: approval G1 (dan setelahnya) digantikan,
          versi episode naik, naskah ditulis ulang dan diperiksa editorial gate lagi.
        - Gagal editorial gate → RETRY ke SCRIPTING dengan catatan.
        """
        episode = self.episode(actor, episode_id)
        notes = _clean_notes(notes)
        if episode.status is EpisodeStatus.AWAITING_EDITORIAL:
            approval = next(
                (a for a in self._approvals.pending(episode.id) if a.gate is Gate.EDITORIAL), None
            )
            if approval is None:
                raise StudioError("tidak ada approval G1 yang menunggu untuk episode ini")
            payload: dict[str, Any] = {
                "mode": "gate",
                "episode_id": episode.id,
                "approval_id": approval.id,
                "notes": notes,
            }
            effect = "approval G1 yang menunggu akan dibatalkan, naskah ditulis ulang"
        elif (
            episode.status is EpisodeStatus.FAILED
            and episode.failed_from is EpisodeStatus.SCRIPTING
        ):
            payload = {
                "mode": "retry",
                "episode_id": episode.id,
                "expected_version": episode.version,
                "notes": notes,
            }
            effect = "tahap naskah diulang dengan catatan ini"
        else:
            raise StudioError(
                "naskah hanya bisa direvisi saat menunggu G1 atau setelah gagal editorial gate "
                f"(status sekarang: {episode.status.value})"
            )
        summary = f"Revisi naskah — {effect}, lalu diperiksa editorial gate lagi.\nCatatan: {notes}"
        return self._confirm(actor, "episode.revise_script", payload, summary, episode)

    def confirm_retry(self, actor: Actor, episode_id: str) -> ConfirmCard:
        episode = self.episode(actor, episode_id)
        if episode.status is not EpisodeStatus.FAILED or episode.failed_from is None:
            raise StudioError(f"episode tidak berstatus FAILED (status: {episode.status.value})")
        return self._confirm(
            actor,
            "episode.retry",
            {"episode_id": episode.id, "expected_version": episode.version},
            f"Ulang tahap {episode.failed_from.value}.",
            episode,
        )

    def confirm_cancel(self, actor: Actor, episode_id: str) -> ConfirmCard:
        episode = self.episode(actor, episode_id)
        if episode.status in state.TERMINAL:
            raise StudioError(f"episode sudah ditutup ({episode.status.value})")
        return self._confirm(
            actor,
            "episode.cancel",
            {"episode_id": episode.id},
            "Batalkan episode. Approval & otorisasi belanjanya dicabut.",
            episode,
        )

    def confirm_reissue(self, actor: Actor, episode_id: str) -> ConfirmCard:
        episode = self.episode(actor, episode_id)
        return self._confirm(
            actor,
            "approval.reissue",
            {"episode_id": episode.id},
            "Terbitkan ulang approval yang kedaluwarsa (subjek terbaru).",
            episode,
        )

    def confirm_activate_budget(self, actor: Actor) -> ConfirmCard:
        self._owner(actor, "mengaktifkan periode anggaran")
        period = self._budget.current_period()
        return self._confirm(
            actor,
            "budget.activate",
            {"period": period},
            f"Aktifkan periode anggaran {period} sesuai config/budget.yaml (nominal tidak diubah).",
        )

    # --- eksekusi tombol ------------------------------------------------------------

    def press(self, actor: Actor, code: str) -> ActionReply:
        """Eksekusi tombol. Kode dihanguskan dulu (commit), baru aksinya dijalankan, supaya
        klik ganda tidak pernah mengeksekusi dua kali."""
        self._owner(actor, "menekan tombol aksi")
        result = self._actions.consume(code, actor)
        if not result.ok or result.code is None:
            return ActionReply(Outcome.REFUSED, _REFUSAL[result.check])
        return self._execute(actor, result.code, notes=None)

    def submit_notes(self, actor: Actor, action_id: str, notes: str) -> ActionReply:
        """Langkah lanjutan: catatan revisi diketik setelah owner memilih target revisi."""
        self._owner(actor, "mengirim catatan revisi")
        cleaned = _clean_notes(notes)
        result = self._actions.consume_by_id(action_id, actor)
        if not result.ok or result.code is None:
            return ActionReply(Outcome.REFUSED, _REFUSAL[result.check])
        return self._execute(actor, result.code, notes=cleaned)

    def _execute(self, actor: Actor, code: ActionCode, *, notes: str | None) -> ActionReply:
        handler = self._handlers().get(code.action)
        if handler is None:
            return ActionReply(Outcome.REFUSED, "Aksi tombol tidak dikenal.")
        self._audit.record(
            actor=actor,
            action="ui.action_used",
            entity_type="ui_action",
            entity_id=code.id,
            episode_id=code.payload.get("episode_id"),
            data={"action": code.action, **{k: v for k, v in code.payload.items() if k != "notes"}},
        )
        try:
            return handler(actor, code.payload, notes)
        except StaleApprovalError as exc:
            replacement = self._approvals.get(exc.replacement_id) if exc.replacement_id else None
            return ActionReply(
                Outcome.STALE,
                "Konten sudah berubah sejak kartu ini dibuat. Kartu lama tidak berlaku.",
                approval=replacement,
            )
        except ApprovalExpiredError:
            episode = self._episodes.get(str(code.payload["episode_id"]))
            return ActionReply(Outcome.EXPIRED, "Approval sudah kedaluwarsa.", episode=episode)
        except ApprovalNotPendingError:
            return ActionReply(Outcome.REFUSED, "Approval ini sudah diputuskan sebelumnya.")
        except InvalidApprovalTokenError:
            return ActionReply(Outcome.REFUSED, "Kartu ini sudah diganti kartu yang lebih baru.")
        except NotAuthorizedError:
            return ActionReply(Outcome.REFUSED, "Akun ini tidak berhak melakukan aksi tersebut.")
        except StudioError as exc:
            return ActionReply(Outcome.FAILED, _sentence(str(exc)))

    def _handlers(
        self,
    ) -> dict[str, Callable[[Actor, dict[str, Any], str | None], ActionReply]]:
        return {
            "approval.approve": self._do_approve,
            "approval.reject": self._do_reject,
            "approval.revise_menu": self._do_revise_menu,
            "approval.revise_target": self._do_revise_target,
            "approval.revise_submit": self._do_revise_submit,
            "approval.card": self._do_card,
            "approval.reissue": self._do_reissue,
            "episode.create": self._do_create,
            "episode.revise_script": self._do_revise_script,
            "episode.retry": self._do_retry,
            "episode.cancel": self._do_cancel,
            "budget.activate": self._do_activate,
            "dismiss": lambda actor, payload, notes: ActionReply(Outcome.DISMISSED, "Dibatalkan."),
        }

    def _decided(self, episode: Episode, message: str) -> ActionReply:
        return ActionReply(Outcome.DONE, message, episode=episode)

    def _do_approve(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        choice = payload.get("choice")
        episode = self._workflow.decide(
            str(payload["approval_id"]),
            Decision.APPROVE,
            actor=actor,
            choice=int(choice) if choice is not None else None,
        )
        text = f"Disetujui. Episode → {episode.status.value}."
        if episode.title and choice is not None:
            text = f"Topik dipilih: {episode.title}. Riset dimulai."
        return self._decided(episode, text)

    def _do_reject(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        episode = self._workflow.decide(
            str(payload["approval_id"]), Decision.REJECT, actor=actor, notes="ditolak owner"
        )
        return self._decided(episode, "Ditolak. Episode ditutup dan otorisasinya dicabut.")

    def _do_revise_menu(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        approval = self._approvals.get(str(payload["approval_id"]))
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalNotPendingError("approval sudah diputuskan")
        episode = self._episodes.get(approval.episode_id)
        targets = sorted(
            state.REVISION_TARGETS[state.GATE_STATUS[approval.gate]], key=state.position
        )
        actions: dict[str, tuple[str, dict[str, Any]]] = {
            f"to:{t.value}": (
                "approval.revise_target",
                {**payload, "revise_to": t.value},
            )
            for t in targets
        }
        actions["back"] = ("approval.card", payload)
        issued = self._actions.issue(
            actor, actions, ttl=self._config.action_ttl, expires_at=approval.expires_at
        )
        card = ReviseCard(approval, episode, [t.value for t in targets], issued.codes)
        return ActionReply(Outcome.REVISE_MENU, "Pilih tahap yang direvisi.", revise=card)

    def _do_revise_target(
        self, actor: Actor, payload: dict[str, Any], _: str | None
    ) -> ActionReply:
        approval = self._approvals.get(str(payload["approval_id"]))
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalNotPendingError("approval sudah diputuskan")
        issued = self._actions.issue(
            actor,
            {"submit": ("approval.revise_submit", payload)},
            ttl=self._config.action_ttl,
            expires_at=approval.expires_at,
        )
        return ActionReply(
            Outcome.NEEDS_NOTES,
            "Tulis catatan revisi (apa yang perlu diubah).",
            episode=self._episodes.get(approval.episode_id),
            pending_action_id=issued.ids["submit"],
            revise_to=str(payload["revise_to"]),
        )

    def _do_revise_submit(
        self, actor: Actor, payload: dict[str, Any], notes: str | None
    ) -> ActionReply:
        if not notes:
            raise StudioError("catatan revisi wajib diisi")
        target = EpisodeStatus(str(payload["revise_to"]))
        episode = self._workflow.decide(
            str(payload["approval_id"]),
            Decision.REVISE,
            actor=actor,
            notes=notes,
            revise_to=target,
        )
        return self._decided(episode, f"Revisi diterima. Episode kembali ke {target.value}.")

    def _do_card(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        approval = self._approvals.get(str(payload["approval_id"]))
        return ActionReply(Outcome.DONE, "Kartu approval.", approval=approval)

    def _do_reissue(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        approval = self._workflow.reissue_approval(str(payload["episode_id"]), actor)
        return ActionReply(Outcome.DONE, "Approval diterbitkan ulang.", approval=approval)

    def _do_create(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        if self._budget.period() is None:
            raise StudioError(
                "periode anggaran bulan ini belum diaktifkan; buka menu Budget → Aktifkan periode"
            )
        with self._db.transaction():
            created = self._workflow.create_episode(
                category=EpisodeCategory(str(payload["category"])),
                target_duration_s=int(payload["duration"]),
                idea=payload.get("idea"),
                actor=actor,
                format=DocumentaryFormat(str(payload["format"])),
            )
            episode = self._workflow.start(created.id, actor)
        return self._decided(episode, "Episode dibuat. Studio sedang mencari kandidat topik…")

    def _do_revise_script(
        self, actor: Actor, payload: dict[str, Any], _: str | None
    ) -> ActionReply:
        notes = str(payload["notes"])
        if payload["mode"] == "gate":
            episode = self._workflow.decide(
                str(payload["approval_id"]),
                Decision.REVISE,
                actor=actor,
                notes=notes,
                revise_to=EpisodeStatus.SCRIPTING,
            )
        else:
            episode = self._workflow.retry(
                str(payload["episode_id"]),
                actor,
                notes=notes,
                expected_version=int(payload["expected_version"]),
            )
        return self._decided(
            episode, "Revisi naskah dikirim. Naskah ditulis ulang lalu dicek ulang."
        )

    def _do_retry(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        episode = self._workflow.retry(
            str(payload["episode_id"]), actor, expected_version=int(payload["expected_version"])
        )
        return self._decided(episode, f"Tahap {episode.status.value} diulang.")

    def _do_cancel(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        episode = self._workflow.cancel(str(payload["episode_id"]), actor, "dibatalkan lewat chat")
        return self._decided(episode, "Episode dibatalkan.")

    def _do_activate(self, actor: Actor, payload: dict[str, Any], _: str | None) -> ActionReply:
        period = self._budget.activate_period(actor, str(payload["period"]))
        return ActionReply(
            Outcome.DONE, f"Periode {period.period} aktif (kurs {period.fx_usd_idr})."
        )


_REFUSAL: dict[ActionCheck, str] = {
    ActionCheck.OK: "",
    ActionCheck.UNKNOWN: "Tombol ini tidak dikenal atau sudah dibersihkan. Buka menu lagi.",
    ActionCheck.WRONG_ACTOR: "Tombol ini bukan untuk akun Anda.",
    ActionCheck.USED: "Tombol ini sudah dipakai atau sudah diganti kartu yang lebih baru.",
    ActionCheck.EXPIRED: "Tombol ini sudah kedaluwarsa. Buka menu Approval untuk kartu baru.",
}


def _spent(ledger: list[Any], mode: Mode) -> int:
    return sum(
        (e.actual_idr if e.actual_idr is not None else e.reserved_idr)
        for e in ledger
        if e.mode is mode and e.status.value != "released"
    )


def _clean_notes(notes: str) -> str:
    cleaned = " ".join(notes.split())
    if len(cleaned) < 3:
        raise StudioError("catatan revisi terlalu pendek")
    return cleaned[:MAX_NOTES_CHARS]


def _sentence(message: str) -> str:
    message = message.strip()
    if not message:
        return "Aksi ditolak."
    return message[0].upper() + message[1:] + ("" if message.endswith(".") else ".")
