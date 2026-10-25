import sqlite3
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from studio.bootstrap import App
from studio.infra.db import Database
from studio.modules.approvals import Decision, compute_subject_hash
from studio.modules.audit import AuditLog
from studio.modules.budget import (
    AuthorizationKind,
    BudgetExceededError,
    BudgetGuard,
    BudgetPlanError,
    Category,
    HermesPurpose,
    LedgerEntry,
    LedgerStateError,
    LedgerStatus,
    Mode,
    Source,
    SpendAuthorization,
    SpendRequest,
    load_plan,
)
from studio.modules.episodes import Category as EpisodeCategory
from studio.shared.actors import Actor
from studio.shared.clock import FakeClock
from studio.shared.errors import ConflictError, NotAuthorizedError
from studio.shared.gates import Gate
from studio.shared.ids import new_id
from tests.conftest import DIRECTOR, OWNER, AppFactory, edit_budget

# 20.000 mikro-dolar × 17.850 = tepat Rp357 (tanpa pembulatan), cocok untuk uji batas.
UNIT_USD = 20_000
UNIT_IDR = 357


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


def _limits(config_dir: Path, **values: int) -> None:
    def mutate(data: dict[str, Any]) -> None:
        for key in ("openai", "tts", "higgsfield"):
            if key in values:
                data["allocations_idr"][key] = values[key]
        if "operational" in values:
            data["limits"]["operational_cap_idr"] = values["operational"]

    edit_budget(config_dir, mutate)


def _approved_episode_authorization(
    app: App, kind: AuthorizationKind, cap: int = 5_000
) -> SpendAuthorization:
    """Buat otorisasi episode lewat jalur sah: approval G0/G2 yang disetujui owner."""
    episode = app.episodes.create(
        category=EpisodeCategory.SAINS, target_duration_s=30, idea=None, actor=OWNER
    )
    gate = Gate.TOPIC if kind is AuthorizationKind.PREPRODUCTION else Gate.COST
    approval = app.approvals.request(
        episode_id=episode.id,
        gate=gate,
        episode_version=episode.version,
        subject={},
        spend_cap_idr=cap,
        actor=Actor.system(),
    )
    result = app.approvals.decide(
        approval.id,
        Decision.APPROVE,
        actor=OWNER,
        current_subject_hash=compute_subject_hash(
            episode_id=episode.id, gate=gate, subject={}, spend_cap_idr=cap
        ),
        current_episode_version=episode.version,
    )
    assert result.accepted
    return app.budget.authorize_episode(
        episode_id=episode.id, kind=kind, approval_id=approval.id, max_idr=cap, actor=OWNER
    )


def _assert_denied(
    app: App, request: SpendRequest, reason: str, guard: BudgetGuard | None = None
) -> None:
    before = len(app.budget.ledger())
    with pytest.raises(BudgetExceededError, match=reason):
        (guard or app.guard).reserve(request)
    assert len(app.budget.ledger()) == before  # tidak ada entri yang tertulis
    denied = app.audit.entries(action="budget.denied")
    assert denied and denied[-1].entity_id == request.idempotency_key


# --- konfigurasi & aktivasi ---------------------------------------------------------


def test_active_period_uses_configured_fx_and_owner_budget(active_app: App) -> None:
    period = active_app.budget.period()
    assert period is not None
    assert period.fx_usd_idr == "17850"
    assert period.plan["monthly_budget_idr"] == 500_000
    assert active_app.plan.vps_cost_idr + active_app.plan.allocations_idr.total == 500_000
    assert period.spendable_total == 275_000  # VPS & cadangan tidak bisa dibelanjakan


def test_only_owner_can_activate_period(app: App) -> None:
    with pytest.raises(NotAuthorizedError):
        app.budget.activate_period(DIRECTOR)
    period = app.budget.activate_period(OWNER)
    assert period.period == "2026-11"
    assert _operational(app).max_idr == 20_000
    assert app.audit.entries(action="budget.period_activated")


def test_invalid_plan_cannot_be_activated(make_app: AppFactory, config_dir: Path) -> None:
    edit_budget(config_dir, lambda d: d["fx"].__setitem__("usd_idr", "18000"))
    app = make_app()
    with pytest.raises(BudgetPlanError, match="melebihi"):
        app.budget.activate_period(OWNER)


def test_reactivation_keeps_usage(active_app: App) -> None:
    auth = _operational(active_app)
    active_app.guard.spend(_request(auth, UNIT_USD))
    active_app.budget.activate_period(OWNER)
    assert _operational(active_app).id == auth.id
    assert active_app.budget.authorization_used(auth.id, Mode.SIMULATED) == UNIT_IDR


# --- reserve / commit / release ------------------------------------------------------


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


def test_amounts_are_stored_as_sqlite_integers(active_app: App) -> None:
    entry = active_app.guard.spend(_request(_operational(active_app), 123_457))
    row = active_app.db.query_one(
        "SELECT typeof(reserved_idr) r, typeof(actual_idr) a, typeof(reserved_usd_micros) u"
        " FROM ledger_entries WHERE id = ?",
        (entry.id,),
    )
    assert row is not None and tuple(row) == ("integer", "integer", "integer")
    with pytest.raises(sqlite3.DatabaseError, match="integers"):
        active_app.db.execute(
            "INSERT INTO ledger_entries (id, idempotency_key, period, mode, category, source,"
            " purpose, authorization_id, episode_id, status, reserved_usd_micros, reserved_idr,"
            " fx_usd_idr, price_ref, created_at, updated_at)"
            " SELECT 'X', 'X', period, mode, category, source, purpose, authorization_id,"
            " episode_id, 'reserved', reserved_usd_micros, 1.5, fx_usd_idr, price_ref,"
            " created_at, updated_at FROM ledger_entries WHERE id = ?",
            (entry.id,),
        )


def test_release_and_double_settlement(active_app: App) -> None:
    entry = active_app.guard.reserve(_request(_operational(active_app), 1_000))
    active_app.guard.release(entry.id)
    with pytest.raises(LedgerStateError):
        active_app.guard.commit(entry.id, 1_000)
    with pytest.raises(LedgerStateError):
        active_app.guard.release(entry.id)


def test_settled_ledger_entries_are_final_in_database(active_app: App) -> None:
    entry = active_app.guard.spend(_request(_operational(active_app), UNIT_USD))
    with pytest.raises(sqlite3.DatabaseError, match="final"):
        active_app.db.execute("UPDATE ledger_entries SET actual_idr = 0 WHERE id = ?", (entry.id,))
    with pytest.raises(sqlite3.DatabaseError, match="cannot be deleted"):
        active_app.db.execute("DELETE FROM ledger_entries")


def test_unknown_outcome_commits_reserved_amount(active_app: App) -> None:
    entry = active_app.guard.reserve(_request(_operational(active_app), UNIT_USD))
    committed = active_app.guard.commit_at_reserved(entry.id)
    assert committed.actual_idr == committed.reserved_idr == UNIT_IDR


# --- overrun ------------------------------------------------------------------------


def test_overrun_is_flagged_audited_and_blocks_further_spending(
    make_app: AppFactory, config_dir: Path
) -> None:
    _limits(config_dir, openai=UNIT_IDR * 2, operational=10_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    entry = app.guard.reserve(_request(auth, UNIT_USD))
    committed = app.guard.commit(entry.id, UNIT_USD * 3)  # tagihan 3× reservasi
    assert committed.overrun and committed.actual_idr == UNIT_IDR * 3
    (overrun,) = app.audit.entries(action="budget.overrun")
    assert overrun.data["excess_idr"] == UNIT_IDR * 2
    usage = next(
        c for c in app.budget.status(Mode.SIMULATED).categories if c.category is Category.OPENAI
    )
    assert usage.remaining_idr == -UNIT_IDR  # uang sudah keluar: sisa negatif, tercatat jujur
    _assert_denied(app, _request(auth, 1), "alokasi openai")


# --- idempotency & double spending ---------------------------------------------------


def test_reserve_and_spend_are_idempotent(active_app: App) -> None:
    auth = _operational(active_app)
    first = active_app.guard.spend(_request(auth, UNIT_USD, key="k1"))
    again = active_app.guard.spend(_request(auth, UNIT_USD, key="k1"))
    assert again == first
    assert len(active_app.budget.ledger()) == 1
    assert active_app.budget.authorization_used(auth.id, Mode.SIMULATED) == UNIT_IDR


@pytest.mark.parametrize(
    "change",
    [
        {"usd_micros": 2 * UNIT_USD},
        {"category": Category.TTS},
        {"source": Source.HERMES, "purpose": "conversation"},
        {"purpose": "lain"},
        {"mode": Mode.REAL},
    ],
    ids=["nominal", "kategori", "sumber", "purpose", "mode"],
)
def test_same_key_for_different_spend_is_conflict(active_app: App, change: dict[str, Any]) -> None:
    auth = _operational(active_app)
    active_app.guard.reserve(_request(auth, UNIT_USD, key="k1"))
    params: dict[str, Any] = {"usd_micros": UNIT_USD, "key": "k1"}
    params.update(change)
    with pytest.raises(ConflictError):
        active_app.guard.reserve(_request(auth, **params))
    assert len(active_app.budget.ledger()) == 1


def test_released_key_cannot_be_reused(active_app: App) -> None:
    auth = _operational(active_app)
    entry = active_app.guard.reserve(_request(auth, UNIT_USD, key="k1"))
    active_app.guard.release(entry.id)
    with pytest.raises(ConflictError, match="dilepas"):
        active_app.guard.spend(_request(auth, UNIT_USD, key="k1"))


def _thread_guard(app: App, clock: FakeClock) -> tuple[Database, BudgetGuard]:
    db = Database(app.db.path, busy_timeout_ms=10_000)
    return db, BudgetGuard(db, clock, AuditLog(db, clock), app.plan, paid_providers_enabled=False)


def test_concurrent_same_key_spends_only_once(active_app: App, clock: FakeClock) -> None:
    auth = _operational(active_app)
    results: list[LedgerEntry] = []
    errors: list[BaseException] = []

    def run() -> None:
        db, guard = _thread_guard(active_app, clock)
        try:
            results.append(guard.spend(_request(auth, UNIT_USD, key="sama")))
        except BaseException as exc:
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len({r.id for r in results}) == 1
    assert len(active_app.budget.ledger()) == 1
    assert active_app.budget.authorization_used(auth.id, Mode.SIMULATED) == UNIT_IDR


def test_concurrent_requests_cannot_exceed_allocation(
    make_app: AppFactory, config_dir: Path, clock: FakeClock
) -> None:
    _limits(config_dir, openai=UNIT_IDR * 10, operational=50_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    granted: list[str] = []
    lock = threading.Lock()
    errors: list[BaseException] = []

    def run() -> None:
        db, guard = _thread_guard(app, clock)
        try:
            for _ in range(10):
                try:
                    entry = guard.spend(_request(auth, UNIT_USD))
                except BudgetExceededError:
                    continue
                with lock:
                    granted.append(entry.id)
        except BaseException as exc:
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=run) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(granted) == 10  # 60 percobaan, hanya 10 yang muat
    usage = next(
        c for c in app.budget.status(Mode.SIMULATED).categories if c.category is Category.OPENAI
    )
    assert usage.used_idr == UNIT_IDR * 10 == usage.allocation_idr


# --- batas anggaran (boundary) -------------------------------------------------------


def test_authorization_cap_exact_boundary(make_app: AppFactory, config_dir: Path) -> None:
    _limits(config_dir, openai=50_000, operational=UNIT_IDR * 3)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    for _ in range(3):
        app.guard.spend(_request(auth, UNIT_USD))  # tepat sampai batas: diizinkan
    assert app.budget.authorization_used(auth.id, Mode.SIMULATED) == auth.max_idr
    _assert_denied(app, _request(auth, 1), "batas otorisasi")  # +Rp1: ditolak


def test_category_allocation_exact_boundary(make_app: AppFactory, config_dir: Path) -> None:
    _limits(config_dir, openai=UNIT_IDR * 2, operational=50_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    app.guard.spend(_request(auth, UNIT_USD))
    app.guard.spend(_request(auth, UNIT_USD))
    _assert_denied(app, _request(auth, 1), "alokasi openai")
    app.guard.spend(_request(auth, UNIT_USD, category=Category.TTS))  # kategori lain aman


def test_reserved_but_uncommitted_amounts_count_against_limits(
    make_app: AppFactory, config_dir: Path
) -> None:
    _limits(config_dir, openai=UNIT_IDR * 2, operational=50_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    held = app.guard.reserve(_request(auth, UNIT_USD * 2))
    _assert_denied(app, _request(auth, 1), "alokasi openai")
    app.guard.release(held.id)
    app.guard.reserve(_request(auth, UNIT_USD))  # sisa kembali setelah dilepas


# --- penolakan per aturan -----------------------------------------------------------


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


def test_denied_without_known_authorization(active_app: App) -> None:
    fake = SpendAuthorization(
        id="TIDAK-ADA",
        kind=AuthorizationKind.PRODUCTION,
        period=None,
        episode_id=None,
        approval_id=None,
        max_idr=10**9,
        status=_operational(active_app).status,
        created_by="penyerang",
    )
    _assert_denied(active_app, _request(fake, 1_000), "otorisasi tidak dikenal")


def test_denied_when_authorization_revoked_or_foreign(active_app: App) -> None:
    auth = _approved_episode_authorization(active_app, AuthorizationKind.PREPRODUCTION)
    other = _approved_episode_authorization(active_app, AuthorizationKind.PREPRODUCTION)
    _assert_denied(active_app, _request(auth, 1_000, episode_id=other.episode_id), "episode lain")
    active_app.budget.revoke(actor=OWNER, reason="uji", episode_id=auth.episode_id)
    _assert_denied(active_app, _request(auth, 1_000), "dicabut")


# --- otorisasi episode hanya dari approval sah ----------------------------------------


def test_episode_authorization_requires_owner(active_app: App) -> None:
    with pytest.raises(NotAuthorizedError):
        active_app.budget.authorize_episode(
            episode_id="x",
            kind=AuthorizationKind.PRODUCTION,
            approval_id="y",
            max_idr=1,
            actor=DIRECTOR,
        )


def test_episode_authorization_requires_approved_matching_approval(active_app: App) -> None:
    episode = active_app.episodes.create(
        category=EpisodeCategory.SAINS, target_duration_s=30, idea=None, actor=OWNER
    )
    pending = active_app.approvals.request(
        episode_id=episode.id,
        gate=Gate.COST,
        episode_version=1,
        subject={},
        spend_cap_idr=1_000,
        actor=Actor.system(),
    )
    # Owner sekalipun tidak bisa membuat otorisasi dari approval yang belum disetujui.
    with pytest.raises(sqlite3.DatabaseError, match="requires an approved"):
        active_app.budget.authorize_episode(
            episode_id=episode.id,
            kind=AuthorizationKind.PRODUCTION,
            approval_id=pending.id,
            max_idr=1_000,
            actor=OWNER,
        )


def test_episode_authorization_cannot_exceed_or_be_raised_or_revived(active_app: App) -> None:
    auth = _approved_episode_authorization(active_app, AuthorizationKind.PRODUCTION, cap=5_000)
    assert auth.approval_id is not None
    with pytest.raises(sqlite3.DatabaseError, match="requires an approved"):
        active_app.budget.authorize_episode(
            episode_id=auth.episode_id or "",
            kind=AuthorizationKind.PRODUCTION,
            approval_id=auth.approval_id,
            max_idr=5_001,
            actor=OWNER,
        )
    with pytest.raises(sqlite3.DatabaseError, match="cannot be raised"):
        active_app.db.execute(
            "UPDATE spend_authorizations SET max_idr = 9999999 WHERE id = ?", (auth.id,)
        )
    active_app.budget.revoke(actor=OWNER, reason="uji", episode_id=auth.episode_id)
    with pytest.raises(sqlite3.DatabaseError, match="cannot be revived"):
        active_app.db.execute(
            "UPDATE spend_authorizations SET status = 'active' WHERE id = ?", (auth.id,)
        )


# --- Hermes (ADR-0009) --------------------------------------------------------------


def test_every_hermes_purpose_is_metered_in_openai_allocation(active_app: App) -> None:
    auth = _operational(active_app)
    pricing = active_app.pricing
    for purpose in HermesPurpose:
        usd = pricing.llm_call_usd_micros("fast", 2_000, 300)
        active_app.guard.spend(_request(auth, usd, source=Source.HERMES, purpose=purpose.value))
    active_app.guard.spend(_request(auth, pricing.llm_call_usd_micros("smart", 3_000, 1_000)))

    entries = active_app.budget.ledger()
    hermes = [e for e in entries if e.source is Source.HERMES]
    assert [e.purpose for e in hermes] == ["conversation", "tool_call", "retry", "background"]
    assert all(e.category is Category.OPENAI for e in hermes)
    status = active_app.budget.status(Mode.SIMULATED)
    openai = next(c for c in status.categories if c.category is Category.OPENAI)
    assert openai.committed_idr == sum(e.actual_idr or 0 for e in entries)
    assert status.by_source["hermes"] == sum(e.actual_idr or 0 for e in hermes)
    assert status.by_source["studio"] > 0


def test_studio_and_hermes_share_one_openai_allocation(
    make_app: AppFactory, config_dir: Path
) -> None:
    _limits(config_dir, openai=UNIT_IDR * 2, operational=50_000)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    app.guard.spend(_request(auth, UNIT_USD))  # Studio
    app.guard.spend(_request(auth, UNIT_USD, source=Source.HERMES, purpose="tool_call"))
    _assert_denied(
        app, _request(auth, 1, source=Source.HERMES, purpose="background"), "alokasi openai"
    )
    _assert_denied(app, _request(auth, 1), "alokasi openai")


def test_hermes_is_blocked_when_operational_cap_is_spent(
    make_app: AppFactory, config_dir: Path
) -> None:
    _limits(config_dir, openai=5_000, operational=UNIT_IDR * 2)
    app = make_app()
    app.budget.activate_period(OWNER)
    auth = _operational(app)
    app.guard.spend(_request(auth, UNIT_USD, source=Source.HERMES, purpose="conversation"))
    app.guard.spend(_request(auth, UNIT_USD, source=Source.HERMES, purpose="retry"))
    _assert_denied(
        app, _request(auth, 1, source=Source.HERMES, purpose="tool_call"), "batas otorisasi"
    )


def test_hermes_cannot_use_episode_budget_or_other_categories(active_app: App) -> None:
    production = _approved_episode_authorization(active_app, AuthorizationKind.PRODUCTION)
    _assert_denied(
        active_app,
        _request(production, 1_000, source=Source.HERMES, purpose="tool_call"),
        "otorisasi operasional",
    )
    auth = _operational(active_app)
    _assert_denied(
        active_app,
        _request(
            auth, 1_000, source=Source.HERMES, purpose="tool_call", category=Category.HIGGSFIELD
        ),
        "kategori openai",
    )
    _assert_denied(
        active_app,
        _request(auth, 1_000, source=Source.HERMES, purpose="sembunyi"),
        "purpose Hermes",
    )


# --- property-based -----------------------------------------------------------------

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
    _limits(config_dir, openai=6_000, tts=4_000, operational=8_000)
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
