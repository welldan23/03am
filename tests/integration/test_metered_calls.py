"""TD-01 + ADR-0009: panggilan provider termeter, di luar transaksi, tanpa bayar dua kali."""

import sqlite3
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from studio.bootstrap import App
from studio.infra.db import Database
from studio.modules.artifacts import ArtifactKind
from studio.modules.budget import LedgerStatus, Mode
from studio.modules.calls import CallStatus
from studio.modules.episodes import EpisodeStatus as S
from studio.providers.errors import InvalidTicketError
from studio.providers.llm.mock import MockLLMProvider
from studio.providers.llm.ports import LLMRequest, LLMResponse
from studio.providers.tickets import SpendTicket, TicketAuthority
from studio.shared.clock import FakeClock
from tests.conftest import OWNER, AppFactory
from tests.helpers import approve, new_started_episode, run_worker


class HookedProvider(MockLLMProvider):
    """Mock dengan kait sebelum menjawab (untuk mensimulasikan crash/lock/worker lain)."""

    hook: Callable[[LLMRequest], None] | None = None

    def complete(self, request: LLMRequest, ticket: SpendTicket) -> LLMResponse:
        if self.hook is not None:
            self.hook(request)
        return super().complete(request, ticket)


def _hooked(**kwargs: Any) -> tuple[Callable[[TicketAuthority], HookedProvider], list[Any]]:
    box: list[HookedProvider] = []

    def factory(tickets: TicketAuthority) -> HookedProvider:
        provider = HookedProvider(tickets, **kwargs)
        box.append(provider)
        return provider

    return factory, box  # type: ignore[return-value]


def _ready(app: App) -> str:
    app.budget.activate_period(OWNER)
    return new_started_episode(app).id


# --- jejak biaya setiap operasi LLM ----------------------------------------------------


def test_every_llm_operation_has_full_cost_trail(active_app: App) -> None:
    episode = new_started_episode(active_app)
    run_worker(active_app)
    approve(active_app, episode.id, choice=1)
    run_worker(active_app)
    calls = active_app.calls.calls_for_episode(episode.id)
    ledger = {e.id: e for e in active_app.budget.ledger(episode_id=episode.id)}
    assert len(calls) >= 14
    for call in calls:
        assert call.status is CallStatus.SUCCEEDED
        assert call.estimated_input_tokens > 0 and call.max_output_tokens > 0
        assert call.estimated_cost_idr >= 0 and call.authorization_id and call.idempotency_key
        entry = ledger[call.ledger_entry_id]
        assert entry.status is LedgerStatus.COMMITTED and entry.mode is Mode.SIMULATED
        assert entry.reserved_idr == call.estimated_cost_idr
        assert entry.actual_idr == call.actual_cost_idr
        assert entry.fx_usd_idr == "17850"
    # Jejak yang sama ikut tersimpan di artefak.
    research = active_app.artifacts.latest(episode.id, ArtifactKind.RESEARCH)
    assert research is not None
    for ref in research.content["llm_calls"]:
        assert {
            "estimated_input_tokens",
            "estimated_cost_idr",
            "authorization_id",
            "idempotency_key",
            "ledger_entry_id",
        } <= ref.keys()
    # Biaya mock = simulasi; saldo nyata tidak tersentuh dan batas Rp5.000 tidak terlampaui.
    assert active_app.budget.status(Mode.REAL).used_idr == 0
    preproduction = sum(
        e.actual_idr or 0 for e in ledger.values() if e.purpose != "topic_discovery"
    )
    assert 0 < preproduction <= 5_000


def test_provider_is_never_called_while_sqlite_write_lock_is_held(make_app: AppFactory) -> None:
    factory, box = _hooked()
    app = make_app(llm_provider_factory=factory)
    probes: list[bool] = []

    def probe(request: LLMRequest) -> None:
        other = Database(app.db.path, busy_timeout_ms=50)
        try:
            other.execute("BEGIN IMMEDIATE")  # gagal "database is locked" kalau lock ditahan
            other.execute("ROLLBACK")
            probes.append(True)
        except sqlite3.OperationalError:
            probes.append(False)
        finally:
            other.close()

    box[0].hook = probe
    episode_id = _ready(app)
    run_worker(app)
    approve(app, episode_id, choice=1)
    run_worker(app)
    assert probes and all(probes)


# --- tidak ada jalur provider tanpa BudgetGuard -----------------------------------------


def test_provider_rejects_calls_without_valid_ticket() -> None:
    tickets = TicketAuthority()
    provider = MockLLMProvider(tickets)
    request = LLMRequest(
        task="topic_discovery",
        tier="fast",
        system="s",
        user="u",
        max_output_tokens=10,
        timeout_s=1,
        idempotency_key="k",
    )
    with pytest.raises(InvalidTicketError):
        provider.complete(request, None)  # type: ignore[arg-type]
    forged = SpendTicket(request.fingerprint, "ledger-palsu", "auth-palsu", "0" * 64)
    with pytest.raises(InvalidTicketError):
        provider.complete(request, forged)
    other_request = TicketAuthority().issue(request.fingerprint, "l", "a")  # otoritas lain
    with pytest.raises(InvalidTicketError):
        provider.complete(request, other_request)
    assert provider.calls == []


def test_no_authorization_means_provider_is_never_called(make_app: AppFactory) -> None:
    factory, box = _hooked()
    app = make_app(llm_provider_factory=factory)
    episode = new_started_episode(app)  # periode belum diaktifkan → tidak ada otorisasi
    run_worker(app)
    assert box[0].calls == []
    assert app.episodes.get(episode.id).status is S.FAILED
    assert app.audit.entries(action="budget.denied")


def test_app_does_not_expose_raw_provider(active_app: App) -> None:
    exposed = {type(v).__name__ for v in vars(active_app).values()}
    assert "MockLLMProvider" not in exposed


# --- timeout, crash, recovery ----------------------------------------------------------


def test_timeout_is_unknown_outcome_and_never_blindly_retried(make_app: AppFactory) -> None:
    factory, box = _hooked(faults={"topic_discovery": ["timeout"]})
    app = make_app(llm_provider_factory=factory)
    episode_id = _ready(app)
    run_worker(app)
    episode = app.episodes.get(episode_id)
    assert episode.status is S.FAILED and "timeout" in (episode.failure_reason or "")
    (call,) = app.calls.calls_for_episode(episode_id)
    assert call.status is CallStatus.UNKNOWN
    (entry,) = app.budget.ledger(episode_id=episode_id)
    assert entry.status is LedgerStatus.COMMITTED and entry.actual_idr == entry.reserved_idr
    assert len(box[0].calls) == 1  # tidak ada retry otomatis
    (job,) = app.queue.list_jobs(episode_id=episode_id)
    assert job.attempts == 1

    # Owner yang memutuskan mengulang → panggilan BARU dengan key baru.
    app.workflow.retry(episode_id, OWNER)
    run_worker(app)
    assert app.episodes.get(episode_id).status is S.AWAITING_TOPIC
    assert len(box[0].calls) == 2
    assert len(app.calls.calls_for_episode(episode_id)) == 2


def test_crash_during_call_is_not_replayed_blindly(make_app: AppFactory, clock: FakeClock) -> None:
    factory, box = _hooked()
    app = make_app(llm_provider_factory=factory)

    def die(request: LLMRequest) -> None:
        raise KeyboardInterrupt  # proses mati saat request sedang di provider

    box[0].hook = die
    episode_id = _ready(app)
    with pytest.raises(KeyboardInterrupt):
        app.worker("w1").run_once()
    (call,) = app.calls.calls_for_episode(episode_id)
    assert call.status is CallStatus.IN_FLIGHT

    box[0].hook = None
    clock.advance(timedelta(seconds=app.settings.worker_lease_seconds + 1))
    run_worker(app, "w2")
    (call,) = app.calls.calls_for_episode(episode_id)
    assert call.status is CallStatus.UNKNOWN
    assert len(box[0].calls) == 0  # tidak dipanggil ulang
    (entry,) = app.budget.ledger(episode_id=episode_id)
    assert entry.status is LedgerStatus.COMMITTED and entry.actual_idr == entry.reserved_idr
    episode = app.episodes.get(episode_id)
    assert episode.status is S.FAILED and "terputus" in (episode.failure_reason or "")


def test_idempotent_provider_may_replay_after_crash(make_app: AppFactory, clock: FakeClock) -> None:
    factory, box = _hooked(idempotent_replay=True)
    app = make_app(llm_provider_factory=factory)
    box[0].hook = lambda r: (_ for _ in ()).throw(KeyboardInterrupt)
    episode_id = _ready(app)
    with pytest.raises(KeyboardInterrupt):
        app.worker("w1").run_once()
    box[0].hook = None
    clock.advance(timedelta(seconds=app.settings.worker_lease_seconds + 1))
    run_worker(app, "w2")
    assert app.episodes.get(episode_id).status is S.AWAITING_TOPIC
    (call,) = app.calls.calls_for_episode(episode_id)
    assert call.status is CallStatus.SUCCEEDED
    (entry,) = app.budget.ledger(episode_id=episode_id)  # satu reservasi, satu biaya
    assert entry.status is LedgerStatus.COMMITTED


def test_unavailable_provider_releases_reservation_and_retries(
    make_app: AppFactory, clock: FakeClock
) -> None:
    factory, _ = _hooked(faults={"topic_discovery": ["unavailable"]})
    app = make_app(llm_provider_factory=factory)
    episode_id = _ready(app)
    run_worker(app)
    clock.advance(timedelta(minutes=1))
    run_worker(app)
    assert app.episodes.get(episode_id).status is S.AWAITING_TOPIC
    statuses = sorted(e.status.value for e in app.budget.ledger(episode_id=episode_id))
    assert statuses == ["committed", "released"]  # gagal pasti → tidak tertagih
    (call,) = app.calls.calls_for_episode(episode_id)
    assert call.status is CallStatus.SUCCEEDED and call.attempt == 2


def test_invalid_json_retry_is_metered_separately(make_app: AppFactory) -> None:
    factory, _ = _hooked(faults={"topic_discovery": ["invalid_json"]})
    app = make_app(llm_provider_factory=factory)
    episode_id = _ready(app)
    run_worker(app)
    assert app.episodes.get(episode_id).status is S.AWAITING_TOPIC
    purposes = [e.purpose for e in app.budget.ledger(episode_id=episode_id)]
    assert purposes == ["topic_discovery", "topic_discovery.retry"]
    assert all(e.status is LedgerStatus.COMMITTED for e in app.budget.ledger(episode_id=episode_id))


# --- worker basi ---------------------------------------------------------------------


def test_stale_worker_result_is_not_accepted_but_cost_is_reused(
    make_app: AppFactory, clock: FakeClock
) -> None:
    """Lease habis selama panggilan: hasil tahap ditolak, worker baru memakai ulang respons."""
    factory, box = _hooked()
    app = make_app(llm_provider_factory=factory)
    box[0].hook = lambda r: clock.advance(timedelta(seconds=app.settings.worker_lease_seconds))
    episode_id = _ready(app)
    app.worker("lambat").run_once()
    assert app.artifacts.latest(episode_id, ArtifactKind.TOPICS) is None  # tidak diterima
    assert app.episodes.get(episode_id).status is S.DISCOVERING

    box[0].hook = None
    run_worker(app, "baru")
    assert app.episodes.get(episode_id).status is S.AWAITING_TOPIC
    assert len(box[0].calls) == 1  # respons yang sudah dibayar dipakai ulang
    assert len(app.budget.ledger(episode_id=episode_id)) == 1


def test_takeover_during_call_marks_unknown_and_stale_result_is_dropped(
    make_app: AppFactory, clock: FakeClock
) -> None:
    """Worker lain mengambil alih saat panggilan berjalan: tidak ada hasil ganda."""
    factory, box = _hooked()
    app = make_app(llm_provider_factory=factory)
    episode_id = _ready(app)
    taken_over: list[bool] = []

    def takeover(request: LLMRequest) -> None:
        if taken_over:
            return
        taken_over.append(True)
        clock.advance(timedelta(seconds=app.settings.worker_lease_seconds + 1))
        app.worker("pengambil-alih").run_once()

    box[0].hook = takeover
    app.worker("lambat").run_once()
    (call,) = app.calls.calls_for_episode(episode_id)
    assert call.status is CallStatus.UNKNOWN  # pengambil alih tidak mengulang secara buta
    assert app.artifacts.latest(episode_id, ArtifactKind.TOPICS) is None
    assert len(app.budget.ledger(episode_id=episode_id)) == 1
    assert app.episodes.get(episode_id).status is S.FAILED


def test_result_is_rejected_when_episode_changes_during_external_work(
    make_app: AppFactory,
) -> None:
    """Owner membatalkan episode saat provider bekerja → hasil tahap tidak diterima."""
    factory, box = _hooked()
    app = make_app(llm_provider_factory=factory)
    episode_id = _ready(app)
    box[0].hook = lambda r: app.workflow.cancel(episode_id, OWNER, "dibatalkan saat riset")
    run_worker(app)
    assert app.episodes.get(episode_id).status is S.CANCELLED
    assert app.artifacts.latest(episode_id, ArtifactKind.TOPICS) is None
    assert app.audit.entries(episode_id=episode_id, action="job.obsolete")
    # Biaya panggilan yang sudah terjadi tetap tercatat jujur.
    (entry,) = app.budget.ledger(episode_id=episode_id)
    assert entry.status is LedgerStatus.COMMITTED


def test_invalid_json_twice_fails_episode_with_clear_message(make_app: AppFactory) -> None:
    factory, _ = _hooked(faults={"topic_discovery": ["invalid_json", "invalid_json"]})
    app = make_app(llm_provider_factory=factory)
    episode_id = _ready(app)
    run_worker(app)
    episode = app.episodes.get(episode_id)
    assert episode.status is S.FAILED and episode.failed_from is S.DISCOVERING
    assert "tidak sesuai skema setelah 2 percobaan" in (episode.failure_reason or "")
    # Dua panggilan (asli + 1 retry), dua-duanya tercatat; tidak ada retry ketiga.
    calls = app.calls.calls_for_episode(episode_id)
    assert [c.purpose for c in calls] == ["topic_discovery", "topic_discovery.retry"]
