"""Lease job yang dipegang handler selama eksekusi dua fase (TD-01).

Pola eksekusi:
1. transaksi singkat: validasi + reservasi/pencatatan request (oleh pemanggil);
2. pekerjaan eksternal di LUAR transaksi (tidak ada write lock SQLite yang ditahan);
3. `finish()`: transaksi singkat yang menulis hasil DAN menandai job selesai. Kalau lease
   sudah kedaluwarsa atau diambil worker lain, `complete` gagal dan seluruh hasil di-rollback.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from studio.infra.db import Database
from studio.infra.jobs.queue import Job, JobQueue, JobStatus
from studio.shared.errors import StudioError


class JobOutcome(StrEnum):
    DONE = "done"
    OBSOLETE = "obsolete"


class JobExecutionError(StudioError):
    """Kesalahan pemrograman pada handler (misalnya I/O di dalam transaksi)."""


class Lease:
    def __init__(
        self, db: Database, queue: JobQueue, job: Job, *, worker_id: str, lease_seconds: int
    ) -> None:
        self._db = db
        self._queue = queue
        self.job = job
        self.worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._finished = False

    @property
    def token(self) -> int:
        return self.job.lease_token

    @property
    def finished(self) -> bool:
        return self._finished

    def require_outside_transaction(self, what: str) -> None:
        """Pekerjaan eksternal tidak boleh berjalan sambil menahan transaksi SQLite."""
        if self._db.in_transaction:
            raise JobExecutionError(f"{what} tidak boleh dijalankan di dalam transaksi database")

    def heartbeat(self) -> None:
        """Validasi lease masih sah lalu perpanjang. Melempar `LeaseLostError` kalau tidak."""
        self._queue.heartbeat(self.job.id, self.worker_id, self.token, self._lease_seconds)

    def finish(self, work: Callable[[], JobOutcome]) -> JobOutcome:
        """Jalankan `work` dan tandai job selesai dalam SATU transaksi singkat.

        Status job (`succeeded`/`obsolete`) mengikuti hasil `work`. Pemeriksaan fencing token
        dan masa lease terjadi di `complete`; kalau gagal, semua tulisan `work` di-rollback.
        """
        if self._finished:
            raise JobExecutionError(f"job {self.job.id} sudah diselesaikan")
        self.require_outside_transaction("finish")
        with self._db.transaction():
            outcome = work()
            status = JobStatus.OBSOLETE if outcome is JobOutcome.OBSOLETE else JobStatus.SUCCEEDED
            self._queue.complete(self.job.id, self.worker_id, self.token, status)
        self._finished = True
        return outcome
