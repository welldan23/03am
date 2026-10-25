import threading
from datetime import timedelta
from pathlib import Path

import pytest

from studio.bootstrap import App
from studio.infra.db import Database
from studio.infra.jobs import (
    Job,
    JobOutcome,
    JobQueue,
    JobStatus,
    LeaseLostError,
    Worker,
    atomic,
)
from studio.shared.clock import FakeClock
from studio.shared.errors import NonRetryableError
from tests.conftest import OWNER

LEASE = 60


@pytest.fixture
def queue(app: App, clock: FakeClock) -> JobQueue:
    return JobQueue(app.db, clock, default_max_attempts=3, backoff_base_seconds=5)


def _claim(queue: JobQueue, worker_id: str) -> Job:
    job = queue.claim(worker_id, LEASE)
    assert job is not None
    return job


def _worker(app: App, queue: JobQueue, handler, dead: list[tuple[str, str]], wid: str = "w1"):  # type: ignore[no-untyped-def]
    return Worker(
        app.db,
        queue,
        {"t": atomic(handler)},
        worker_id=wid,
        lease_seconds=LEASE,
        on_dead=lambda job, err: dead.append((job.id, err)),
    )


def test_enqueue_is_idempotent(queue: JobQueue) -> None:
    first = queue.enqueue("t", {"a": 1}, idempotency_key="k")
    again = queue.enqueue("t", {"a": 2}, idempotency_key="k")
    assert again.id == first.id
    assert again.payload == {"a": 1}
    assert len(queue.list_jobs()) == 1


def test_claim_increments_fencing_token(queue: JobQueue, clock: FakeClock) -> None:
    queue.enqueue("t", {}, idempotency_key="k")
    first = _claim(queue, "w1")
    assert first.status is JobStatus.RUNNING and first.attempts == 1 and first.lease_token == 1
    assert queue.claim("w2", LEASE) is None  # lease masih dipegang w1
    clock.advance(timedelta(seconds=LEASE))
    second = _claim(queue, "w2")
    assert second.lease_token == 2 and second.attempts == 2


def test_claim_and_complete_with_valid_lease(queue: JobQueue) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    claimed = _claim(queue, "w1")
    with pytest.raises(LeaseLostError):
        queue.complete(job.id, "w2", claimed.lease_token)  # worker lain
    with pytest.raises(LeaseLostError):
        queue.complete(job.id, "w1", claimed.lease_token + 1)  # token salah
    assert queue.complete(job.id, "w1", claimed.lease_token).status is JobStatus.SUCCEEDED
    with pytest.raises(LeaseLostError, match="succeeded"):
        queue.complete(job.id, "w1", claimed.lease_token)  # sudah selesai


# --- regresi: lease kedaluwarsa ------------------------------------------------


def test_expired_lease_cannot_complete_even_if_not_reclaimed(
    queue: JobQueue, clock: FakeClock
) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    claimed = _claim(queue, "w1")
    clock.advance(timedelta(seconds=LEASE))  # tepat di batas = sudah habis
    with pytest.raises(LeaseLostError, match="kedaluwarsa"):
        queue.complete(job.id, "w1", claimed.lease_token)
    with pytest.raises(LeaseLostError, match="kedaluwarsa"):
        queue.fail(job.id, "w1", claimed.lease_token, "x", retryable=True)
    assert queue.get(job.id).status is JobStatus.RUNNING  # tetap bisa diklaim ulang
    assert _claim(queue, "w2").lease_token == 2


def test_lease_valid_until_just_before_expiry(queue: JobQueue, clock: FakeClock) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    claimed = _claim(queue, "w1")
    clock.advance(timedelta(seconds=LEASE - 1))
    assert queue.complete(job.id, "w1", claimed.lease_token).status is JobStatus.SUCCEEDED


# --- regresi: worker basi (stale) -------------------------------------------------


def test_stale_worker_cannot_finish_after_reclaim(queue: JobQueue, clock: FakeClock) -> None:
    job = queue.enqueue("t", {}, idempotency_key="k")
    stale = _claim(queue, "w1")
    clock.advance(timedelta(seconds=LEASE + 1))
    fresh = _claim(queue, "w2")
    with pytest.raises(LeaseLostError, match="diambil w2"):
        queue.complete(job.id, "w1", stale.lease_token)
    with pytest.raises(LeaseLostError):
        queue.fail(job.id, "w1", stale.lease_token, "x", retryable=False)
    assert queue.complete(job.id, "w2", fresh.lease_token).status is JobStatus.SUCCEEDED


def test_restarted_worker_with_same_id_is_fenced(queue: JobQueue, clock: FakeClock) -> None:
    """Worker yang di-restart memakai ID sama: hanya token terbaru yang sah."""
    job = queue.enqueue("t", {}, idempotency_key="k")
    old = _claim(queue, "w1")
    clock.advance(timedelta(seconds=LEASE + 1))
    new = _claim(queue, "w1")
    assert new.lease_token == old.lease_token + 1
    with pytest.raises(LeaseLostError):
        queue.complete(job.id, "w1", old.lease_token)
    assert queue.complete(job.id, "w1", new.lease_token).status is JobStatus.SUCCEEDED


def test_slow_handler_past_lease_is_rolled_back_and_redone_once(
    app: App, queue: JobQueue, clock: FakeClock
) -> None:
    """Handler yang lebih lama dari lease: efeknya dibatalkan, worker lain mengulang sekali."""
    runs: list[str] = []

    def handler(job: Job) -> JobOutcome:
        app.audit.record(actor=OWNER, action="efek", entity_type="job", entity_id=job.id)
        runs.append(job.lease_owner or "")
        if job.lease_owner == "slow":
            clock.advance(timedelta(seconds=LEASE + 1))  # kerja terlalu lama
        return JobOutcome.DONE

    job = queue.enqueue("t", {}, idempotency_key="k")
    _worker(app, queue, handler, [], "slow").run_once()
    assert app.audit.entries(action="efek") == []  # efek di-rollback
    assert queue.get(job.id).status is JobStatus.RUNNING

    _worker(app, queue, handler, [], "fast").run_until_idle()
    assert len(app.audit.entries(action="efek")) == 1
    final = queue.get(job.id)
    assert final.status is JobStatus.SUCCEEDED and final.attempts == 2
    assert runs == ["slow", "fast"]


# --- regresi: klaim bersamaan ------------------------------------------------------


def test_concurrent_claims_never_hand_out_a_job_twice(
    app: App, clock: FakeClock, tmp_path: Path
) -> None:
    for i in range(30):
        JobQueue(app.db, clock).enqueue("t", {"i": i}, idempotency_key=f"k{i}")

    claimed: list[tuple[str, str]] = []
    lock = threading.Lock()
    errors: list[BaseException] = []

    def run(worker_id: str) -> None:
        db = Database(app.db.path, busy_timeout_ms=10_000)
        local = JobQueue(db, clock)
        try:
            while (job := local.claim(worker_id, LEASE)) is not None:
                with lock:
                    claimed.append((job.id, worker_id))
                local.complete(job.id, worker_id, job.lease_token)
        except BaseException as exc:
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=run, args=(f"w{n}",)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    ids = [job_id for job_id, _ in claimed]
    assert len(ids) == 30 == len(set(ids))
    assert all(j.status is JobStatus.SUCCEEDED for j in JobQueue(app.db, clock).list_jobs())


# --- retry, dead letter, crash ------------------------------------------------------


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

    assert queue.get(job.id).status is JobStatus.FAILED
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


def test_worker_crash_rolls_back_effects_and_recovers_once(
    app: App, queue: JobQueue, clock: FakeClock
) -> None:
    crash = {"on": True}

    def handler(job: Job) -> JobOutcome:
        app.audit.record(actor=OWNER, action="efek", entity_type="job", entity_id=job.id)
        if crash["on"]:
            raise KeyboardInterrupt  # proses mati, bukan exception biasa
        return JobOutcome.DONE

    job = queue.enqueue("t", {}, idempotency_key="k")
    with pytest.raises(KeyboardInterrupt):
        _worker(app, queue, handler, [], "w1").run_once()
    assert app.audit.entries(action="efek") == []
    assert queue.get(job.id).status is JobStatus.RUNNING

    crash["on"] = False
    clock.advance(timedelta(seconds=LEASE + 1))
    _worker(app, queue, handler, [], "w2").run_until_idle()
    _worker(app, queue, handler, [], "w3").run_until_idle()  # tidak ada pengulangan lagi
    assert len(app.audit.entries(action="efek")) == 1
    final = queue.get(job.id)
    assert final.status is JobStatus.SUCCEEDED and final.attempts == 2


def test_crash_loop_ends_in_dead_letter(app: App, queue: JobQueue, clock: FakeClock) -> None:
    def handler(job: Job) -> JobOutcome:
        raise KeyboardInterrupt

    dead: list[tuple[str, str]] = []
    job = queue.enqueue("t", {}, idempotency_key="k", max_attempts=2)
    for wid in ("w1", "w2"):
        with pytest.raises(KeyboardInterrupt):
            _worker(app, queue, handler, dead, wid).run_once()
        clock.advance(timedelta(seconds=LEASE + 1))
    assert _worker(app, queue, handler, dead, "w3").run_once() is None
    reaped = queue.get(job.id)
    assert reaped.status is JobStatus.FAILED
    assert reaped.lease_token == 3  # token dinaikkan: worker lama pasti tertolak
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


def test_dead_letter_hook_is_atomic_with_job_failure(
    app: App, queue: JobQueue, clock: FakeClock
) -> None:
    """Kalau hook dead-letter gagal, job TIDAK boleh tercatat `failed` sendirian."""
    hook_calls: list[str] = []

    def hook(job: Job, error: str) -> None:
        hook_calls.append(job.id)
        app.audit.record(actor=OWNER, action="hook", entity_type="job", entity_id=job.id)
        if len(hook_calls) == 1:
            raise RuntimeError("database sibuk")

    def broken(job: Job) -> JobOutcome:
        raise NonRetryableError("gagal permanen")

    worker = Worker(
        app.db, queue, {"t": atomic(broken)}, worker_id="w1", lease_seconds=LEASE, on_dead=hook
    )
    job = queue.enqueue("t", {}, idempotency_key="k", max_attempts=2)
    with pytest.raises(RuntimeError, match="sibuk"):
        worker.run_once()
    assert queue.get(job.id).status is JobStatus.RUNNING  # tidak 'failed' tanpa efek hook
    assert app.audit.entries(action="hook") == []

    clock.advance(timedelta(seconds=LEASE))
    worker.run_once()
    assert queue.get(job.id).status is JobStatus.FAILED
    assert len(app.audit.entries(action="hook")) == 1
