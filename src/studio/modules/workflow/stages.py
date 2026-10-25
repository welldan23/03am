"""Tahap konten Fase 2 yang memanggil provider (di LUAR transaksi database).

Setiap fungsi tahap mengembalikan `StageOutput` (artefak + alasan gagal bila ada). Output
baru diterima oleh `WorkflowService` di dalam `Lease.finish`, setelah fencing token dan versi
episode divalidasi ulang.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from studio.infra.jobs import Job, Lease
from studio.modules.approvals import ApprovalService
from studio.modules.artifacts import Artifact, ArtifactKind, ArtifactStore
from studio.modules.budget import AuthorizationKind
from studio.modules.calls import CallScope
from studio.modules.episodes import Episode
from studio.modules.research import (
    ResearchBrief,
    ResearchDossier,
    ResearchEngine,
    TopicCandidate,
)
from studio.modules.scripting import EditorialReport, ScriptEngine
from studio.shared.errors import StudioError
from studio.shared.gates import Gate


class StageError(StudioError):
    pass


@dataclass(frozen=True)
class StageOutput:
    artifacts: list[tuple[ArtifactKind, dict[str, Any]]] = field(default_factory=list)
    fail_reason: str | None = None


@dataclass(frozen=True)
class StageRun:
    job: Job
    lease: Lease
    episode: Episode
    notes: str | None
    payload: dict[str, Any]

    def scope(self, authorization: AuthorizationKind) -> CallScope:
        return CallScope(
            lease=self.lease,
            key_prefix=self.job.idempotency_key,
            episode_id=self.episode.id,
            authorization=authorization,
        )


class ContentStages:
    def __init__(
        self,
        *,
        artifacts: ArtifactStore,
        approvals: ApprovalService,
        research: ResearchEngine,
        scripts: ScriptEngine,
    ) -> None:
        self._artifacts = artifacts
        self._approvals = approvals
        self._research = research
        self._scripts = scripts

    def _latest(self, episode: Episode, kind: ArtifactKind) -> Artifact:
        artifact = self._artifacts.latest(episode.id, kind)
        if artifact is None:
            raise StageError(f"artefak {kind.value} belum ada untuk episode {episode.id}")
        return artifact

    def _dossier(self, episode: Episode) -> ResearchDossier:
        return ResearchDossier.model_validate(
            self._latest(episode, ArtifactKind.RESEARCH).content["dossier"]
        )

    def _brief(self, episode: Episode) -> ResearchBrief:
        return ResearchBrief.model_validate(
            self._latest(episode, ArtifactKind.FACTCHECK).content["brief"]
        )

    def selected_topic(self, episode: Episode) -> TopicCandidate:
        approval = self._approvals.latest_approved(episode.id, Gate.TOPIC)
        if approval is None or "choice" not in approval.decision_data:
            raise StageError("topik belum dipilih owner (G0)")
        candidates = self._latest(episode, ArtifactKind.TOPICS).content["candidates"]
        return TopicCandidate.model_validate(candidates[int(approval.decision_data["choice"]) - 1])

    # --- tahap ---------------------------------------------------------------

    def discover(self, run: StageRun) -> StageOutput:
        result = self._research.discover(
            run.scope(AuthorizationKind.OPERATIONAL),
            episode_category=run.episode.category.value,
            idea=run.episode.idea,
            notes=run.notes,
        )
        content = {
            "candidates": [c.model_dump(mode="json") for c in result.value.candidates],
            "notes": run.notes,
            "llm_calls": result.llm_calls,
        }
        return StageOutput([(ArtifactKind.TOPICS, content)])

    def research(self, run: StageRun) -> StageOutput:
        topic = self.selected_topic(run.episode)
        result = self._research.research(
            run.scope(AuthorizationKind.PREPRODUCTION), topic, notes=run.notes
        )
        content = {
            "dossier": result.value.model_dump(mode="json"),
            "notes": run.notes,
            "llm_calls": result.llm_calls,
        }
        return StageOutput([(ArtifactKind.RESEARCH, content)])

    def fact_check(self, run: StageRun) -> StageOutput:
        checked = self._research.fact_check(self._dossier(run.episode))
        content = {
            "brief": checked.brief.model_dump(mode="json"),
            "quality_report": checked.report.model_dump(mode="json"),
            "evidence": [e.model_dump(mode="json") for e in checked.evidence],
            "claims": [c.model_dump(mode="json") for c in checked.claims],
        }
        fail = None
        if not checked.report.passed:
            blocking = [i.message for i in checked.report.issues if i.severity.value == "blocking"]
            fail = "riset belum memenuhi standar 03:AM: " + "; ".join(blocking)
        return StageOutput([(ArtifactKind.FACTCHECK, content)], fail)

    def script(self, run: StageRun) -> StageOutput:
        if run.payload.get("editorial_override"):
            return self._apply_override(run)
        config = self._scripts.config
        format_name = (
            run.episode.format.value
            if run.episode.format
            else config.format_for_duration(run.episode.target_duration_s)
        )
        result = self._scripts.write(
            run.scope(AuthorizationKind.PREPRODUCTION),
            self._brief(run.episode),
            self._dossier(run.episode).source_texts,
            format_name=format_name,
            target_duration_s=run.episode.target_duration_s,
            notes=run.notes,
        )
        script = {**result.script.model_dump(mode="json"), "llm_calls": result.llm_calls}
        report = result.report.model_dump(mode="json")
        fail = None
        if not result.report.passed:
            codes = sorted({i.code for i in result.report.blocking})
            fail = (
                "naskah tidak lulus editorial gate (" + ", ".join(codes) + "); laporan "
                "revisi tersimpan di artefak editorial_report"
            )
        return StageOutput(
            [(ArtifactKind.SCRIPT, script), (ArtifactKind.EDITORIAL_REPORT, report)], fail
        )

    def _apply_override(self, run: StageRun) -> StageOutput:
        """Owner sudah menyetujui pengecualian: naskah terakhir dipakai apa adanya (tanpa LLM)."""
        override = self._latest(run.episode, ArtifactKind.EDITORIAL_OVERRIDE)
        report_artifact = self._latest(run.episode, ArtifactKind.EDITORIAL_REPORT)
        if override.content["report_hash"] != report_artifact.content_hash:
            raise StageError("override tidak cocok dengan laporan editorial terakhir")
        report = EditorialReport.model_validate(report_artifact.content)
        overridden = report.model_copy(
            update={"overridden": True, "override_reason": override.content["reason"]}
        )
        return StageOutput([(ArtifactKind.EDITORIAL_REPORT, overridden.model_dump(mode="json"))])
