from datetime import timedelta

import pytest

from studio.bootstrap import App
from studio.modules.approvals import (
    Approval,
    ApprovalStatus,
    Decision,
    DecisionOutcome,
    compute_subject_hash,
)
from studio.modules.episodes import Category
from studio.shared.actors import Actor
from studio.shared.clock import FakeClock
from studio.shared.gates import Gate
from tests.conftest import DIRECTOR, OWNER

SUBJECT = {"script": {"version": 1, "hash": "abc"}}


@pytest.fixture
def approval(app: App) -> Approval:
    episode = app.episodes.create(
        category=Category.GEOGRAFI, target_duration_s=60, idea=None, actor=OWNER
    )
    return app.approvals.request(
        episode_id=episode.id,
        gate=Gate.EDITORIAL,
        episode_version=episode.version,
        subject=SUBJECT,
        spend_cap_idr=None,
        actor=Actor.system(),
    )


def _hash(approval: Approval, subject: dict[str, object] = SUBJECT) -> str:
    return compute_subject_hash(
        episode_id=approval.episode_id,
        gate=approval.gate,
        subject=subject,
        spend_cap_idr=approval.spend_cap_idr,
    )


def _decide(app: App, approval: Approval, *, actor: Actor = OWNER, **kwargs: object):  # type: ignore[no-untyped-def]
    params: dict[str, object] = {
        "current_subject_hash": _hash(approval),
        "current_episode_version": approval.episode_version,
    }
    params.update(kwargs)
    return app.approvals.decide(approval.id, Decision.APPROVE, actor=actor, **params)  # type: ignore[arg-type]


def test_owner_can_approve_matching_subject(app: App, approval: Approval) -> None:
    result = _decide(app, approval, notes="ok")
    assert result.outcome is DecisionOutcome.ACCEPTED
    assert result.approval.status is ApprovalStatus.APPROVED
    assert result.approval.decided_by == "owner:cli:owner"


@pytest.mark.parametrize(
    "actor",
    [DIRECTOR, Actor.system("workflow"), Actor.owner("telegram:999")],
    ids=["director", "system", "owner-luar-allowlist"],
)
def test_non_owner_cannot_decide(app: App, approval: Approval, actor: Actor) -> None:
    result = _decide(app, approval, actor=actor)
    assert result.outcome is DecisionOutcome.NOT_AUTHORIZED
    assert app.approvals.get(approval.id).status is ApprovalStatus.PENDING
    refused = app.audit.entries(action="approval.refused")
    assert refused[-1].actor == actor.label


def test_changed_subject_makes_approval_stale(app: App, approval: Approval) -> None:
    changed = {"script": {"version": 2, "hash": "def"}}
    result = _decide(app, approval, current_subject_hash=_hash(approval, changed))
    assert result.outcome is DecisionOutcome.STALE
    assert app.approvals.get(approval.id).status is ApprovalStatus.SUPERSEDED


def test_changed_episode_version_makes_approval_stale(app: App, approval: Approval) -> None:
    result = _decide(app, approval, current_episode_version=approval.episode_version + 1)
    assert result.outcome is DecisionOutcome.STALE


def test_double_decision_processed_once(app: App, approval: Approval) -> None:
    assert _decide(app, approval).accepted
    second = _decide(app, approval)
    assert second.outcome is DecisionOutcome.NOT_PENDING
    assert len(app.audit.entries(action="approval.decided")) == 1


def test_expired_approval_is_refused(app: App, approval: Approval, clock: FakeClock) -> None:
    clock.advance(timedelta(hours=72))
    result = _decide(app, approval)
    assert result.outcome is DecisionOutcome.EXPIRED
    assert app.approvals.get(approval.id).status is ApprovalStatus.EXPIRED


def test_token_is_single_use_and_rotates(app: App, approval: Approval) -> None:
    old_token = app.approvals.issue_token(approval.id, Actor.system("telegram"))
    new_token = app.approvals.issue_token(approval.id, Actor.system("telegram"))
    assert app.approvals.find_by_token(old_token) is None
    assert app.approvals.find_by_token(new_token) == app.approvals.get(approval.id)

    assert _decide(app, approval, token=old_token).outcome is DecisionOutcome.INVALID_TOKEN
    assert _decide(app, approval, token="palsu").outcome is DecisionOutcome.INVALID_TOKEN
    assert _decide(app, approval, token=new_token).accepted
    # Setelah diputuskan, token tidak bisa dipakai lagi.
    assert app.approvals.find_by_token(new_token) is None
    assert _decide(app, approval, token=new_token).outcome is DecisionOutcome.NOT_PENDING


def test_new_request_supersedes_pending(app: App, approval: Approval) -> None:
    replacement = app.approvals.request(
        episode_id=approval.episode_id,
        gate=approval.gate,
        episode_version=approval.episode_version,
        subject=SUBJECT,
        spend_cap_idr=None,
        actor=Actor.system(),
    )
    assert app.approvals.get(approval.id).status is ApprovalStatus.SUPERSEDED
    assert app.approvals.pending(approval.episode_id) == [replacement]


def test_spend_cap_is_part_of_subject_hash(approval: Approval) -> None:
    base = compute_subject_hash(episode_id="e", gate=Gate.COST, subject=SUBJECT, spend_cap_idr=1)
    other = compute_subject_hash(episode_id="e", gate=Gate.COST, subject=SUBJECT, spend_cap_idr=2)
    assert base != other


def test_final_decision_cannot_be_rewritten(app: App, approval: Approval) -> None:
    assert _decide(app, approval).accepted
    import sqlite3

    with pytest.raises(sqlite3.DatabaseError, match="final"):
        app.db.execute("UPDATE approvals SET status = 'pending' WHERE id = ?", (approval.id,))
