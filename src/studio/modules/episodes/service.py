from __future__ import annotations

from typing import Any

from studio.infra.db import Database
from studio.modules.audit import AuditLog
from studio.modules.episodes import state
from studio.modules.episodes.models import (
    MAX_DURATION_S,
    MIN_DURATION_S,
    Category,
    DocumentaryFormat,
    Episode,
    EpisodeStatus,
    Trigger,
)
from studio.shared.actors import Actor
from studio.shared.clock import Clock, to_iso
from studio.shared.errors import ConflictError, NotFoundError
from studio.shared.ids import new_id


class EpisodeService:
    def __init__(self, db: Database, clock: Clock, audit: AuditLog) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit

    def create(
        self,
        *,
        category: Category,
        target_duration_s: int,
        idea: str | None,
        actor: Actor,
        format: DocumentaryFormat | None = None,
    ) -> Episode:
        if not MIN_DURATION_S <= target_duration_s <= MAX_DURATION_S:
            raise ValueError(f"durasi harus {MIN_DURATION_S}–{MAX_DURATION_S} detik")
        episode_id = new_id(self._clock)
        now = to_iso(self._clock.now())
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO episodes (id, category, target_duration_s, format, idea, status,"
                " version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    episode_id,
                    category.value,
                    target_duration_s,
                    format.value if format else None,
                    idea,
                    EpisodeStatus.DRAFT.value,
                    now,
                    now,
                ),
            )
            self._audit.record(
                actor=actor,
                action="episode.created",
                entity_type="episode",
                entity_id=episode_id,
                episode_id=episode_id,
                data={
                    "category": category.value,
                    "target_duration_s": target_duration_s,
                    "format": format.value if format else None,
                },
            )
        return self.get(episode_id)

    def get(self, episode_id: str) -> Episode:
        row = self._db.query_one("SELECT * FROM episodes WHERE id = ?", (episode_id,))
        if row is None:
            raise NotFoundError(f"episode {episode_id} tidak ditemukan")
        return Episode.from_row(row)

    def list_episodes(self, status: EpisodeStatus | None = None) -> list[Episode]:
        if status is None:
            rows = self._db.query_all("SELECT * FROM episodes ORDER BY created_at")
        else:
            rows = self._db.query_all(
                "SELECT * FROM episodes WHERE status = ? ORDER BY created_at", (status.value,)
            )
        return [Episode.from_row(r) for r in rows]

    def transition(
        self,
        episode_id: str,
        *,
        trigger: Trigger,
        target: EpisodeStatus,
        actor: Actor,
        expected_version: int | None = None,
        reason: str | None = None,
        title: str | None = None,
    ) -> Episode:
        """Pindahkan status sesuai tabel transisi. Satu transisi = satu entri audit."""
        with self._db.transaction():
            episode = self.get(episode_id)
            if expected_version is not None and episode.version != expected_version:
                raise ConflictError(
                    f"episode {episode_id} sudah berubah (versi {episode.version}, "
                    f"diharapkan {expected_version})"
                )
            state.check_transition(episode.status, trigger, target)
            if trigger is Trigger.RETRY and target != episode.failed_from:
                raise ConflictError(
                    f"retry harus kembali ke {episode.failed_from}, bukan {target.value}"
                )

            failed_from: str | None = None
            failure_reason: str | None = None
            if target is EpisodeStatus.FAILED:
                failed_from = episode.status.value
                failure_reason = reason

            cursor = self._db.execute(
                "UPDATE episodes SET status = ?, failed_from = ?, failure_reason = ?,"
                " title = COALESCE(?, title), version = version + 1, updated_at = ?"
                " WHERE id = ? AND version = ?",
                (
                    target.value,
                    failed_from,
                    failure_reason,
                    title,
                    to_iso(self._clock.now()),
                    episode_id,
                    episode.version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError(f"episode {episode_id} diubah proses lain")

            data: dict[str, Any] = {
                "from": episode.status.value,
                "to": target.value,
                "trigger": trigger.value,
                "version": episode.version + 1,
            }
            if reason:
                data["reason"] = reason
            self._audit.record(
                actor=actor,
                action="episode.transition",
                entity_type="episode",
                entity_id=episode_id,
                episode_id=episode_id,
                data=data,
            )
        return self.get(episode_id)
