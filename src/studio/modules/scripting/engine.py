"""ScriptEngine: naskah dari ResearchBrief + editorial gate + revisi otomatis terbatas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from studio.modules.calls import CallScope, LLMClient
from studio.modules.research import ResearchBrief
from studio.modules.scripting.config import ScriptingConfig
from studio.modules.scripting.editorial import EditorialGate
from studio.modules.scripting.models import DocumentaryScript, EditorialReport, ScriptDraft
from studio.modules.scripting.timing import build_script


@dataclass(frozen=True)
class ScriptResult:
    script: DocumentaryScript
    report: EditorialReport
    llm_calls: list[dict[str, Any]]


def _brief_for_writer(brief: ResearchBrief) -> dict[str, Any]:
    """Hanya klaim yang boleh dipakai yang dikirim ke penulis naskah."""
    return {
        "topic": brief.topic.model_dump(mode="json"),
        "objective": brief.objective,
        "claims": [
            {
                "id": claim.id,
                "statement": claim.statement,
                "category": claim.category.value if claim.category else None,
                "conflicts_with": claim.conflicts_with,
            }
            for claim in brief.usable_claims()
        ],
        "sensitivity": brief.sensitivity.value,
        "sensitivity_reason": brief.sensitivity_reason,
    }


class ScriptEngine:
    def __init__(self, llm: LLMClient, config: ScriptingConfig) -> None:
        self._llm = llm
        self._config = config
        self.gate = EditorialGate(llm, config)

    @property
    def config(self) -> ScriptingConfig:
        return self._config

    def write(
        self,
        scope: CallScope,
        brief: ResearchBrief,
        source_texts: dict[str, str],
        *,
        format_name: str,
        target_duration_s: int,
        notes: str | None,
    ) -> ScriptResult:
        spec = self._config.format_spec(format_name)
        common = {
            "format": format_name,
            "format_label": spec.label,
            "duration_range_s": [spec.min_s, spec.max_s],
            "target_duration_s": target_duration_s,
            "words_per_minute": self._config.narration.words_per_minute,
            "owner_notes": notes,
        }
        calls: list[dict[str, Any]] = []
        draft = self._llm.run(
            scope,
            "script_generation",
            data={**common, "brief": _brief_for_writer(brief)},
            schema=ScriptDraft,
            context_key=brief.topic.key,
            variant=format_name,
        )
        calls += draft.calls
        revision = 0
        while True:
            script = build_script(
                draft.value,
                format_name=format_name,
                spec=spec,
                target_duration_s=target_duration_s,
                narration=self._config.narration,
                revision=revision,
                notes=notes,
            )
            report, review_calls = self.gate.review(
                scope, script, brief, source_texts, spec, sub_key=f"r{revision}"
            )
            calls += review_calls
            if report.passed or revision >= self._config.editorial.max_auto_revisions:
                break
            revision += 1
            draft = self._llm.run(
                scope,
                "script_revision",
                data={
                    **common,
                    "brief": _brief_for_writer(brief),
                    "script": script.model_dump(mode="json"),
                    "editorial_report": report.model_dump(mode="json"),
                },
                schema=ScriptDraft,
                context_key=brief.topic.key,
                variant=format_name,
                sub_key=f"r{revision}",
            )
            calls += draft.calls
        warnings = [f"[{i.severity.value}] {i.message}" for i in report.issues]
        script = script.model_copy(update={"editorial_warnings": warnings})
        return ScriptResult(script, report, calls)
