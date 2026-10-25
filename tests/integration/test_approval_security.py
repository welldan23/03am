"""Regresi keamanan approval G0–G3 (audit Fase 1)."""

import contextlib
import io
import sqlite3
import threading
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from studio.bootstrap import App
from studio.interfaces.cli.main import main
from studio.modules.approvals import (
    ApprovalExpiredError,
    ApprovalNotPendingError,
    ApprovalStatus,
    Decision,
    InvalidApprovalTokenError,
    StaleApprovalError,
    compute_subject_hash,
)
from studio.modules.artifacts import ArtifactKind
from studio.modules.budget import AuthorizationKind
from studio.modules.episodes import EpisodeStatus as S
from studio.modules.episodes import Trigger, state
from studio.modules.workflow import STAGE_JOB
from studio.shared.actors import Actor
from studio.shared.clock import FakeClock
from studio.shared.errors import NotAuthorizedError, StudioError
from tests.conftest import DIRECTOR, OWNER, AppFactory
from tests.helpers import drive_to, new_started_episode, pending_approval, run_worker

GATES = [S.AWAITING_TOPIC, S.AWAITING_EDITORIAL, S.AWAITING_COST, S.AWAITING_FINAL]
NOT_OWNERS = [
    DIRECTOR,
    Actor.system("workflow"),
    Actor.owner("cli:penyusup"),  # format owner, tapi tidak ada di allowlist
    Actor.owner("telegram:999"),
]


def _at_gate(app: App, gate_status: S) -> str:
    episode = new_started_episode(app)
    drive_to(app, episode.id, gate_status)
    return episode.id


def _revise_target(gate_status: S) -> S:
    return S.DISCOVERING if gate_status is S.AWAITING_TOPIC else S.RESEARCHING


# --- hanya owner -----------------------------------------------------------------


@pytest.mark.parametrize("gate_status", GATES, ids=lambda s: s.value)
@pytest.mark.parametrize("actor", NOT_OWNERS, ids=lambda a: a.label)
def test_only_allowlisted_owner_can_decide(active_app: App, gate_status: S, actor: Actor) -> None:
    episode_id = _at_gate(active_app, gate_status)
    approval = pending_approval(active_app, episode_id)
    for decision in Decision:
        with pytest.raises(NotAuthorizedError):
            active_app.workflow.decide(
                approval.id,
                decision,
                actor=actor,
                choice=1,
                notes="x",
                revise_to=_revise_target(gate_status),
            )
    assert active_app.episodes.get(episode_id).status is gate_status
    assert active_app.approvals.get(approval.id).status is ApprovalStatus.PENDING
    assert len(active_app.audit.entries(action="approval.refused")) == len(Decision)


def test_empty_allowlist_means_nobody_can_decide(make_app: AppFactory) -> None:
    setup = make_app()
    setup.budget.activate_period(OWNER)
    episode_id = _at_gate(setup, S.AWAITING_TOPIC)
    locked = make_app(owner_ids="")  # app kedua, database sama, allowlist kosong
    approval = pending_approval(locked, episode_id)
    with pytest.raises(NotAuthorizedError):
        locked.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER, choice=1)
    with pytest.raises(NotAuthorizedError):
        locked.budget.activate_period(OWNER)


@pytest.mark.parametrize("actor", NOT_OWNERS, ids=lambda a: a.label)
def test_privileged_services_reject_non_owner(active_app: App, actor: Actor) -> None:
    episode = new_started_episode(active_app)
    calls: list[Callable[[], object]] = [
        lambda: active_app.workflow.cancel(episode.id, actor),
        lambda: active_app.workflow.retry(episode.id, actor),
        lambda: active_app.workflow.reissue_approval(episode.id, actor),
        lambda: active_app.budget.activate_period(actor),
        lambda: active_app.budget.authorize_episode(
            episode_id=episode.id,
            kind=AuthorizationKind.PRODUCTION,
            approval_id="x",
            max_idr=1,
            actor=actor,
        ),
    ]
    for call in calls:
        with pytest.raises(NotAuthorizedError):
            call()
    assert active_app.episodes.get(episode.id).status is S.DISCOVERING


# --- tidak ada jalur internal yang melewati gate ---------------------------------------


@pytest.mark.parametrize("gate_status", GATES, ids=lambda s: s.value)
def test_gate_cannot_be_left_without_recorded_decision(active_app: App, gate_status: S) -> None:
    """Memanggil EpisodeService langsung (melewati workflow & approval) ditolak database."""
    episode_id = _at_gate(active_app, gate_status)
    attempts = [
        (Trigger.APPROVE, state_next(gate_status)),
        (Trigger.REJECT, S.REJECTED),
        (Trigger.REVISE, _revise_target(gate_status)),
    ]
    for trigger, target in attempts:
        with pytest.raises(sqlite3.DatabaseError, match="recorded owner decision"):
            active_app.episodes.transition(episode_id, trigger=trigger, target=target, actor=OWNER)
    assert active_app.episodes.get(episode_id).status is gate_status


def state_next(gate_status: S) -> S:
    return state.NEXT_ON_APPROVE[gate_status]


def test_decision_of_one_kind_does_not_unlock_another_direction(active_app: App) -> None:
    episode_id = _at_gate(active_app, S.AWAITING_EDITORIAL)
    approval = pending_approval(active_app, episode_id)
    # Keputusan "tolak" tercatat lewat service approval saja (tanpa workflow)...
    subject_hash = compute_subject_hash(
        episode_id=episode_id,
        gate=approval.gate,
        subject=approval.subject,
        spend_cap_idr=approval.spend_cap_idr,
    )
    assert active_app.approvals.decide(
        approval.id,
        Decision.REJECT,
        actor=OWNER,
        current_subject_hash=subject_hash,
        current_episode_version=approval.episode_version,
    ).accepted
    # ...tidak bisa dipakai untuk melanjutkan produksi.
    with pytest.raises(sqlite3.DatabaseError, match="recorded owner decision"):
        active_app.episodes.transition(
            episode_id, trigger=Trigger.APPROVE, target=S.ESTIMATING_COST, actor=OWNER
        )


def test_cancel_at_gate_is_allowed_for_owner(active_app: App) -> None:
    episode_id = _at_gate(active_app, S.AWAITING_COST)
    assert active_app.workflow.cancel(episode_id, OWNER).status is S.CANCELLED


# --- token sekali pakai ---------------------------------------------------------------


def test_token_is_single_use_through_workflow(active_app: App) -> None:
    episode_id = _at_gate(active_app, S.AWAITING_EDITORIAL)
    approval = pending_approval(active_app, episode_id)
    token = active_app.approvals.issue_token(approval.id, Actor.system("telegram"))
    assert (
        active_app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER, token=token).status
        is S.ESTIMATING_COST
    )
    with pytest.raises(ApprovalNotPendingError):
        active_app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER, token=token)
    assert len(active_app.audit.entries(action="approval.decided")) == 2  # G0 + G1 saja


def test_token_of_one_approval_cannot_decide_another(active_app: App) -> None:
    first = pending_approval(active_app, _at_gate(active_app, S.AWAITING_EDITORIAL))
    second = pending_approval(active_app, _at_gate(active_app, S.AWAITING_EDITORIAL))
    token_first = active_app.approvals.issue_token(first.id, Actor.system("telegram"))
    active_app.approvals.issue_token(second.id, Actor.system("telegram"))
    with pytest.raises(InvalidApprovalTokenError):
        active_app.workflow.decide(second.id, Decision.APPROVE, actor=OWNER, token=token_first)
    assert active_app.approvals.get(second.id).status is ApprovalStatus.PENDING


def test_rotated_token_and_expired_token_are_rejected(active_app: App, clock: FakeClock) -> None:
    approval = pending_approval(active_app, _at_gate(active_app, S.AWAITING_EDITORIAL))
    old = active_app.approvals.issue_token(approval.id, Actor.system("telegram"))
    new = active_app.approvals.issue_token(approval.id, Actor.system("telegram"))
    with pytest.raises(InvalidApprovalTokenError):
        active_app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER, token=old)
    clock.advance(timedelta(hours=72))
    with pytest.raises(ApprovalExpiredError):
        active_app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER, token=new)
    assert active_app.approvals.get(approval.id).status is ApprovalStatus.EXPIRED


def test_valid_token_does_not_replace_owner_check(active_app: App) -> None:
    approval = pending_approval(active_app, _at_gate(active_app, S.AWAITING_EDITORIAL))
    token = active_app.approvals.issue_token(approval.id, Actor.system("telegram"))
    with pytest.raises(NotAuthorizedError):
        active_app.workflow.decide(approval.id, Decision.APPROVE, actor=DIRECTOR, token=token)


# --- approval lama tidak berlaku setelah revisi ----------------------------------------


def test_old_cards_are_dead_after_revision(active_app: App) -> None:
    app = active_app
    episode_id = _at_gate(app, S.AWAITING_FINAL)
    editorial = next(a for a in app.approvals.for_episode(episode_id) if a.gate.value == "G1")
    final = pending_approval(app, episode_id)
    final_token = app.approvals.issue_token(final.id, Actor.system("telegram"))
    app.workflow.decide(
        final.id, Decision.REVISE, actor=OWNER, revise_to=S.SCRIPTING, notes="ubah hook"
    )
    run_worker(app)  # naskah v2 → kembali ke G1 dengan kartu baru

    assert app.approvals.get(editorial.id).status is ApprovalStatus.SUPERSEDED
    with pytest.raises(ApprovalNotPendingError):
        app.workflow.decide(editorial.id, Decision.APPROVE, actor=OWNER)
    with pytest.raises(ApprovalNotPendingError):
        app.workflow.decide(final.id, Decision.APPROVE, actor=OWNER, token=final_token)
    new_card = pending_approval(app, episode_id)
    assert new_card.id != editorial.id
    assert new_card.subject["script"]["version"] == 2


def test_card_is_stale_when_content_changes_before_decision(active_app: App) -> None:
    episode_id = _at_gate(active_app, S.AWAITING_COST)
    card = pending_approval(active_app, episode_id)
    active_app.artifacts.put(
        episode_id,
        ArtifactKind.COST_ESTIMATE,
        {
            **active_app.artifacts.latest(
                episode_id,  # type: ignore[union-attr]
                ArtifactKind.COST_ESTIMATE,
            ).content,
            "cap_idr": 1,
        },
        OWNER,
    )
    with pytest.raises(StaleApprovalError):
        active_app.workflow.decide(card.id, Decision.APPROVE, actor=OWNER)
    assert active_app.budget.episode_authorization(episode_id, AuthorizationKind.PRODUCTION) is None
    assert active_app.episodes.get(episode_id).status is S.AWAITING_COST


# --- keputusan bersamaan -----------------------------------------------------------


def test_concurrent_approvals_execute_once(make_app: AppFactory) -> None:
    primary = make_app()
    primary.budget.activate_period(OWNER)
    episode_id = _at_gate(primary, S.AWAITING_EDITORIAL)
    approval = pending_approval(primary, episode_id)
    version_before = primary.episodes.get(episode_id).version
    apps = [make_app() for _ in range(6)]  # 6 proses/koneksi berbeda ke database yang sama

    outcomes: list[str] = []
    lock = threading.Lock()

    def click(app: App) -> None:
        try:
            app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER)
            result = "ok"
        except StudioError as exc:
            result = type(exc).__name__
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=click, args=(a,)) for a in apps]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["ApprovalNotPendingError"] * 5 + ["ok"]
    episode = primary.episodes.get(episode_id)
    assert episode.status is S.ESTIMATING_COST and episode.version == version_before + 1
    decided = [
        e for e in primary.audit.entries(action="approval.decided") if e.entity_id == approval.id
    ]
    assert len(decided) == 1
    stage_jobs = [
        j
        for j in primary.queue.list_jobs(episode_id=episode_id)
        if j.type == STAGE_JOB and j.payload["expected_status"] == "ESTIMATING_COST"
    ]
    assert len(stage_jobs) == 1


def test_concurrent_cost_approvals_create_one_authorization(make_app: AppFactory) -> None:
    primary = make_app()
    primary.budget.activate_period(OWNER)
    episode_id = _at_gate(primary, S.AWAITING_COST)
    approval = pending_approval(primary, episode_id)
    apps = [make_app() for _ in range(4)]
    threads = [
        threading.Thread(
            target=lambda a=a: _swallow(
                lambda: a.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER)
            )
        )
        for a in apps
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = primary.db.query_all(
        "SELECT * FROM spend_authorizations WHERE episode_id = ? AND kind = 'production'",
        (episode_id,),
    )
    assert len(rows) == 1


def _swallow(call: Callable[[], object]) -> None:
    with contextlib.suppress(StudioError):
        call()


# --- CLI ------------------------------------------------------------------------------


def _cli(app: App, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return main(list(argv), app=app, out=out), out.getvalue()


def test_cli_cannot_impersonate_other_channels(make_app: AppFactory) -> None:
    app = make_app(owner_ids="cli:owner,telegram:123")
    app.budget.activate_period(OWNER)
    approval = pending_approval(app, _at_gate(app, S.AWAITING_EDITORIAL))
    for actor in ("telegram:123", "owner", "cli:"):
        code, text = _cli(app, "--actor", actor, "approval", "approve", approval.id)
        assert code == 1 and "actor CLI tidak sah" in text
    assert app.approvals.get(approval.id).status is ApprovalStatus.PENDING


def test_cli_owner_must_still_be_allowlisted(make_app: AppFactory, tmp_path: Path) -> None:
    setup = make_app()
    setup.budget.activate_period(OWNER)
    approval = pending_approval(setup, _at_gate(setup, S.AWAITING_EDITORIAL))
    telegram_only = make_app(owner_ids="telegram:123")
    code, text = _cli(telegram_only, "approval", "approve", approval.id)
    assert code == 1 and "tidak berhak" in text
    code, _ = _cli(telegram_only, "budget", "activate")
    assert code == 1
