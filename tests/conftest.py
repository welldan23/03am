from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from studio.bootstrap import App, LLMProviderFactory, build_app
from studio.shared.actors import Actor
from studio.shared.clock import FakeClock
from studio.shared.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
# 09:00 WIB, 3 November 2026 → periode anggaran "2026-11".
START = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
OWNER = Actor.owner("cli:owner")
DIRECTOR = Actor.director("hermes")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test tidak boleh terpengaruh .env / env developer."""
    import os

    for name in list(os.environ):
        if name.startswith("STUDIO_") or name == "PAID_PROVIDERS_ENABLED":
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    target.mkdir()
    for path in sorted((REPO_ROOT / "config").glob("*.yaml")):
        shutil.copy(path, target / path.name)
    return target


def edit_budget(config_dir: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    path = config_dir / "budget.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


AppFactory = Callable[..., App]


@pytest.fixture
def make_app(tmp_path: Path, config_dir: Path, clock: FakeClock) -> Iterator[AppFactory]:
    apps: list[App] = []

    def factory(
        *,
        llm_provider_factory: LLMProviderFactory | None = None,
        source_provider: Any = None,
        **overrides: Any,
    ) -> App:
        values: dict[str, Any] = {
            "data_dir": tmp_path / "data",
            "config_dir": config_dir,
            "owner_ids": "cli:owner",
        }
        values.update(overrides)
        app = build_app(
            Settings(_env_file=None, **values),  # type: ignore[call-arg]
            clock=clock,
            llm_provider_factory=llm_provider_factory,
            source_provider=source_provider,
        )
        apps.append(app)
        return app

    yield factory
    for app in apps:
        app.close()


@pytest.fixture
def app(make_app: AppFactory) -> App:
    return make_app()


@pytest.fixture
def active_app(app: App) -> App:
    """App dengan periode anggaran bulan berjalan sudah diaktifkan owner."""
    app.budget.activate_period(OWNER)
    return app
