"""Model domain riset: dari kandidat topik sampai ResearchBrief.

Prinsip: setiap klaim bisa ditelusuri ke bukti (kutipan persis) dan sumbernya. Sumber hanya
berasal dari SourceProvider — keluaran LLM tidak pernah dianggap sumber.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TopicCategory(StrEnum):
    SEJARAH_DUNIA = "sejarah_dunia"
    GEOGRAFI = "geografi"
    GEOPOLITIK = "geopolitik"
    SAINS_TEKNOLOGI = "sains_teknologi"
    MISTERI_SEJARAH = "misteri_sejarah"
    PERADABAN_KUNO = "peradaban_kuno"
    FENOMENA_ALAM = "fenomena_alam"
    FAKTA_UNIK = "fakta_unik"


class Level(StrEnum):
    RENDAH = "rendah"
    SEDANG = "sedang"
    TINGGI = "tinggi"


class SourceType(StrEnum):
    ACADEMIC = "academic"
    PRIMARY_RESEARCH = "primary_research"
    ARCHIVE = "archive"
    MUSEUM = "museum"
    SCIENTIFIC_INSTITUTION = "scientific_institution"
    GOVERNMENT = "government"
    INTERNATIONAL_ORG = "international_org"
    MEDIA = "media"
    SECONDARY = "secondary"
    OTHER = "other"


# Tier 1 = paling kuat. Urutan mengikuti kebijakan sumber 03:AM.
SOURCE_TIER: dict[SourceType, int] = {
    SourceType.ACADEMIC: 1,
    SourceType.PRIMARY_RESEARCH: 1,
    SourceType.ARCHIVE: 2,
    SourceType.MUSEUM: 2,
    SourceType.SCIENTIFIC_INSTITUTION: 2,
    SourceType.GOVERNMENT: 3,
    SourceType.INTERNATIONAL_ORG: 3,
    SourceType.MEDIA: 4,
    SourceType.SECONDARY: 5,
    SourceType.OTHER: 5,
}


class Stance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class AssertionType(StrEnum):
    FACT = "fact"
    INTERPRETATION = "interpretation"
    HYPOTHESIS = "hypothesis"


class Importance(StrEnum):
    CRITICAL = "critical"
    SUPPORTING = "supporting"


class ClaimCategory(StrEnum):
    VERIFIED_FACT = "verified_fact"
    INTERPRETATION = "interpretation"
    HYPOTHESIS = "hypothesis"
    DISPUTED = "disputed"
    UNVERIFIED = "unverified"


CATEGORY_LABEL: dict[ClaimCategory, str] = {
    ClaimCategory.VERIFIED_FACT: "Fakta terverifikasi",
    ClaimCategory.INTERPRETATION: "Interpretasi",
    ClaimCategory.HYPOTHESIS: "Hipotesis",
    ClaimCategory.DISPUTED: "Diperdebatkan",
    ClaimCategory.UNVERIFIED: "Belum terverifikasi",
}


class Severity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


# --- kandidat topik & rencana ------------------------------------------------------


class TopicCandidate(_Model):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    title: str = Field(min_length=3, max_length=120)
    topic_category: TopicCategory
    angle: str
    hook_question: str
    why_interesting: str
    sensitivity: Level
    sensitivity_reason: str
    verifiability: Level
    suggested_format: Literal["quick_files", "archives", "deep_files"]
    search_terms: list[str] = Field(default_factory=list)


class TopicList(_Model):
    candidates: list[TopicCandidate] = Field(min_length=1, max_length=8)


class ResearchQuestion(_Model):
    id: str
    question: str
    priority: Importance


class ResearchPlan(_Model):
    objective: str
    questions: list[ResearchQuestion] = Field(min_length=1)
    search_queries: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(default_factory=list)


# --- sumber, bukti, klaim ------------------------------------------------------------


class SourceRecord(_Model):
    id: str
    title: str
    publisher: str
    url: str
    source_type: SourceType
    tier: int = Field(ge=1, le=5)
    quality_score: int = Field(ge=0, le=100)
    published_date: str | None
    authors: list[str]
    origin: str
    derived_from: list[str]
    independence_group: str
    retrieved_via: str
    retrieved_at: str  # tanggal akses (UTC, ISO 8601)
    is_fixture: bool
    content_hash: str
    injection_suspected: bool
    injection_markers: list[str]
    quarantined: bool
    notes: list[str]


class EvidenceRecord(_Model):
    id: str
    source_id: str
    quote: str
    quote_word_count: int
    stance: Stance
    claim_key: str
    verified: bool | None = None
    rejection_reason: str | None = None


class ClaimRecord(_Model):
    id: str
    key: str
    statement: str
    assertion_type: AssertionType
    importance: Importance
    event_date: str | None = None
    evidence_ids: list[str]
    conflicts_with: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    category: ClaimCategory | None = None
    supporting_source_ids: list[str] = Field(default_factory=list)
    contradicting_source_ids: list[str] = Field(default_factory=list)
    independent_groups: int = 0
    best_tier: int | None = None
    rationale: str = ""


class ResearchDossier(_Model):
    """Hasil tahap RESEARCHING (belum diperiksa). Disimpan sebagai artefak `research`."""

    topic: TopicCandidate
    plan: ResearchPlan
    sources: list[SourceRecord]
    source_texts: dict[str, str]
    evidence: list[EvidenceRecord]
    claims: list[ClaimRecord]


class QualityIssue(_Model):
    code: str
    severity: Severity
    message: str
    claim_id: str | None = None
    source_id: str | None = None


class ResearchQualityReport(_Model):
    passed: bool
    verified_facts: int
    min_verified_facts: int
    claims_by_category: dict[str, int]
    sources_by_tier: dict[str, int]
    rejected_evidence: int
    issues: list[QualityIssue]


class Contradiction(_Model):
    claim_id: str
    supporting_source_ids: list[str]
    contradicting_source_ids: list[str]
    conflicting_claim_ids: list[str]


class TimelineEntry(_Model):
    event_date: str
    claim_id: str
    statement: str


class ResearchBrief(_Model):
    """Ringkasan riset terverifikasi — satu-satunya dasar penulisan naskah."""

    topic: TopicCandidate
    objective: str
    verified_facts: list[ClaimRecord]
    interpretations: list[ClaimRecord]
    hypotheses: list[ClaimRecord]
    disputed: list[ClaimRecord]
    unverified: list[ClaimRecord]
    timeline: list[TimelineEntry]
    sources: list[SourceRecord]
    contradictions: list[Contradiction]
    open_questions: list[str]
    sensitivity: Level
    sensitivity_reason: str

    def all_claims(self) -> list[ClaimRecord]:
        return [
            *self.verified_facts,
            *self.interpretations,
            *self.hypotheses,
            *self.disputed,
            *self.unverified,
        ]

    def claim(self, claim_id: str) -> ClaimRecord | None:
        return next((c for c in self.all_claims() if c.id == claim_id), None)

    def usable_claims(self) -> list[ClaimRecord]:
        """Klaim yang boleh dipakai di naskah (yang belum terverifikasi dikecualikan)."""
        return [c for c in self.all_claims() if c.category is not ClaimCategory.UNVERIFIED]


# --- skema keluaran LLM (divalidasi ketat) ----------------------------------------------


class ExtractedEvidence(_Model):
    quote: str = Field(min_length=1)
    stance: Stance
    claim_key: str


class EvidenceExtractionOutput(_Model):
    evidence: list[ExtractedEvidence]


class AnalyzedClaim(_Model):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    statement: str = Field(min_length=3)
    assertion_type: AssertionType
    importance: Importance
    event_date: str | None = None
    evidence_ids: list[str]
    conflicts_with: list[str] = Field(default_factory=list)
    # Kalau model menyebut URL, URL itu diperiksa terhadap daftar sumber yang benar-benar
    # diambil. URL yang tidak terdaftar ditandai sebagai halusinasi.
    source_urls: list[str] = Field(default_factory=list)


class ClaimAnalysisOutput(_Model):
    claims: list[AnalyzedClaim]
