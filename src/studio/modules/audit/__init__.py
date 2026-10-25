"""Audit log append-only: siapa melakukan apa, kapan, terhadap apa."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from studio.infra.db import Database
from studio.shared.actors import Actor
from studio.shared.clock import Clock, from_iso, to_iso
from studio.shared.hashing import canonical_json
from studio.shared.ids import new_id


@dataclass(frozen=True)
class AuditEntry:
    id: str
    at: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    episode_id: str | None
    data: dict[str, Any]


class AuditLog:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def record(
        self,
        *,
        actor: Actor,
        action: str,
        entity_type: str,
        entity_id: str,
        episode_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        entry_id = new_id(self._clock)
        self._db.execute(
            "INSERT INTO audit_log (id, at, actor, action, entity_type, entity_id,"
            " episode_id, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id,
                to_iso(self._clock.now()),
                actor.label,
                action,
                entity_type,
                entity_id,
                episode_id,
                canonical_json(data or {}),
            ),
        )
        return entry_id

    def entries(
        self, *, episode_id: str | None = None, action: str | None = None
    ) -> list[AuditEntry]:
        sql = "SELECT * FROM audit_log WHERE 1 = 1"
        params: list[Any] = []
        if episode_id is not None:
            sql += " AND episode_id = ?"
            params.append(episode_id)
        if action is not None:
            sql += " AND action = ?"
            params.append(action)
        rows = self._db.query_all(sql + " ORDER BY at, id", params)
        return [
            AuditEntry(
                id=r["id"],
                at=from_iso(r["at"]),
                actor=r["actor"],
                action=r["action"],
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                episode_id=r["episode_id"],
                data=json.loads(r["data"]),
            )
            for r in rows
        ]


__all__ = ["AuditEntry", "AuditLog"]
