"""Pemeriksa fakta deterministik (tanpa LLM).

LLM hanya mengusulkan kutipan dan klaim. Yang menentukan kategori klaim adalah aturan di
sini, berdasarkan bukti yang kutipannya terbukti ada di teks sumber.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from studio.modules.research.config import ResearchConfig
from studio.modules.research.models import (
    AssertionType,
    ClaimCategory,
    ClaimRecord,
    Contradiction,
    EvidenceRecord,
    Importance,
    QualityIssue,
    ResearchBrief,
    ResearchDossier,
    ResearchQualityReport,
    Severity,
    SourceRecord,
    Stance,
    TimelineEntry,
)
from studio.modules.research.text import normalize, truncate_words, word_count


@dataclass(frozen=True)
class FactCheckResult:
    brief: ResearchBrief
    report: ResearchQualityReport
    evidence: list[EvidenceRecord]
    claims: list[ClaimRecord]


def _event_start(value: str | None) -> date | None:
    if not value:
        return None
    parts = value.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


class FactChecker:
    def __init__(self, config: ResearchConfig) -> None:
        self._config = config

    def _verify_evidence(
        self,
        dossier: ResearchDossier,
        sources: dict[str, SourceRecord],
        issues: list[QualityIssue],
    ) -> dict[str, EvidenceRecord]:
        verified: dict[str, EvidenceRecord] = {}
        for item in dossier.evidence:
            source = sources.get(item.source_id)
            reason: str | None = None
            if source is None:
                reason = "sumber tidak dikenal (bukan hasil pengambilan sumber)"
                issues.append(
                    QualityIssue(
                        code="UNKNOWN_SOURCE_REFERENCE",
                        severity=Severity.WARNING,
                        source_id=item.source_id,
                        message=f"bukti {item.id} merujuk sumber yang tidak "
                        "pernah diambil; dibuang",
                    )
                )
            elif normalize(item.quote) not in normalize(dossier.source_texts.get(source.id, "")):
                reason = "kutipan tidak ditemukan persis di teks sumber"
                issues.append(
                    QualityIssue(
                        code="EVIDENCE_QUOTE_NOT_FOUND",
                        severity=Severity.WARNING,
                        source_id=source.id,
                        message=f"kutipan bukti {item.id} tidak ada di teks "
                        "sumber (kemungkinan halusinasi); dibuang",
                    )
                )
            elif source.quarantined:
                reason = "sumber dikarantina (indikasi prompt injection)"
            quote = item.quote
            if reason is None and item.quote_word_count > self._config.max_evidence_quote_words:
                quote = truncate_words(item.quote, self._config.max_evidence_quote_words)
                issues.append(
                    QualityIssue(
                        code="QUOTE_TOO_LONG",
                        severity=Severity.WARNING,
                        source_id=item.source_id,
                        message=f"kutipan {item.id} dipotong menjadi "
                        f"{self._config.max_evidence_quote_words} kata",
                    )
                )
            verified[item.id] = item.model_copy(
                update={"verified": reason is None, "rejection_reason": reason, "quote": quote}
            )
        return verified

    def _classify(
        self,
        claim: ClaimRecord,
        evidence: dict[str, EvidenceRecord],
        sources: dict[str, SourceRecord],
        issues: list[QualityIssue],
    ) -> ClaimRecord:
        supports: list[SourceRecord] = []
        contradicts: list[SourceRecord] = []
        event_start = _event_start(claim.event_date)
        for evidence_id in claim.evidence_ids:
            item = evidence.get(evidence_id)
            if item is None:
                issues.append(
                    QualityIssue(
                        code="UNKNOWN_EVIDENCE_REFERENCE",
                        severity=Severity.WARNING,
                        claim_id=claim.id,
                        message=f"klaim {claim.id} merujuk bukti {evidence_id} yang tidak ada",
                    )
                )
                continue
            if not item.verified:
                continue
            source = sources[item.source_id]
            published = date.fromisoformat(source.published_date) if source.published_date else None
            if event_start and published and published < event_start:
                issues.append(
                    QualityIssue(
                        code="SOURCE_PREDATES_EVENT",
                        severity=Severity.WARNING,
                        claim_id=claim.id,
                        source_id=source.id,
                        message=f"{source.id} terbit ({source.published_date}) "
                        f"sebelum peristiwa ({claim.event_date}); tidak dihitung",
                    )
                )
                continue
            if item.stance is Stance.SUPPORTS:
                supports.append(source)
            elif (
                item.stance is Stance.CONTRADICTS
                and source.tier <= self._config.max_tier_for_independence
            ):
                contradicts.append(source)

        registered = {s.url for s in sources.values()}
        for url in claim.source_urls:
            if url not in registered:
                issues.append(
                    QualityIssue(
                        code="UNREGISTERED_URL",
                        severity=Severity.WARNING,
                        claim_id=claim.id,
                        message=f"URL '{url}' disebut model tetapi bukan sumber "
                        "yang diambil; diabaikan (bukan sumber)",
                    )
                )

        groups = {
            s.independence_group
            for s in supports
            if s.tier <= self._config.max_tier_for_independence
        }
        best_tier = min((s.tier for s in supports), default=None)
        required = (
            self._config.min_independent_sources_critical
            if claim.importance is Importance.CRITICAL
            else self._config.min_independent_sources_supporting
        )

        if not supports:
            category, rationale = ClaimCategory.UNVERIFIED, "tidak ada bukti terverifikasi"
        elif contradicts:
            category = ClaimCategory.DISPUTED
            rationale = (
                f"didukung {len(supports)} sumber, dibantah {', '.join(s.id for s in contradicts)}"
            )
        elif claim.assertion_type is AssertionType.HYPOTHESIS:
            category, rationale = ClaimCategory.HYPOTHESIS, "hipotesis yang tercatat di sumber"
        elif claim.assertion_type is AssertionType.INTERPRETATION:
            category, rationale = (
                ClaimCategory.INTERPRETATION,
                "interpretasi yang tercatat di sumber",
            )
        elif best_tier is not None and best_tier > self._config.max_tier_for_verification:
            category = ClaimCategory.UNVERIFIED
            rationale = (
                f"hanya didukung sumber tier {best_tier} (perlu tier ≤ "
                f"{self._config.max_tier_for_verification})"
            )
            issues.append(
                QualityIssue(
                    code="LOW_TIER_ONLY",
                    severity=Severity.WARNING,
                    claim_id=claim.id,
                    message=rationale,
                )
            )
        elif len(groups) < required:
            category = ClaimCategory.UNVERIFIED
            rationale = (
                f"{len(supports)} sumber pendukung tetapi hanya {len(groups)} kelompok "
                f"independen (perlu {required})"
            )
            issues.append(
                QualityIssue(
                    code="INSUFFICIENT_INDEPENDENCE",
                    severity=Severity.WARNING,
                    claim_id=claim.id,
                    message=rationale,
                )
            )
        else:
            category = ClaimCategory.VERIFIED_FACT
            rationale = f"{len(groups)} kelompok sumber independen, tier terbaik {best_tier}"

        if category is ClaimCategory.UNVERIFIED and claim.importance is Importance.CRITICAL:
            issues.append(
                QualityIssue(
                    code="CRITICAL_CLAIM_UNVERIFIED",
                    severity=Severity.WARNING,
                    claim_id=claim.id,
                    message=f"klaim penting {claim.id} belum terverifikasi: "
                    f"{rationale}; tidak boleh disajikan sebagai fakta",
                )
            )
        if category is ClaimCategory.DISPUTED:
            issues.append(
                QualityIssue(
                    code="CONTRADICTION",
                    severity=Severity.INFO,
                    claim_id=claim.id,
                    message=rationale,
                )
            )
        return claim.model_copy(
            update={
                "category": category,
                "supporting_source_ids": sorted({s.id for s in supports}),
                "contradicting_source_ids": sorted({s.id for s in contradicts}),
                "independent_groups": len(groups),
                "best_tier": best_tier,
                "rationale": rationale,
            }
        )

    def check(self, dossier: ResearchDossier) -> FactCheckResult:
        issues: list[QualityIssue] = []
        sources = {s.id: s for s in dossier.sources}
        for source in dossier.sources:
            if source.injection_suspected:
                issues.append(
                    QualityIssue(
                        code="INJECTION_SUSPECTED",
                        severity=Severity.WARNING,
                        source_id=source.id,
                        message=f"{source.id} berisi pola instruksi "
                        "tersembunyi; teks dinetralkan & sumber dikarantina",
                    )
                )
        evidence = self._verify_evidence(dossier, sources, issues)
        claims = [self._classify(c, evidence, sources, issues) for c in dossier.claims]

        by_category: dict[ClaimCategory, list[ClaimRecord]] = {c: [] for c in ClaimCategory}
        for claim in claims:
            if claim.category is not None:
                by_category[claim.category].append(claim)
        verified_count = len(by_category[ClaimCategory.VERIFIED_FACT])
        if verified_count < self._config.min_verified_facts:
            issues.append(
                QualityIssue(
                    code="INSUFFICIENT_VERIFIED_FACTS",
                    severity=Severity.BLOCKING,
                    message=f"hanya {verified_count} fakta terverifikasi "
                    f"(minimal {self._config.min_verified_facts})",
                )
            )

        cited = sorted(
            {sid for c in claims for sid in (*c.supporting_source_ids, *c.contradicting_source_ids)}
        )
        contradictions = [
            Contradiction(
                claim_id=c.id,
                supporting_source_ids=c.supporting_source_ids,
                contradicting_source_ids=c.contradicting_source_ids,
                conflicting_claim_ids=c.conflicts_with,
            )
            for c in claims
            if c.category is ClaimCategory.DISPUTED or c.conflicts_with
        ]
        timeline = sorted(
            (
                TimelineEntry(event_date=c.event_date, claim_id=c.id, statement=c.statement)
                for c in claims
                if c.event_date and c.category is ClaimCategory.VERIFIED_FACT
            ),
            key=lambda entry: entry.event_date,
        )
        brief = ResearchBrief(
            topic=dossier.topic,
            objective=dossier.plan.objective,
            verified_facts=by_category[ClaimCategory.VERIFIED_FACT],
            interpretations=by_category[ClaimCategory.INTERPRETATION],
            hypotheses=by_category[ClaimCategory.HYPOTHESIS],
            disputed=by_category[ClaimCategory.DISPUTED],
            unverified=by_category[ClaimCategory.UNVERIFIED],
            timeline=timeline,
            sources=[sources[sid] for sid in cited],
            contradictions=contradictions,
            open_questions=[
                f"Perlu sumber tambahan: {c.statement} ({c.rationale})"
                for c in by_category[ClaimCategory.UNVERIFIED]
                if c.importance is Importance.CRITICAL
            ],
            sensitivity=dossier.topic.sensitivity,
            sensitivity_reason=dossier.topic.sensitivity_reason,
        )
        report = ResearchQualityReport(
            passed=not any(i.severity is Severity.BLOCKING for i in issues),
            verified_facts=verified_count,
            min_verified_facts=self._config.min_verified_facts,
            claims_by_category={c.value: len(v) for c, v in by_category.items()},
            sources_by_tier={
                str(t): n for t, n in sorted(Counter(s.tier for s in dossier.sources).items())
            },
            rejected_evidence=sum(1 for e in evidence.values() if not e.verified),
            issues=issues,
        )
        return FactCheckResult(brief, report, list(evidence.values()), claims)


def evidence_from_extraction(
    source: SourceRecord, items: list[tuple[str, Stance, str]]
) -> list[EvidenceRecord]:
    """Beri ID deterministik E-<sumber>-<urutan> pada bukti hasil ekstraksi."""
    return [
        EvidenceRecord(
            id=f"E-{source.id}-{i}",
            source_id=source.id,
            quote=quote,
            quote_word_count=word_count(quote),
            stance=stance,
            claim_key=claim_key,
        )
        for i, (quote, stance, claim_key) in enumerate(items, start=1)
    ]
