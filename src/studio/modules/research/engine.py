"""ResearchEngine: Topic → Research Plan → Evidence → Source Verification → Claims → Brief.

Semua pekerjaan eksternal (LLM, pengambilan sumber) dijalankan di luar transaksi database.
Fact checking (`fact_check`) murni deterministik.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from studio.modules.calls import CallScope, LLMClient
from studio.modules.research.config import ResearchConfig
from studio.modules.research.factcheck import FactChecker, FactCheckResult, evidence_from_extraction
from studio.modules.research.models import (
    ClaimAnalysisOutput,
    ClaimRecord,
    EvidenceExtractionOutput,
    ResearchDossier,
    ResearchPlan,
    TopicCandidate,
    TopicList,
)
from studio.modules.research.sources import assess, assign_groups
from studio.providers.sources.ports import SourceProvider
from studio.shared.clock import Clock, to_iso


@dataclass(frozen=True)
class EngineResult[T]:
    value: T
    llm_calls: list[dict[str, Any]]


class ResearchEngine:
    def __init__(
        self, llm: LLMClient, sources: SourceProvider, config: ResearchConfig, clock: Clock
    ) -> None:
        self._llm = llm
        self._clock = clock
        self._sources = sources
        self._config = config
        self._checker = FactChecker(config)

    def discover(
        self, scope: CallScope, *, episode_category: str, idea: str | None, notes: str | None
    ) -> EngineResult[TopicList]:
        result = self._llm.run(
            scope,
            "topic_discovery",
            data={"episode_category": episode_category, "idea": idea, "owner_notes": notes},
            schema=TopicList,
            context_key="default",
        )
        return EngineResult(result.value, result.calls)

    def research(
        self, scope: CallScope, topic: TopicCandidate, *, notes: str | None
    ) -> EngineResult[ResearchDossier]:
        calls: list[dict[str, Any]] = []
        plan_result = self._llm.run(
            scope,
            "research_plan",
            data={"topic": topic.model_dump(mode="json"), "owner_notes": notes},
            schema=ResearchPlan,
            context_key=topic.key,
        )
        plan = plan_result.value
        calls += plan_result.calls

        # Sumber HANYA dari SourceProvider (I/O di luar transaksi). Tidak pernah dari LLM.
        documents = self._sources.search(
            topic.key, [*plan.search_queries, *topic.search_terms], self._config.max_sources
        )
        retrieved_at = to_iso(self._clock.now())
        assessed = [assess(doc, self._config, retrieved_at=retrieved_at) for doc in documents]
        records = assign_groups(record for record, _ in assessed)
        texts = {doc.id: doc.text for doc in documents}

        evidence = []
        for record, (_, injection) in zip(records, assessed, strict=True):
            extraction = self._llm.run(
                scope,
                "evidence_extraction",
                data={
                    "plan": plan.model_dump(mode="json"),
                    "source": {
                        "id": record.id,
                        "title": record.title,
                        "publisher": record.publisher,
                        # Kalimat berpola injeksi sudah dihapus sebelum masuk prompt.
                        "text": injection.sanitized_text,
                    },
                },
                schema=EvidenceExtractionOutput,
                context_key=topic.key,
                variant=record.id,
                sub_key=record.id,
            )
            calls += extraction.calls
            evidence += evidence_from_extraction(
                record, [(e.quote, e.stance, e.claim_key) for e in extraction.value.evidence]
            )

        quarantined = {r.id for r in records if r.quarantined}
        analysis = self._llm.run(
            scope,
            "claim_analysis",
            data={
                "plan": plan.model_dump(mode="json"),
                "evidence": [
                    e.model_dump(mode="json") for e in evidence if e.source_id not in quarantined
                ],
            },
            schema=ClaimAnalysisOutput,
            context_key=topic.key,
        )
        calls += analysis.calls
        claims = [
            ClaimRecord(
                id=f"C-{c.key}",
                key=c.key,
                statement=c.statement,
                assertion_type=c.assertion_type,
                importance=c.importance,
                event_date=c.event_date,
                evidence_ids=c.evidence_ids,
                conflicts_with=[f"C-{k}" for k in c.conflicts_with],
                source_urls=c.source_urls,
            )
            for c in analysis.value.claims
        ]
        dossier = ResearchDossier(
            topic=topic,
            plan=plan,
            sources=records,
            source_texts=texts,
            evidence=evidence,
            claims=claims,
        )
        return EngineResult(dossier, calls)

    def fact_check(self, dossier: ResearchDossier) -> FactCheckResult:
        return self._checker.check(dossier)
