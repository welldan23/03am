"""Model naskah dokumenter & laporan editorial."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from studio.modules.research import Severity


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SegmentRole(StrEnum):
    HOOK = "hook"
    CONTEXT = "context"
    CONFLICT = "conflict"
    EXPLANATION = "explanation"
    CLOSING = "closing"


REQUIRED_STRUCTURE = [
    SegmentRole.HOOK,
    SegmentRole.CONTEXT,
    SegmentRole.CONFLICT,
    SegmentRole.EXPLANATION,
    SegmentRole.CLOSING,
]


class ScriptLine(_Model):
    text: str = Field(min_length=1)
    claim_refs: list[str] = Field(default_factory=list)


class PronunciationNote(_Model):
    term: str
    guide: str


# --- skema keluaran LLM -------------------------------------------------------------


class DraftSegment(_Model):
    role: SegmentRole
    visual_direction: str
    lines: list[ScriptLine] = Field(min_length=1)


class ScriptDraft(_Model):
    title: str
    segments: list[DraftSegment] = Field(min_length=1)
    pronunciation_notes: list[PronunciationNote] = Field(default_factory=list)


class ReviewNote(_Model):
    severity: str
    segment: str | None = None
    message: str


class ScriptReviewOutput(BaseModel):
    """Saran gaya dari LLM. Field tambahan (misalnya "approve": true) diabaikan, bukan ditolak,
    karena LLM memang tidak punya wewenang menentukan hasil gate."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    notes: list[ReviewNote] = Field(default_factory=list)


# --- naskah hasil olahan sistem -----------------------------------------------------


class ScriptSegment(_Model):
    index: int
    role: SegmentRole
    visual_direction: str
    lines: list[ScriptLine]
    word_count: int
    start_s: float
    end_s: float
    duration_s: float

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines)


class DocumentaryScript(_Model):
    title: str
    format: str
    format_label: str
    target_duration_s: int
    words_per_minute: int
    segments: list[ScriptSegment]
    narration_text: str
    word_count: int
    estimated_duration_s: float
    claim_refs: list[str]
    pronunciation_notes: list[PronunciationNote]
    editorial_warnings: list[str] = Field(default_factory=list)
    revision: int = 0
    notes: str | None = None


class EditorialIssue(_Model):
    code: str
    severity: Severity
    message: str
    segment_index: int | None = None
    line_index: int | None = None
    claim_id: str | None = None


class EditorialReport(_Model):
    passed: bool
    script_revision: int
    issues: list[EditorialIssue]
    advisory_notes: list[ReviewNote]
    revision_instructions: list[str]
    metrics: dict[str, float | int | str]
    overridden: bool = False
    override_reason: str | None = None

    @property
    def blocking(self) -> list[EditorialIssue]:
        return [i for i in self.issues if i.severity is Severity.BLOCKING]
