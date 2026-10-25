"""Worker sinkron: klaim job → jalankan handler + tandai selesai dalam SATU transaksi.

Kalau proses mati di tengah handler, transaksi di-rollback dan job diambil ulang setelah
lease habis, jadi efek handler (artefak, ledger, transisi) tidak pernah tercatat dua kali.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum

from studio.infra.db import Database
from studio.infra.jobs.queue import Job, JobQueue, JobStatus, LeaseLostError
from studio.shared.errors import NonRetryableError
from studio.shared.logging import get_logger


class JobOutcome(StrEnum):
    DONE = "done"
    OBSOLETE = "obsolete"


Handler = Callable[[Job], JobOutcome]
DeadLetterHook = Callable[[Job, str], None]

_log = get_logger("studio.jobs")


class Worker:
    def __init__(
        self,
        db: Database,
        queue: JobQueue,
        handlers: Mapping[str, Handler],
        *,
        worker_id: str,
        lease_seconds: int,
        on_dead: DeadLetterHook | None = None,
    ) -> None:
        self._db = db
        self._queue = queue
        self._handlers = handlers
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._on_dead = on_dead

    def _dead(self, job: Job, error: str) -> None:
        """Hook dead-letter. Selalu dipanggil di DALAM transaksi yang menandai job `failed`,
        supaya status job dan efek hook (misalnya episode → FAILED) tidak pernah terpisah."""
        _log.warning("job.dead", job_id=job.id, job_type=job.type, error=error)
        if self._on_dead is not None:
            self._on_dead(job, error)

    def run_once(self) -> Job | None:
        """Proses satu job. Mengembalikan job yang diklaim, atau None kalau antrean kosong."""
        with self._db.transaction():
            for exhausted in self._queue.reap_exhausted():
                self._dead(exhausted, exhausted.last_error or "lease habis")

        job = self._queue.claim(self._worker_id, self._lease_seconds)
        if job is None:
            return None

        handler = self._handlers.get(job.type)
        try:
            if handler is None:
                raise NonRetryableError(f"tidak ada handler untuk job '{job.type}'")
            with self._db.transaction():
                outcome = handler(job)
                status = (
                    JobStatus.OBSOLETE if outcome is JobOutcome.OBSOLETE else JobStatus.SUCCEEDED
                )
                self._queue.complete(job.id, self._worker_id, job.lease_token, status)
            _log.info("job.completed", job_id=job.id, job_type=job.type, outcome=outcome.value)
        except LeaseLostError:
            _log.warning("job.lease_lost", job_id=job.id)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            try:
                with self._db.transaction():
                    failed = self._queue.fail(
                        job.id,
                        self._worker_id,
                        job.lease_token,
                        error,
                        retryable=not isinstance(exc, NonRetryableError),
                    )
                    if failed.status is JobStatus.FAILED:
                        self._dead(failed, error)
            except LeaseLostError:
                _log.warning("job.lease_lost", job_id=job.id)
                return job
            if failed.status is not JobStatus.FAILED:
                _log.info("job.retry_scheduled", job_id=job.id, attempts=failed.attempts)
        return job

    def run_until_idle(self, max_jobs: int = 1000) -> int:
        """Proses job sampai tidak ada job yang siap. Job dengan backoff di masa depan dilewati."""
        processed = 0
        while processed < max_jobs and self.run_once() is not None:
            processed += 1
        return processed
