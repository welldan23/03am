import io
import subprocess
import sys
from pathlib import Path

import pytest

from studio.bootstrap import App
from studio.interfaces.cli.main import main, parse_actor
from studio.modules.budget import Mode
from studio.modules.episodes import EpisodeStatus
from studio.shared.actors import ActorKind
from studio.shared.config import Settings
from tests.conftest import REPO_ROOT


def run(app: App, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = main(list(argv), app=app, out=out)
    return code, out.getvalue()


def test_module_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "studio", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0
    assert "03:AM" in result.stdout


def test_parse_actor() -> None:
    assert parse_actor("cli:owner").kind is ActorKind.OWNER
    assert parse_actor("director:hermes").kind is ActorKind.DIRECTOR
    assert parse_actor("system:x").kind is ActorKind.SYSTEM


def test_budget_plan_and_recalc_output(app: App) -> None:
    code, text = run(app, "budget", "plan")
    assert code == 0
    assert "Rp169.575" in text and "Rp500.000" in text and "VALID" in text
    assert "DIBLOKIR" in text  # API berbayar belum boleh aktif
    code, text = run(app, "budget", "recalc", "--vps-usd", "11.00")
    assert code == 0
    assert "reserve: 28650" in text and "USULAN" in text


def test_full_flow_via_cli_only(app: App) -> None:
    """AC1.21: DRAFT → EXPORTED hanya lewat perintah CLI, biaya nyata Rp0."""

    def ok(*argv: str) -> str:
        code, text = run(app, *argv)
        assert code == 0, text
        return text

    ok("budget", "activate")
    created = ok("episode", "new", "--category", "geopolitik", "--duration", "90")
    episode_id = created.split()[2]
    ok("episode", "start", episode_id)

    for _ in range(6):
        ok("worker", "run")
        status = app.episodes.get(episode_id).status
        if status is EpisodeStatus.EXPORTED:
            break
        (approval,) = app.approvals.pending(episode_id)
        ok("approval", "show", approval.id)
        extra = ["--choice", "2"] if status is EpisodeStatus.AWAITING_TOPIC else []
        ok("approval", "approve", approval.id, *extra)

    assert app.episodes.get(episode_id).status is EpisodeStatus.EXPORTED
    assert "EXPORTED" in ok("episode", "show", episode_id)
    assert "episode.transition" in ok("episode", "history", episode_id)
    assert "simulated" in ok("budget", "ledger", "--episode", episode_id)
    assert app.budget.status(Mode.REAL).used_idr == 0
    ok("budget", "status")
    ok("jobs", "list")


def test_director_cannot_approve_via_cli(app: App) -> None:
    run(app, "budget", "activate")
    _, created = run(app, "episode", "new", "--category", "sains", "--duration", "30")
    episode_id = created.split()[2]
    run(app, "episode", "start", episode_id)
    run(app, "worker", "run")
    (approval,) = app.approvals.pending(episode_id)
    code, text = run(
        app, "--actor", "director:hermes", "approval", "approve", approval.id, "--choice", "1"
    )
    assert code == 1
    assert "tidak berhak" in text
    code, text = run(app, "--actor", "director:hermes", "budget", "activate")
    assert code == 1


def test_paid_providers_flag_refuses_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, config_dir: Path
) -> None:
    monkeypatch.setenv("PAID_PROVIDERS_ENABLED", "true")
    settings = Settings(_env_file=None, data_dir=tmp_path / "d", config_dir=config_dir)  # type: ignore[call-arg]
    assert settings.paid_providers_enabled
    out = io.StringIO()
    assert main(["budget", "plan"], settings=settings, out=out) == 2
    assert "PAID_PROVIDERS_ENABLED=true ditolak" in out.getvalue()
    assert not (tmp_path / "d").exists()  # ditolak sebelum database dibuat


def test_database_errors_are_reported_without_traceback(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    from studio.interfaces.cli import main as cli

    def locked(*_: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(cli, "cmd_budget_status", locked)
    code, text = run(app, "budget", "status")
    assert code == 1
    assert "database is locked" in text
