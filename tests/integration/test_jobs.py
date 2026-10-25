from datetime import timedelta

import pytest

from studio.bootstrap import App
from studio.infra.jobs import Job, JobOutcome, JobQueue, JobStatus, LeaseLostError, Worker
from studio.shared.clock import FakeClock
from studio.shared.errors import NonRetryableError
from tests.conftest import OWNER


@pytest.fixture
def queue(app: App, clock: FakeClock) -> JobQueue:
    return JobQueue(app.db, clock, default_max_attempts=3, backoff_base_seconds=5)


def _worker(app: App, queue: JobQueue, handler, dead: list[tuple[str, str]], wid: str = "w1"):  # type: ignore[no-untyped-def]
    return Worker(
        app.db,
        queue,
        {"t": handler},
        worker_id=wid,
        lease_seconds=60,
        on_dead=lambda job, err: dead.append((job.id, err)),
    )


def test_enqueue_is_idempotent(queue: JobQueue) -> None:
    first = queue.enqueue("t", {"a": 1}, idempotency_key="k")
    again = queue.enqueue("t", {"a": 2}, idempotency_key="k")
    assert again.id == first.id
    assert again.payload == {"a": 1}
    assert len(queue.list_jobs()) == 1


def test_claim_and_complete(queue: JobQueue) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    claimed = queue.claim("w1", 60)
    assert claimed is not None and claimed.id == job.id
    assert claimed.status is JobStatus.RUNNING and claimed.attempts == 1
    assert queue.claim("w2", 60) is None  # lease masih dipegang w1
    with pytest.raises(LeaseLostError):
        queue.complete(job.id, "w2")
    assert queue.complete(job.id, "w1").status is JobStatus.SUCCEEDED


def test_expired_lease_is_reclaimed_and_old_worker_cannot_finish(
    queue: JobQueue, clock: FakeClock
) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    queue.claim("w1", 60)  # w1 "crash"
    clock.advance(timedelta(seconds=61))
    reclaimed = queue.claim("w2", 60)
    assert reclaimed is not None and reclaimed.id == job.id and reclaimed.attempts == 2
    with pytest.raises(LeaseLostError):
        queue.complete(job.id, "w1")
    assert queue.complete(job.id, "w2").status is JobStatus.SUCCEEDED


def test_retry_with_exponential_backoff_then_dead(
    app: App, queue: JobQueue, clock: FakeClock
) -> None:
    calls: list[int] = []

    def flaky(job: Job) -> JobOutcome:
        calls.append(job.attempts)
        raise RuntimeError("sementara")

    dead: list[tuple[str, str]] = []
    worker = _worker(app, queue, flaky, dead)
    job = queue.enqueue("t", {}, idempotency_key="k")

    worker.run_once()
    assert queue.get(job.id).status is JobStatus.QUEUED
    assert worker.run_once() is None  # backoff 5 detik belum lewat
    clock.advance(timedelta(seconds=5))
    worker.run_once()
    clock.advance(timedelta(seconds=9))
    assert worker.run_once() is None  # backoff kedua 10 detik
    clock.advance(timedelta(seconds=1))
    worker.run_once()

    final = queue.get(job.id)
    assert final.status is JobStatus.FAILED
    assert calls == [1, 2, 3]
    assert dead == [(job.id, "RuntimeError: sementara")]


def test_non_retryable_error_fails_immediately(app: App, queue: JobQueue) -> None:
    def broken(job: Job) -> JobOutcome:
        raise NonRetryableError("budget habis")

    dead: list[tuple[str, str]] = []
    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, broken, dead).run_once()
    assert queue.get(job.id).status is JobStatus.FAILED
    assert queue.get(job.id).attempts == 1
    assert len(dead) == 1


def test_missing_handler_is_dead_letter(app: App, queue: JobQueue) -> None:
    dead: list[tuple[str, str]] = []
    job = queue.enqueue("unknown", {}, idempotency_key="k")
    _worker(app, queue, lambda j: JobOutcome.DONE, dead).run_once()
    assert queue.get(job.id).status is JobStatus.FAILED
    assert "tidak ada handler" in dead[0][1]


def test_handler_effects_rolled_back_on_crash(app: App, queue: JobQueue, clock: FakeClock) -> None:
    """Crash di tengah handler: tidak ada efek tersimpan, job diulang tepat sekali."""
    crash = {"on": True}

    def handler(job: Job) -> JobOutcome:
        app.audit.record(actor=OWNER, action="efek", entity_type="job", entity_id=job.id)
        if crash["on"]:
            raise KeyboardInterrupt  # proses mati, bukan exception biasa
        return JobOutcome.DONE

    dead: list[tuple[str, str]] = []
    job = queue.enqueue("t", {}, idempotency_key="k")
    with pytest.raises(KeyboardInterrupt):
        _worker(app, queue, handler, dead, "w1").run_once()
    assert app.audit.entries(action="efek") == []
    assert queue.get(job.id).status is JobStatus.RUNNING

    crash["on"] = False
    clock.advance(timedelta(seconds=61))
    _worker(app, queue, handler, dead, "w2").run_until_idle()
    assert len(app.audit.entries(action="efek")) == 1
    assert queue.get(job.id).status is JobStatus.SUCCEEDED
    assert queue.get(job.id).attempts == 2


def test_crash_loop_ends_in_dead_letter(app: App, queue: JobQueue, clock: FakeClock) -> None:
    def handler(job: Job) -> JobOutcome:
        raise KeyboardInterrupt

    dead: list[tuple[str, str]] = []
    job = queue.enqueue("t", {}, idempotency_key="k", max_attempts=2)
    for wid in ("w1", "w2"):
        with pytest.raises(KeyboardInterrupt):
            _worker(app, queue, handler, dead, wid).run_once()
        clock.advance(timedelta(seconds=61))
    assert _worker(app, queue, handler, dead, "w3").run_once() is None
    assert queue.get(job.id).status is JobStatus.FAILED
    assert dead and dead[0][0] == job.id


def test_obsolete_outcome(app: App, queue: JobQueue) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, lambda j: JobOutcome.OBSOLETE, []).run_once()
    assert queue.get(job.id).status is JobStatus.OBSOLETE


def test_cancel_for_episode_only_touches_queued(queue: JobQueue) -> None:
    queued = queue.enqueue("t", {}, idempotency_key="a", episode_id="E1")
    other = queue.enqueue("t", {}, idempotency_key="b", episode_id="E2")
    assert queue.cancel_for_episode("E1") == 1
    assert queue.get(queued.id).status is JobStatus.CANCELLED
    assert queue.get(other.id).status is JobStatus.QUEUED
