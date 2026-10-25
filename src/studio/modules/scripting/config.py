from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FormatSpec(_Config):
    label: str
    min_s: int = Field(gt=0)
    max_s: int = Field(gt=0)
    default_s: int = Field(gt=0)

    @model_validator(mode="after")
    def _range(self) -> FormatSpec:
        if not self.min_s <= self.default_s <= self.max_s:
            raise ValueError("default_s harus di antara min_s dan max_s")
        return self

    def contains(self, seconds: float) -> bool:
        return self.min_s <= seconds <= self.max_s


class NarrationConfig(_Config):
    words_per_minute: int = Field(gt=60, lt=300)
    segment_pause_s: float = Field(ge=0, le=5)


class EditorialConfig(_Config):
    duration_tolerance_pct: int = Field(ge=0, le=50)
    max_auto_revisions: int = Field(ge=0, le=3)
    max_quote_words: int = Field(gt=0)
    verbatim_warn_words: int = Field(gt=3)
    verbatim_block_words: int = Field(gt=3)
    sensational_blocking_threshold: int = Field(ge=1)
    min_claim_overlap: float = Field(ge=0, le=1)
    hedge_markers: list[str]
    sensational_terms: list[str]
    ambiguous_terms: list[str]


class ScriptingConfig(_Config):
    narration: NarrationConfig
    formats: dict[str, FormatSpec]
    editorial: EditorialConfig

    def format_spec(self, name: str) -> FormatSpec:
        return self.formats[name]

    def format_for_duration(self, seconds: int) -> str:
        """Format yang rentangnya memuat durasi; kalau tidak ada, format terdekat."""
        for name, spec in self.formats.items():
            if spec.contains(seconds):
                return name

        def distance(item: tuple[str, FormatSpec]) -> tuple[int, int]:
            _, spec = item
            gap = spec.min_s - seconds if seconds < spec.min_s else seconds - spec.max_s
            return gap, spec.max_s

        return min(self.formats.items(), key=distance)[0]
