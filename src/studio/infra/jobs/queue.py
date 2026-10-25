"""Antrean job di SQLite dengan lease.

- `claim` mengambil job `queued` yang sudah waktunya, atau job `running` yang lease-nya
  habis (worker sebelumnya crash). `attempts` naik setiap kali diklaim.
- `complete`/`fail` hanya berhasil kalau lease masih dipegang worker yang sama.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from studio.infra.db import Database
from studio.shared.clock import Clock, from_iso, to_iso
from studio.shared.errors import NotFoundError, StudioError
from studio.shared.ids import new_id


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OBSOLETE = "obsolete"
    CANCELLED = "cancelled"


class LeaseLostError(StudioError):
    """Lease job sudah tidak dipegang worker ini (diambil worker lain atau sudah selesai)."""


@dataclass(frozen=True)
class Job:
    id: str
    type: str
    episode_id: str | None
    payload: dict[str, Any]
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    lease_owner: str | None
    lease_until: datetime | None
    idempotency_key: str
    last_error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        return cls(
            id=row["id"],
            type=row["type"],
            episode_id=row["episode_id"],
            payload=json.loads(row["payload"]),
            status=JobStatus(row["status"]),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            run_after=from_iso(row["run_after"]),
            lease_owner=row["lease_owner"],
            lease_until=from_iso(row["lease_until"]) if row["lease_until"] else None,
            idempotency_key=row["idempotency_key"],
            last_error=row["last_error"],
        )


class JobQueue:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        *,
        default_max_attempts: int = 3,
        backoff_base_seconds: int = 5,
    ) -> None:
        self._db = db
        self._clock = clock
        self._default_max_attempts = default_max_attempts
        self._backoff_base = backoff_base_seconds

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        episode_id: str | None = None,
        max_attempts: int | None = None,
        run_after: datetime | None = None,
    ) -> Job:
        """Masukkan job. Kalau idempotency key sudah ada, kembalikan job yang lama."""
        with self._db.transaction():
            existing = self._db.query_one(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)
            )
            if existing is not None:
                return Job.from_row(existing)
            now = to_iso(self._clock.now())
            job_id = new_id(self._clock)
            self._db.execute(
                "INSERT INTO jobs (id, type, episode_id, payload, status, attempts, max_attempts,"
                " run_after, idempotency_key, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    job_type,
                    episode_id,
                    json.dumps(payload, sort_keys=True),
                    max_attempts or self._default_max_attempts,
                    to_iso(run_after or self._clock.now()),
                    idempotency_key,
                    now,
                    now,
                ),
            )
            return self.get(job_id)

    def get(self, job_id: str) -> Job:
        row = self._db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if row is None:
            raise NotFoundError(f"job {job_id} tidak ditemukan")
        return Job.from_row(row)

    def list_jobs(
        self, status: JobStatus | None = None, episode_id: str | None = None
    ) -> list[Job]:
        sql = "SELECT * FROM jobs WHERE 1 = 1"
        params: list[Any] = []
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        if episode_id is not None:
            sql += " AND episode_id = ?"
            params.append(episode_id)
        return [Job.from_row(r) for r in self._db.query_all(sql + " ORDER BY created_at", params)]

    def reap_exhausted(self) -> list[Job]:
        """Job `running` yang lease-nya habis dan jatah attempt-nya sudah habis → `failed`."""
        now = to_iso(self._clock.now())
        with self._db.transaction():
            rows = self._db.query_all(
                "SELECT * FROM jobs WHERE status = 'running' AND lease_until < ?"
                " AND attempts >= max_attempts",
                (now,),
            )
            for row in rows:
                self._db.execute(
                    "UPDATE jobs SET status = 'failed', lease_owner = NULL, lease_until = NULL,"
                    " last_error = ?, updated_at = ? WHERE id = ?",
                    (
                        "lease habis setelah jatah attempt habis (worker crash berulang)",
                        now,
                        row["id"],
                    ),
                )
        return [self.get(row["id"]) for row in rows]

    def claim(self, worker_id: str, lease_seconds: int) -> Job | None:
        now_dt = self._clock.now()
        now = to_iso(now_dt)
        with self._db.transaction():
            row = self._db.query_one(
                "SELECT id FROM jobs"
                " WHERE (status = 'queued' AND run_after <= ?)"
                "    OR (status = 'running' AND lease_until < ? AND attempts < max_attempts)"
                " ORDER BY run_after, created_at LIMIT 1",
                (now, now),
            )
            if row is None:
                return None
            self._db.execute(
                "UPDATE jobs SET status = 'running', attempts = attempts + 1, lease_owner = ?,"
                " lease_until = ?, updated_at = ? WHERE id = ?",
                (worker_id, to_iso(now_dt + timedelta(seconds=lease_seconds)), now, row["id"]),
            )
            return self.get(row["id"])

    def _assert_lease(self, job_id: str, worker_id: str) -> Job:
        job = self.get(job_id)
        if job.status is not JobStatus.RUNNING or job.lease_owner != worker_id:
            raise LeaseLostError(f"job {job_id} tidak lagi dipegang {worker_id}")
        return job

    def complete(self, job_id: str, worker_id: str, status: JobStatus = JobStatus.SUCCEEDED) -> Job:
        if status not in (JobStatus.SUCCEEDED, JobStatus.OBSOLETE):
            raise ValueError("complete hanya untuk succeeded/obsolete")
        with self._db.transaction():
            self._assert_lease(job_id, worker_id)
            self._db.execute(
                "UPDATE jobs SET status = ?, lease_owner = NULL, lease_until = NULL,"
                " last_error = NULL, updated_at = ? WHERE id = ?",
                (status.value, to_iso(self._clock.now()), job_id),
            )
            return self.get(job_id)

    def fail(self, job_id: str, worker_id: str, error: str, *, retryable: bool) -> Job:
        """Catat kegagalan: antre ulang dengan backoff, atau `failed` kalau tidak bisa diulang."""
        with self._db.transaction():
            job = self._assert_lease(job_id, worker_id)
            now_dt = self._clock.now()
            if retryable and job.attempts < job.max_attempts:
                delay = self._backoff_base * (2 ** (job.attempts - 1))
                self._db.execute(
                    "UPDATE jobs SET status = 'queued', lease_owner = NULL, lease_until = NULL,"
                    " run_after = ?, last_error = ?, updated_at = ? WHERE id = ?",
                    (to_iso(now_dt + timedelta(seconds=delay)), error, to_iso(now_dt), job_id),
                )
            else:
                self._db.execute(
                    "UPDATE jobs SET status = 'failed', lease_owner = NULL, lease_until = NULL,"
                    " last_error = ?, updated_at = ? WHERE id = ?",
                    (error, to_iso(now_dt), job_id),
                )
            return self.get(job_id)

    def cancel_for_episode(self, episode_id: str) -> int:
        """Batalkan job episode yang masih antre. Job yang sedang jalan akan jadi obsolete."""
        cursor = self._db.execute(
            "UPDATE jobs SET status = 'cancelled', updated_at = ?"
            " WHERE episode_id = ? AND status = 'queued'",
            (to_iso(self._clock.now()), episode_id),
        )
        return cursor.rowcount
