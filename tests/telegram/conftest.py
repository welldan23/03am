from __future__ import annotations

from collections.abc import Iterator

import pytest

from studio.bootstrap import App
from studio.shared.actors import Actor
from tests.conftest import AppFactory
from tests.telegram.fakes import OWNER_TG, Harness

TG_OWNER = Actor.owner(f"telegram:{OWNER_TG}")


@pytest.fixture
def tg_app(make_app: AppFactory) -> App:
    app = make_app(owner_ids=f"cli:owner,telegram:{OWNER_TG}")
    app.budget.activate_period(TG_OWNER)
    return app


@pytest.fixture
def harness(tg_app: App) -> Iterator[Harness]:
    h = Harness(tg_app)
    yield h
    h.close()
