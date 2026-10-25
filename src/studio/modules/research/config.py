from __future__ import annotations

import re
from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field


class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_sources: int = Field(gt=0, le=50)
    min_verified_facts: int = Field(ge=1)
    min_independent_sources_critical: int = Field(ge=1)
    min_independent_sources_supporting: int = Field(ge=1)
    max_tier_for_verification: int = Field(ge=1, le=5)
    max_tier_for_independence: int = Field(ge=1, le=5)
    max_evidence_quote_words: int = Field(gt=0)
    injection_patterns: list[str]

    @cached_property
    def injection_regexes(self) -> list[re.Pattern[str]]:
        return [re.compile(p, re.IGNORECASE) for p in self.injection_patterns]
