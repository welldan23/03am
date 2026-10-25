from __future__ import annotations

from studio.bootstrap import App
from studio.modules.approvals import Approval, Decision
from studio.modules.episodes import Category, Episode, EpisodeStatus
from tests.conftest import OWNER


def run_worker(app: App, worker_id: str = "test-worker") -> int:
    return app.worker(worker_id).run_until_idle()


def pending_approval(app: App, episode_id: str) -> Approval:
    pending = app.approvals.pending(episode_id)
    assert len(pending) == 1, pending
    return pending[0]


def new_started_episode(app: App, *, duration: int = 60) -> Episode:
    episode = app.workflow.create_episode(
        category=Category.SEJARAH, target_duration_s=duration, idea="uji", actor=OWNER
    )
    return app.workflow.start(episode.id, OWNER)


def approve(app: App, episode_id: str, **kwargs: object) -> Episode:
    approval = pending_approval(app, episode_id)
    return app.workflow.decide(approval.id, Decision.APPROVE, actor=OWNER, **kwargs)  # type: ignore[arg-type]


def drive_to(app: App, episode_id: str, target: EpisodeStatus) -> Episode:
    """Jalankan worker + approve semua gate sampai episode mencapai `target`."""
    for _ in range(40):
        run_worker(app)
        episode = app.episodes.get(episode_id)
        if episode.status is target:
            return episode
        choice = 1 if episode.status is EpisodeStatus.AWAITING_TOPIC else None
        approve(app, episode_id, choice=choice)
    raise AssertionError(f"tidak mencapai {target}")
