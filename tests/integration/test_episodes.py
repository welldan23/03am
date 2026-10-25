import pytest

from studio.bootstrap import App
from studio.modules.episodes import Category, EpisodeStatus, IllegalTransitionError, Trigger
from studio.shared.errors import ConflictError
from tests.conftest import OWNER


def _episode(app: App):  # type: ignore[no-untyped-def]
    return app.episodes.create(
        category=Category.MISTERI, target_duration_s=90, idea="segitiga", actor=OWNER
    )


@pytest.mark.parametrize("duration", [29, 181])
def test_duration_bounds(app: App, duration: int) -> None:
    with pytest.raises(ValueError):
        app.episodes.create(
            category=Category.SAINS, target_duration_s=duration, idea=None, actor=OWNER
        )


def test_each_transition_writes_exactly_one_audit_entry(app: App) -> None:
    episode = _episode(app)
    app.episodes.transition(
        episode.id, trigger=Trigger.START, target=EpisodeStatus.DISCOVERING, actor=OWNER
    )
    updated = app.episodes.transition(
        episode.id, trigger=Trigger.COMPLETE, target=EpisodeStatus.AWAITING_TOPIC, actor=OWNER
    )
    entries = app.audit.entries(episode_id=episode.id, action="episode.transition")
    assert len(entries) == 2 == updated.version - 1
    last = entries[-1]
    assert last.actor == "owner:cli:owner"
    assert last.data == {
        "from": "DISCOVERING",
        "to": "AWAITING_TOPIC",
        "trigger": "complete",
        "version": 3,
    }
    assert last.at.tzinfo is not None


def test_illegal_transition_changes_nothing(app: App) -> None:
    episode = _episode(app)
    with pytest.raises(IllegalTransitionError):
        app.episodes.transition(
            episode.id, trigger=Trigger.APPROVE, target=EpisodeStatus.RESEARCHING, actor=OWNER
        )
    assert app.episodes.get(episode.id) == episode
    assert app.audit.entries(episode_id=episode.id, action="episode.transition") == []


def test_optimistic_lock_rejects_stale_version(app: App) -> None:
    episode = _episode(app)
    app.episodes.transition(
        episode.id, trigger=Trigger.START, target=EpisodeStatus.DISCOVERING, actor=OWNER
    )
    with pytest.raises(ConflictError):
        app.episodes.transition(
            episode.id,
            trigger=Trigger.CANCEL,
            target=EpisodeStatus.CANCELLED,
            actor=OWNER,
            expected_version=episode.version,
        )


def test_fail_records_origin_and_retry_must_return_there(app: App) -> None:
    episode = _episode(app)
    app.episodes.transition(
        episode.id, trigger=Trigger.START, target=EpisodeStatus.DISCOVERING, actor=OWNER
    )
    failed = app.episodes.transition(
        episode.id, trigger=Trigger.FAIL, target=EpisodeStatus.FAILED, actor=OWNER, reason="boom"
    )
    assert failed.failed_from is EpisodeStatus.DISCOVERING
    assert failed.failure_reason == "boom"
    with pytest.raises(ConflictError):
        app.episodes.transition(
            episode.id, trigger=Trigger.RETRY, target=EpisodeStatus.RESEARCHING, actor=OWNER
        )
    retried = app.episodes.transition(
        episode.id, trigger=Trigger.RETRY, target=EpisodeStatus.DISCOVERING, actor=OWNER
    )
    assert retried.failed_from is None and retried.failure_reason is None
