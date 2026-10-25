from datetime import timedelta
from pathlib import Path

import pytest

from studio.bootstrap import App
from studio.infra.jobs import Job, JobOutcome, JobStatus, Worker
from studio.modules.approvals import (
    ApprovalExpiredError,
    ApprovalStatus,
    Decision,
    StaleApprovalError,
)
from studio.modules.artifacts import ArtifactKind
from studio.modules.budget import AuthorizationKind, BudgetExceededError, Mode
from studio.modules.episodes import EpisodeStatus as S
from studio.modules.workflow import STAGE_JOB, WorkflowError, placeholders
from studio.shared.clock import FakeClock
from studio.shared.errors import NotAuthorizedError
from studio.shared.gates import Gate
from tests.conftest import DIRECTOR, OWNER, AppFactory, edit_budget
from tests.helpers import approve, drive_to, new_started_episode, pending_approval, run_worker


def test_full_flow_to_exported_with_simulated_costs_only(active_app: App) -> None:
    app = active_app
    episode = new_started_episode(app, duration=60)
    final = drive_to(app, episode.id, S.EXPORTED)

    assert final.title == "[PLACEHOLDER] Topik sejarah #1"
    statuses = [
        e.data["to"] for e in app.audit.entries(episode_id=episode.id, action="episode.transition")
    ]
    assert statuses == [
        "DISCOVERING",
        "AWAITING_TOPIC",
        "RESEARCHING",
        "FACT_CHECKING",
        "SCRIPTING",
        "STORYBOARDING",
        "AWAITING_EDITORIAL",
        "ESTIMATING_COST",
        "AWAITING_COST",
        "GENERATING_ASSETS",
        "GENERATING_VOICE",
        "RENDERING",
        "AWAITING_FINAL",
        "EXPORTING",
        "EXPORTED",
    ]
    assert len(statuses) == final.version - 1

    ledger = app.budget.ledger(episode_id=episode.id)
    assert ledger and all(e.mode is Mode.SIMULATED for e in ledger)
    assert all(e.fx_usd_idr == "17850" for e in ledger)
    real = app.budget.status(Mode.REAL)
    assert real.used_idr == 0
    estimate = app.artifacts.latest(episode.id, ArtifactKind.COST_ESTIMATE)
    assert estimate is not None
    production = sum(
        e.actual_idr or 0 for e in ledger if e.purpose.startswith(("higgsfield", "tts"))
    )
    assert production == estimate.content["total_idr"] <= estimate.content["cap_idr"]
    assert [a.gate for a in app.approvals.for_episode(episode.id)] == list(Gate)


def test_topic_choice_is_required_and_validated(active_app: App) -> None:
    episode = new_started_episode(active_app)
    run_worker(active_app)
    with pytest.raises(WorkflowError, match="pilih topik"):
        approve(active_app, episode.id)
    with pytest.raises(WorkflowError):
        approve(active_app, episode.id, choice=9)
    updated = approve(active_app, episode.id, choice=3)
    assert updated.status is S.RESEARCHING
    assert active_app.budget.episode_authorization(episode.id, AuthorizationKind.PREPRODUCTION)


@pytest.mark.parametrize(
    "gate_status", [S.AWAITING_TOPIC, S.AWAITING_EDITORIAL, S.AWAITING_COST, S.AWAITING_FINAL]
)
def test_director_can_never_decide_a_gate(active_app: App, gate_status: S) -> None:
    episode = new_started_episode(active_app)
    drive_to(active_app, episode.id, gate_status)
    approval = pending_approval(active_app, episode.id)
    for decision in Decision:
        with pytest.raises(NotAuthorizedError):
            active_app.workflow.decide(
                approval.id,
                decision,
                actor=DIRECTOR,
                choice=1,
                notes="x",
                revise_to=S.RESEARCHING if gate_status is not S.AWAITING_TOPIC else S.DISCOVERING,
            )
    assert active_app.episodes.get(episode.id).status is gate_status
    assert active_app.approvals.get(approval.id).status is ApprovalStatus.PENDING


def test_revision_at_final_gate_invalidates_editorial_and_cost(active_app: App) -> None:
    app = active_app
    episode = new_started_episode(app)
    drive_to(app, episode.id, S.AWAITING_FINAL)
    production = app.budget.episode_authorization(episode.id, AuthorizationKind.PRODUCTION)
    assert production is not None

    final_approval = pending_approval(app, episode.id)
    revised = app.workflow.decide(
        final_approval.id,
        Decision.REVISE,
        actor=OWNER,
        revise_to=S.SCRIPTING,
        notes="hook lebih misterius",
    )
    assert revised.status is S.SCRIPTING

    by_gate = {a.gate: a.status for a in app.approvals.for_episode(episode.id)}
    assert by_gate[Gate.TOPIC] is ApprovalStatus.APPROVED
    assert by_gate[Gate.EDITORIAL] is ApprovalStatus.SUPERSEDED
    assert by_gate[Gate.COST] is ApprovalStatus.SUPERSEDED
    assert by_gate[Gate.FINAL] is ApprovalStatus.REVISION_REQUESTED
    assert app.budget.episode_authorization(episode.id, AuthorizationKind.PRODUCTION) is None
    assert app.budget.episode_authorization(episode.id, AuthorizationKind.PREPRODUCTION)

    run_worker(app)
    script = app.artifacts.latest(episode.id, ArtifactKind.SCRIPT)
    assert script is not None and script.version == 2
    assert script.content["notes"] == "hook lebih misterius"
    assert app.episodes.get(episode.id).status is S.AWAITING_EDITORIAL
    assert pending_approval(app, episode.id).gate is Gate.EDITORIAL


def test_revision_target_must_be_before_gate(active_app: App) -> None:
    episode = new_started_episode(active_app)
    drive_to(active_app, episode.id, S.AWAITING_EDITORIAL)
    approval = pending_approval(active_app, episode.id)
    with pytest.raises(WorkflowError, match="target revisi"):
        active_app.workflow.decide(
            approval.id, Decision.REVISE, actor=OWNER, revise_to=S.RENDERING, notes="x"
        )


def test_changed_content_makes_card_stale_and_issues_new_one(active_app: App) -> None:
    app = active_app
    episode = new_started_episode(app)
    drive_to(app, episode.id, S.AWAITING_EDITORIAL)
    old = pending_approval(app, episode.id)
    # Konten berubah di luar alur normal (misal hasil edit) → hash subjek berbeda.
    app.artifacts.put(episode.id, ArtifactKind.SCRIPT, {"text": "versi lain"}, OWNER)

    with pytest.raises(StaleApprovalError) as info:
        app.workflow.decide(old.id, Decision.APPROVE, actor=OWNER)
    assert app.approvals.get(old.id).status is ApprovalStatus.SUPERSEDED
    replacement = pending_approval(app, episode.id)
    assert info.value.replacement_id == replacement.id
    assert replacement.subject["script"]["version"] == 2
    assert app.workflow.decide(replacement.id, Decision.APPROVE, actor=OWNER).status is (
        S.ESTIMATING_COST
    )


def test_expired_approval_can_be_reissued(active_app: App, clock: FakeClock) -> None:
    episode = new_started_episode(active_app)
    run_worker(active_app)
    old = pending_approval(active_app, episode.id)
    clock.advance(timedelta(hours=73))
    with pytest.raises(ApprovalExpiredError):
        active_app.workflow.decide(old.id, Decision.APPROVE, actor=OWNER, choice=1)
    with pytest.raises(NotAuthorizedError):
        active_app.workflow.reissue_approval(episode.id, DIRECTOR)
    new = active_app.workflow.reissue_approval(episode.id, OWNER)
    assert new.id != old.id
    assert active_app.workflow.decide(new.id, Decision.APPROVE, actor=OWNER, choice=1).status is (
        S.RESEARCHING
    )


def test_cost_approval_refused_when_budget_insufficient(
    make_app: AppFactory, config_dir: Path
) -> None:
    edit_budget(config_dir, lambda d: d["allocations_idr"].__setitem__("higgsfield", 10_000))
    app = make_app()
    app.budget.activate_period(OWNER)
    episode = new_started_episode(app)
    drive_to(app, episode.id, S.AWAITING_COST)
    approval = pending_approval(app, episode.id)
    with pytest.raises(BudgetExceededError, match="higgsfield"):
        app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER)
    assert app.episodes.get(episode.id).status is S.AWAITING_COST
    assert app.approvals.get(approval.id).status is ApprovalStatus.PENDING
    assert app.budget.episode_authorization(episode.id, AuthorizationKind.PRODUCTION) is None
    (denied,) = app.audit.entries(episode_id=episode.id, action="budget.denied")
    assert denied.entity_id == approval.id and "higgsfield" in denied.data["reason"]


def test_crash_mid_stage_has_no_double_effects(active_app: App, clock: FakeClock) -> None:
    app = active_app
    episode = new_started_episode(app)

    def crash_after_work(job: Job) -> JobOutcome:
        app.workflow.handle_stage_job(job)  # artefak + ledger + transisi + job berikutnya
        raise KeyboardInterrupt  # proses mati sebelum commit

    crashing = Worker(
        app.db,
        app.queue,
        {STAGE_JOB: crash_after_work},
        worker_id="w1",
        lease_seconds=app.settings.worker_lease_seconds,
    )
    with pytest.raises(KeyboardInterrupt):
        crashing.run_once()
    assert app.artifacts.latest(episode.id, ArtifactKind.TOPICS) is None
    assert app.budget.ledger(episode_id=episode.id) == []
    assert app.episodes.get(episode.id).status is S.DISCOVERING

    clock.advance(timedelta(seconds=app.settings.worker_lease_seconds + 1))
    run_worker(app, "w2")
    assert len(app.artifacts.versions(episode.id, ArtifactKind.TOPICS)) == 1
    assert len(app.budget.ledger(episode_id=episode.id)) == 1
    assert app.episodes.get(episode.id).status is S.AWAITING_TOPIC
    (job,) = app.queue.list_jobs(episode_id=episode.id)
    assert job.status is JobStatus.SUCCEEDED and job.attempts == 2


def test_stale_job_is_obsolete_without_effects(active_app: App) -> None:
    episode = new_started_episode(active_app)
    stale = active_app.queue.enqueue(
        STAGE_JOB,
        {"episode_id": episode.id, "expected_status": "DISCOVERING", "expected_version": 1},
        idempotency_key="stale",
        episode_id=episode.id,
    )
    run_worker(active_app)
    assert active_app.queue.get(stale.id).status is JobStatus.OBSOLETE
    assert len(active_app.artifacts.versions(episode.id, ArtifactKind.TOPICS)) == 1
    assert active_app.audit.entries(action="job.obsolete")


def test_budget_denial_fails_episode_without_retry(make_app: AppFactory, config_dir: Path) -> None:
    edit_budget(config_dir, lambda d: d["limits"].__setitem__("preproduction_cap_idr", 100))
    app = make_app()
    app.budget.activate_period(OWNER)
    episode = new_started_episode(app)
    run_worker(app)
    approve(app, episode.id, choice=1)
    run_worker(app)
    failed = app.episodes.get(episode.id)
    assert failed.status is S.FAILED
    assert failed.failed_from is S.FACT_CHECKING
    assert failed.failure_reason is not None and "batas otorisasi" in failed.failure_reason
    jobs = app.queue.list_jobs(episode_id=episode.id, status=JobStatus.FAILED)
    assert len(jobs) == 1 and jobs[0].attempts == 1
    # Penolakan di dalam handler di-rollback bersama handler, tapi alasannya tetap tercatat.
    (dead,) = app.audit.entries(episode_id=episode.id, action="job.dead")
    assert "BudgetExceededError" in dead.data["error"]
    assert "batas otorisasi" in dead.data["error"]


def test_no_active_period_blocks_discovery(app: App) -> None:
    episode = new_started_episode(app)
    run_worker(app)
    failed = app.episodes.get(episode.id)
    assert failed.status is S.FAILED
    assert "otorisasi operational" in (failed.failure_reason or "")


def test_transient_failures_then_owner_retry(
    active_app: App, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(ctx: placeholders.StageContext) -> None:
        raise RuntimeError("provider mock sedang error")

    monkeypatch.setitem(placeholders.PLACEHOLDER_STAGES, S.DISCOVERING, broken)  # type: ignore[index]
    episode = new_started_episode(active_app)
    for _ in range(3):
        run_worker(active_app)
        clock.advance(timedelta(minutes=1))
    failed = active_app.episodes.get(episode.id)
    assert failed.status is S.FAILED and failed.failed_from is S.DISCOVERING

    monkeypatch.undo()
    with pytest.raises(NotAuthorizedError):
        active_app.workflow.retry(episode.id, DIRECTOR)
    assert active_app.workflow.retry(episode.id, OWNER).status is S.DISCOVERING
    run_worker(active_app)
    assert active_app.episodes.get(episode.id).status is S.AWAITING_TOPIC


def test_reject_closes_episode_and_revokes_spending(active_app: App) -> None:
    episode = new_started_episode(active_app)
    drive_to(active_app, episode.id, S.AWAITING_EDITORIAL)
    approval = pending_approval(active_app, episode.id)
    rejected = active_app.workflow.decide(
        approval.id, Decision.REJECT, actor=OWNER, notes="topik terlalu sensitif"
    )
    assert rejected.status is S.REJECTED
    assert (
        active_app.budget.episode_authorization(episode.id, AuthorizationKind.PREPRODUCTION) is None
    )
    assert active_app.queue.list_jobs(episode_id=episode.id, status=JobStatus.QUEUED) == []


def test_cancel_supersedes_pending_and_cancels_jobs(active_app: App) -> None:
    episode = new_started_episode(active_app)
    with pytest.raises(NotAuthorizedError):
        active_app.workflow.cancel(episode.id, DIRECTOR)
    cancelled = active_app.workflow.cancel(episode.id, OWNER)
    assert cancelled.status is S.CANCELLED
    (job,) = active_app.queue.list_jobs(episode_id=episode.id)
    assert job.status is JobStatus.CANCELLED


def test_director_may_create_and_start_but_system_may_not(active_app: App) -> None:
    from studio.modules.episodes import Category
    from studio.shared.actors import Actor

    episode = active_app.workflow.create_episode(
        category=Category.SAINS, target_duration_s=45, idea=None, actor=DIRECTOR
    )
    assert active_app.workflow.start(episode.id, DIRECTOR).status is S.DISCOVERING
    with pytest.raises(NotAuthorizedError):
        active_app.workflow.create_episode(
            category=Category.SAINS, target_duration_s=45, idea=None, actor=Actor.system("x")
        )
