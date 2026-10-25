"""TD-01: eksekusi dua fase — handler di luar transaksi, hasil diterima lewat Lease.finish."""

from datetime import timedelta

import pytest

from studio.bootstrap import App
from studio.infra.jobs import (
    Job,
    JobExecutionError,
    JobOutcome,
    JobQueue,
    JobStatus,
    Lease,
    LeaseLostError,
    Worker,
)
from studio.shared.clock import FakeClock
from tests.conftest import OWNER

LEASE = 60


@pytest.fixture
def queue(app: App, clock: FakeClock) -> JobQueue:
    return JobQueue(app.db, clock)


def _worker(app: App, queue: JobQueue, handler, wid: str = "w1") -> Worker:  # type: ignore[no-untyped-def]
    return Worker(app.db, queue, {"t": handler}, worker_id=wid, lease_seconds=LEASE)


def test_handler_runs_outside_any_transaction(app: App, queue: JobQueue) -> None:
    seen: list[bool] = []

    def handler(job: Job, lease: Lease) -> JobOutcome:
        seen.append(app.db.in_transaction)
        lease.require_outside_transaction("panggilan provider")  # tidak melempar
        return lease.finish(lambda: JobOutcome.DONE)

    queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, handler).run_once()
    assert seen == [False]


def test_external_work_inside_transaction_is_refused(app: App) -> None:
    job = JobQueue(app.db, FakeClock(app.clock.now())).enqueue("t", {}, idempotency_key="k")
    lease = Lease(app.db, JobQueue(app.db, app.clock), job, worker_id="w", lease_seconds=LEASE)
    with app.db.transaction(), pytest.raises(JobExecutionError, match="di dalam transaksi"):
        lease.require_outside_transaction("panggilan provider")


def test_heartbeat_extends_a_valid_lease(app: App, queue: JobQueue, clock: FakeClock) -> None:
    def handler(job: Job, lease: Lease) -> JobOutcome:
        clock.advance(timedelta(seconds=LEASE - 5))
        lease.heartbeat()  # masih sah → diperpanjang 60 detik dari sekarang
        clock.advance(timedelta(seconds=LEASE - 5))  # total 110 detik > lease awal
        return lease.finish(lambda: JobOutcome.DONE)

    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, handler).run_once()
    assert queue.get(job.id).status is JobStatus.SUCCEEDED


def test_heartbeat_cannot_revive_an_expired_lease(
    app: App, queue: JobQueue, clock: FakeClock
) -> None:
    def handler(job: Job, lease: Lease) -> JobOutcome:
        clock.advance(timedelta(seconds=LEASE))
        lease.heartbeat()
        return lease.finish(lambda: JobOutcome.DONE)  # pragma: no cover

    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, handler).run_once()
    assert queue.get(job.id).status is JobStatus.RUNNING  # tidak diselesaikan worker basi


def test_stale_worker_result_is_not_accepted(app: App, queue: JobQueue, clock: FakeClock) -> None:
    """Worker lambat menyelesaikan kerja eksternal setelah job diambil worker lain."""

    def slow(job: Job, lease: Lease) -> JobOutcome:
        clock.advance(timedelta(seconds=LEASE + 1))
        # Worker lain mengambil alih dan menyelesaikan lebih dulu.
        _worker(app, queue, fast, "w2").run_once()

        def write() -> JobOutcome:
            app.audit.record(actor=OWNER, action="hasil", entity_type="job", entity_id="lambat")
            return JobOutcome.DONE

        return lease.finish(write)

    def fast(job: Job, lease: Lease) -> JobOutcome:
        def write() -> JobOutcome:
            app.audit.record(actor=OWNER, action="hasil", entity_type="job", entity_id="cepat")
            return JobOutcome.DONE

        return lease.finish(write)

    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, slow, "w1").run_once()
    assert [e.entity_id for e in app.audit.entries(action="hasil")] == ["cepat"]
    assert queue.get(job.id).status is JobStatus.SUCCEEDED


def test_handler_that_never_finishes_is_retried(app: App, queue: JobQueue) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, lambda j, lease: JobOutcome.DONE).run_once()
    reloaded = queue.get(job.id)
    assert reloaded.status is JobStatus.QUEUED
    assert "lease.finish" in (reloaded.last_error or "")


def test_finish_twice_is_refused(app: App, queue: JobQueue) -> None:
    errors: list[Exception] = []

    def handler(job: Job, lease: Lease) -> JobOutcome:
        outcome = lease.finish(lambda: JobOutcome.DONE)
        try:
            lease.finish(lambda: JobOutcome.DONE)
        except JobExecutionError as exc:
            errors.append(exc)
        return outcome

    queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, handler).run_once()
    assert len(errors) == 1


def test_obsolete_outcome_through_finish(app: App, queue: JobQueue) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, lambda j, lease: lease.finish(lambda: JobOutcome.OBSOLETE)).run_once()
    assert queue.get(job.id).status is JobStatus.OBSOLETE


def test_lease_lost_error_from_heartbeat_message(app: App, queue: JobQueue) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    claimed = queue.claim("w1", LEASE)
    assert claimed is not None
    with pytest.raises(LeaseLostError):
        queue.heartbeat(job.id, "w2", claimed.lease_token, LEASE)
