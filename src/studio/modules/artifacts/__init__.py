"""Konten episode berversi. Versi lama tidak pernah ditimpa (dijaga trigger database)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from studio.infra.db import Database
from studio.shared.actors import Actor
from studio.shared.clock import Clock, from_iso, to_iso
from studio.shared.hashing import canonical_json, sha256_hex
from studio.shared.ids import new_id


class ArtifactKind(StrEnum):
    TOPICS = "topics"
    RESEARCH = "research"
    FACTCHECK = "factcheck"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    COST_ESTIMATE = "cost_estimate"
    RENDER = "render"
    EXPORT = "export"


@dataclass(frozen=True)
class Artifact:
    id: str
    episode_id: str
    kind: ArtifactKind
    version: int
    content: dict[str, Any]
    content_hash: str
    created_at: datetime
    created_by: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Artifact:
        return cls(
            id=row["id"],
            episode_id=row["episode_id"],
            kind=ArtifactKind(row["kind"]),
            version=row["version"],
            content=json.loads(row["content"]),
            content_hash=row["content_hash"],
            created_at=from_iso(row["created_at"]),
            created_by=row["created_by"],
        )


class ArtifactStore:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def put(
        self, episode_id: str, kind: ArtifactKind, content: dict[str, Any], actor: Actor
    ) -> Artifact:
        body = canonical_json(content)
        with self._db.transaction():
            current = self._db.scalar(
                "SELECT COALESCE(MAX(version), 0) FROM artifacts WHERE episode_id = ? AND kind = ?",
                (episode_id, kind.value),
            )
            artifact_id = new_id(self._clock)
            self._db.execute(
                "INSERT INTO artifacts (id, episode_id, kind, version, content, content_hash,"
                " created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    episode_id,
                    kind.value,
                    int(current) + 1,
                    body,
                    sha256_hex(body),
                    to_iso(self._clock.now()),
                    actor.label,
                ),
            )
            row = self._db.query_one("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        if row is None:  # pragma: no cover - baru saja di-insert dalam transaksi yang sama
            raise RuntimeError("artefak hilang setelah insert")
        return Artifact.from_row(row)

    def latest(self, episode_id: str, kind: ArtifactKind) -> Artifact | None:
        row = self._db.query_one(
            "SELECT * FROM artifacts WHERE episode_id = ? AND kind = ?"
            " ORDER BY version DESC LIMIT 1",
            (episode_id, kind.value),
        )
        return None if row is None else Artifact.from_row(row)

    def versions(self, episode_id: str, kind: ArtifactKind) -> list[Artifact]:
        rows = self._db.query_all(
            "SELECT * FROM artifacts WHERE episode_id = ? AND kind = ? ORDER BY version",
            (episode_id, kind.value),
        )
        return [Artifact.from_row(r) for r in rows]

    def all_latest(self, episode_id: str) -> dict[ArtifactKind, Artifact]:
        latest: dict[ArtifactKind, Artifact] = {}
        for kind in ArtifactKind:
            artifact = self.latest(episode_id, kind)
            if artifact is not None:
                latest[kind] = artifact
        return latest


__all__ = ["Artifact", "ArtifactKind", "ArtifactStore"]
