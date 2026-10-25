from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from studio.bootstrap import App
from studio.modules.budget import (
    AuthorizationKind,
    BudgetExceededError,
    BudgetGuard,
    BudgetPlanError,
    Category,
    LedgerStateError,
    LedgerStatus,
    Mode,
    Source,
    SpendAuthorization,
    SpendRequest,
    load_plan,
)
from studio.modules.episodes import Category as EpisodeCategory
from studio.shared.clock import FakeClock
from studio.shared.errors import ConflictError, NotAuthorizedError
from studio.shared.gates import Gate
from studio.shared.ids import new_id
from tests.conftest import DIRECTOR, OWNER, AppFactory, edit_budget


def _operational(app: App) -> SpendAuthorization:
    auth = app.budget.operational_authorization()
    assert auth is not None
    return auth


def _request(
    auth: SpendAuthorization,
    usd_micros: int,
    *,
    key: str | None = None,
    category: Category = Category.OPENAI,
    source: Source = Source.STUDIO,
    purpose: str = "test",
    mode: Mode = Mode.SIMULATED,
    episode_id: str | None = None,
) -> SpendRequest:
    return SpendRequest(
        idempotency_key=key or new_id(),
        category=category,
        source=source,
        purpose=purpose,
        mode=mode,
        authorization_id=auth.id,
        usd_micros=usd_micros,
        price_ref="test:price",
        episode_id=episode_id if episode_id is not None else auth.episode_id,
    )


def _small_budget(config_dir: Path, **limits: int) -> None:
    def mutate(data: dict[str, Any]) -> None:
        data["allocations_idr"]["openai"] = limits.get("openai", 1000)
        data["limits"]["operational_cap_idr"] = limits.get("operational", 1000)

    edit_budget(config_dir, mutate)


# --- aktivasi ------------------------------------------------------------------


def test_only_owner_can_activate_period(app: App) -> None:
    with pytest.raises(NotAuthorizedError):
        app.budget.activate_period(DIRECTOR)
    period = app.budget.activate_period(OWNER)
    assert period.period == "2026-11"
    assert period.fx_usd_idr == "17850"
    assert period.plan["allocations_idr"]["openai"] == 60_000
    assert _operational(app).max_idr == 20_000
    assert app.audit.entries(action="budget.period_activated")


def test_invalid_plan_cannot_be_activated(make_app: AppFactory, config_dir: Path) -> None:
    edit_budget(config_dir, lambda d: d["fx"].__setitem__("usd_idr", "18000"))
    app = make_app()
    with pytest.raises(BudgetPlanError, match="melebihi"):
        app.budget.activate_period(OWNER)


def test_reactivation_keeps_usage(active_app: App) -> None:
    auth = _operational(active_app)
    active_app.guard.spend(_request(auth, 56_000))  # Rp1.000
    active_app.budget.activate_period(OWNER)
    assert _operational(active_app).id == auth.id
    assert active_app.budget.authorization_used(auth.id, Mode.SIMULATED) == 1_000


# --- reserve / commit / release -------------------------------------------------


def test_reserve_commit_stores_fx_and_price(active_app: App) -> None:
    entry = active_app.guard.reserve(_request(_operational(active_app), 1_000_000))  # $1
    assert entry.status is LedgerStatus.RESERVED
    assert entry.reserved_idr == 17_850
    assert entry.fx_usd_idr == "17850"
    assert entry.price_ref == "test:price"
    assert entry.period == "2026-11"
    committed = active_app.guard.commit(entry.id, 400_000)
    assert committed.status is LedgerStatus.COMMITTED
    assert committed.actual_idr == 7_140
    assert not committed.overrun


def test_release_and_double_settlement(active_app: App) -> None:
    entry = active_app.guard.reserve(_request(_operational(active_app), 1_000))
    active_app.guard.release(entry.id)
    with pytest.raises(LedgerStateError):
        active_app.guard.commit(entry.id, 1_000)
    with pytest.raises(LedgerStateError):
        active_app.guard.release(entry.id)


def test_overrun_is_flagged(active_app: App) -> None:
    entry = active_app.guard.reserve(_request(_operational(active_app), 1_000))
    assert active_app.guard.commit(entry.id, 100_000).overrun


def test_unknown_outcome_commits_reserved_amount(active_app: App) -> None:
    entry = active_app.guard.reserve(_request(_operational(active_app), 56_000))
    committed = active_app.guard.commit_at_reserved(entry.id)
    assert committed.actual_idr == committed.reserved_idr == 1_000


def test_reserve_is_idempotent(active_app: App) -> None:
    auth = _operational(active_app)
    first = active_app.guard.reserve(_request(auth, 1_000, key="k1"))
    again = active_app.guard.reserve(_request(auth, 1_000, key="k1"))
    assert again == first
    with pytest.raises(ConflictError):
        active_app.guard.reserve(_request(auth, 2_000, key="k1"))
    assert len(active_app.budget.ledger()) == 1


# --- penolakan (masing-masing aturan) -------------------------------------------


def _assert_denied(
    app: App, request: SpendRequest, reason: str, guard: BudgetGuard | None = None
) -> None:
    with pytest.raises(BudgetExceededError, match=reason):
        (guard or app.guard).reserve(request)
    denied = app.audit.entries(action="budget.denied")
    assert denied and reason.split()[0] in denied[-1].data["reason"]


def test_denied_when_period_not_active(app: App, clock: FakeClock) -> None:
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    clock.advance(timedelta(days=30))  # Desember belum diaktifkan
    _assert_denied(app, _request(auth, 1_000), "belum diaktifkan")


def test_operational_authorization_is_bound_to_its_period(app: App, clock: FakeClock) -> None:
    app.budget.activate_period(OWNER)
    november = _operational(app)
    clock.advance(timedelta(days=30))
    app.budget.activate_period(OWNER)
    _assert_denied(app, _request(november, 1_000), "bukan untuk periode")


def test_real_mode_denied_by_kill_switch(active_app: App) -> None:
    _assert_denied(
        active_app, _request(_operational(active_app), 1_000, mode=Mode.REAL), "kill switch"
    )


def test_real_mode_denied_until_paid_activation_ready(active_app: App, clock: FakeClock) -> None:
    guard = BudgetGuard(
        active_app.db, clock, active_app.audit, active_app.plan, paid_providers_enabled=True
    )
    _assert_denied(
        active_app,
        _request(_operational(active_app), 1_000, mode=Mode.REAL),
        "syarat aktivasi",
        guard,
    )


def test_denied_when_live_plan_becomes_invalid(
    active_app: App, config_dir: Path, clock: FakeClock
) -> None:
    edit_budget(config_dir, lambda d: d["vps"].__setitem__("actual_usd", "11.00"))
    guard = BudgetGuard(
        active_app.db,
        clock,
        active_app.audit,
        load_plan(config_dir / "budget.yaml"),
        paid_providers_enabled=False,
    )
    _assert_denied(active_app, _request(_operational(active_app), 1_000), "tidak valid", guard)


def test_denied_when_authorization_revoked_or_foreign(active_app: App) -> None:
    episodes = [
        active_app.episodes.create(
            category=EpisodeCategory.SAINS, target_duration_s=30, idea=None, actor=OWNER
        )
        for _ in range(2)
    ]
    approval_ids = []
    for ep in episodes:
        approval = active_app.approvals.request(
            episode_id=ep.id,
            gate=Gate.TOPIC,
            episode_version=1,
            subject={},
            spend_cap_idr=5_000,
            actor=OWNER,
        )
        approval_ids.append(approval.id)
    auth = active_app.budget.authorize_episode(
        episode_id=episodes[0].id,
        kind=AuthorizationKind.PREPRODUCTION,
        approval_id=approval_ids[0],
        max_idr=5_000,
        actor=OWNER,
    )
    _assert_denied(active_app, _request(auth, 1_000, episode_id=episodes[1].id), "episode lain")
    active_app.budget.revoke(actor=OWNER, reason="uji", episode_id=episodes[0].id)
    _assert_denied(active_app, _request(auth, 1_000), "dicabut")


def test_episode_authorization_requires_owner(active_app: App) -> None:
    with pytest.raises(NotAuthorizedError):
        active_app.budget.authorize_episode(
            episode_id="x",
            kind=AuthorizationKind.PRODUCTION,
            approval_id="y",
            max_idr=1,
            actor=DIRECTOR,
        )


def test_denied_when_authorization_cap_exceeded(make_app: AppFactory, config_dir: Path) -> None:
    _small_budget(config_dir, openai=5_000, operational=1_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    app.guard.spend(_request(auth, 50_000))  # Rp893
    _assert_denied(app, _request(auth, 10_000), "batas otorisasi")


def test_denied_when_category_allocation_exhausted(make_app: AppFactory, config_dir: Path) -> None:
    _small_budget(config_dir, openai=1_000, operational=5_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    app.guard.spend(_request(auth, 50_000))  # Rp893
    _assert_denied(app, _request(auth, 10_000), "alokasi openai")
    # Kategori lain tidak terpengaruh.
    app.guard.spend(_request(auth, 10_000, category=Category.TTS))


def test_reserve_is_not_spendable(active_app: App) -> None:
    status = active_app.budget.status(Mode.SIMULATED)
    assert status.spendable_total_idr == 275_000
    assert {c.category for c in status.categories} == set(Category)


# --- Hermes (ADR-0009) --------------------------------------------------------


def test_hermes_usage_is_metered_against_openai_allocation(active_app: App) -> None:
    auth = _operational(active_app)
    pricing = active_app.pricing
    calls = [
        ("conversation", pricing.llm_call_usd_micros("fast", 2_000, 300)),
        ("tool_call", pricing.llm_call_usd_micros("fast", 2_500, 150)),
        ("tool_call", pricing.llm_call_usd_micros("fast", 2_800, 200)),
        ("retry", pricing.llm_call_usd_micros("fast", 2_800, 200)),
    ]
    for purpose, usd in calls:
        active_app.guard.spend(_request(auth, usd, source=Source.HERMES, purpose=purpose))
    active_app.guard.spend(_request(auth, pricing.llm_call_usd_micros("smart", 3_000, 1_000)))

    entries = active_app.budget.ledger()
    hermes = [e for e in entries if e.source is Source.HERMES]
    assert [e.purpose for e in hermes] == ["conversation", "tool_call", "tool_call", "retry"]
    status = active_app.budget.status(Mode.SIMULATED)
    openai = next(c for c in status.categories if c.category is Category.OPENAI)
    assert openai.committed_idr == sum(e.actual_idr or 0 for e in entries)
    assert status.by_source["hermes"] == sum(e.actual_idr or 0 for e in hermes)
    assert status.by_source["studio"] > 0


def test_hermes_is_blocked_when_operational_cap_is_spent(
    make_app: AppFactory, config_dir: Path
) -> None:
    _small_budget(config_dir, openai=5_000, operational=100)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    usd = app.pricing.llm_call_usd_micros("fast", 2_000, 300)  # ±Rp23
    for _ in range(4):
        app.guard.spend(_request(auth, usd, source=Source.HERMES, purpose="tool_call"))
    _assert_denied(
        app, _request(auth, usd, source=Source.HERMES, purpose="retry"), "batas otorisasi"
    )


# --- property-based --------------------------------------------------------------

_OPS = st.lists(
    st.tuples(
        st.sampled_from([Category.OPENAI, Category.TTS]),
        st.integers(min_value=0, max_value=120_000),  # 0 – ±Rp2.142
        st.sampled_from(["commit", "release", "keep", "commit_less"]),
    ),
    min_size=1,
    max_size=25,
)


@pytest.fixture
def property_app(make_app: AppFactory, config_dir: Path) -> App:
    """Satu app dipakai bersama semua contoh hypothesis: invariannya berlaku kumulatif."""
    edit_budget(
        config_dir,
        lambda d: (
            d["allocations_idr"].update({"openai": 6_000, "tts": 4_000}),
            d["limits"].update({"operational_cap_idr": 8_000}),
        ),
    )
    app = make_app()
    app.budget.activate_period(OWNER)
    return app


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(ops=_OPS)
def test_usage_never_exceeds_allocation_or_authorization(
    property_app: App, ops: list[tuple[Category, int, str]]
) -> None:
    app = property_app
    auth = _operational(app)
    for category, usd, action in ops:
        try:
            entry = app.guard.reserve(_request(auth, usd, category=category))
        except BudgetExceededError:
            continue
        if action == "commit":
            app.guard.commit(entry.id, usd)
        elif action == "commit_less":
            app.guard.commit(entry.id, usd // 2)
        elif action == "release":
            app.guard.release(entry.id)

        status = app.budget.status(Mode.SIMULATED)
        for usage in status.categories:
            assert usage.used_idr <= usage.allocation_idr
        assert app.budget.authorization_used(auth.id, Mode.SIMULATED) <= auth.max_idr
