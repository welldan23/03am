from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from studio.shared.clock import from_iso
from studio.shared.errors import StudioError

MIN_DURATION_S = 30
MAX_DURATION_S = 180


class Category(StrEnum):
    SEJARAH = "sejarah"
    GEOPOLITIK = "geopolitik"
    SAINS = "sains"
    GEOGRAFI = "geografi"
    MISTERI = "misteri"


class EpisodeStatus(StrEnum):
    DRAFT = "DRAFT"
    DISCOVERING = "DISCOVERING"
    AWAITING_TOPIC = "AWAITING_TOPIC"
    RESEARCHING = "RESEARCHING"
    FACT_CHECKING = "FACT_CHECKING"
    SCRIPTING = "SCRIPTING"
    STORYBOARDING = "STORYBOARDING"
    AWAITING_EDITORIAL = "AWAITING_EDITORIAL"
    ESTIMATING_COST = "ESTIMATING_COST"
    AWAITING_COST = "AWAITING_COST"
    GENERATING_ASSETS = "GENERATING_ASSETS"
    GENERATING_VOICE = "GENERATING_VOICE"
    RENDERING = "RENDERING"
    AWAITING_FINAL = "AWAITING_FINAL"
    EXPORTING = "EXPORTING"
    EXPORTED = "EXPORTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class Trigger(StrEnum):
    START = "start"
    COMPLETE = "complete"
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"
    FAIL = "fail"
    RETRY = "retry"
    CANCEL = "cancel"


class IllegalTransitionError(StudioError):
    pass


@dataclass(frozen=True)
class Episode:
    id: str
    category: Category
    target_duration_s: int
    idea: str | None
    title: str | None
    status: EpisodeStatus
    failed_from: EpisodeStatus | None
    failure_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Episode:
        return cls(
            id=row["id"],
            category=Category(row["category"]),
            target_duration_s=row["target_duration_s"],
            idea=row["idea"],
            title=row["title"],
            status=EpisodeStatus(row["status"]),
            failed_from=EpisodeStatus(row["failed_from"]) if row["failed_from"] else None,
            failure_reason=row["failure_reason"],
            version=row["version"],
            created_at=from_iso(row["created_at"]),
            updated_at=from_iso(row["updated_at"]),
        )
