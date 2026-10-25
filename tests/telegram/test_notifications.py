"""Outbox notifikasi persisten: dibuat transaksional oleh trigger DB, dikirim di luar
transaksi, selamat dari restart, tidak dobel ke penerima yang sama, retry/backoff."""

from datetime import timedelta

import pytest

from studio.interfaces.telegram.transport import TransportError
from studio.modules.episodes import Category, DocumentaryFormat
from studio.modules.episodes import EpisodeStatus as S
from studio.modules.notifications import NotificationKind, NotificationStatus
from studio.providers.llm.mock import MockLLMProvider
from studio.shared.clock import FakeClock
from tests.conftest import AppFactory
from tests.telegram.conftest import TG_OWNER
from tests.telegram.fakes import OWNER_TG, Harness, create_episode, g0_card, to_editorial


def _kinds(h: Harness) -> list[str]:
    return [n.kind.value for n in h.app.outbox.entries()]


def test_outbox_rows_are_written_in_the_same_transaction(harness: Harness) -> None:
    app = harness.app
    episode = app.workflow.create_episode(
        category=Category.SEJARAH,
        target_duration_s=None,
        idea=None,
        actor=TG_OWNER,
        format=DocumentaryFormat.ARCHIVES,
    )
    app.workflow.start(episode.id, TG_OWNER)
    harness.work()
    assert _kinds(harness) == ["approval.requested"]
    # Transaksi yang di-rollback tidak meninggalkan notifikasi.
    with pytest.raises(RuntimeError), app.db.transaction():
        app.workflow.cancel(episode.id, TG_OWNER)
        assert "episode.closed" in _kinds(harness)
        raise RuntimeError("rollback")
    assert _kinds(harness) == ["approval.requested"]
    assert app.episodes.get(episode.id).status is S.AWAITING_TOPIC


def test_all_pipeline_events_are_notified_once(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    assert _kinds(h) == [
        "approval.requested",
        "research.started",
        "research.brief_ready",
        "script.ready",
        "approval.requested",
    ]
    assert all(n.status is NotificationStatus.SENT for n in h.app.outbox.entries())
    sent_before = len(h.transport.messages)
    assert h.notify() == 0  # tidak ada yang dikirim ulang
    assert len(h.transport.messages) == sent_before


def test_notifications_survive_restart(harness: Harness, clock: FakeClock) -> None:
    h = harness
    create_episode(h)  # kartu G0 terkirim
    h.press("✅ 1", g0_card(h))
    h.work()  # riset & naskah selesai, notifikasi belum dikirim (bot "mati")
    claimed = h.app.outbox.claim("bot-lama", lease_seconds=60)  # klaim lalu crash
    assert claimed
    restarted = Harness(h.app, first_update_id=10_000)
    try:
        assert restarted.notify() == 0  # klaim lama masih berlaku
        clock.advance(timedelta(seconds=61))
        assert restarted.notify() == len(claimed)
        texts = "\n".join(restarted.transport.texts())
        assert "ResearchBrief selesai" in texts and "G1 menunggu approval" in texts
        assert all(n.status is NotificationStatus.SENT for n in h.app.outbox.entries())
    finally:
        restarted.close()


def test_rate_limit_reschedules_with_retry_after(harness: Harness, clock: FakeClock) -> None:
    h = harness
    h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
    h.press("Ya, lanjutkan")
    h.work()
    h.transport.fail_next.append(TransportError("429", retryable=True, retry_after=30))
    assert h.notify() == 1
    (n,) = h.app.outbox.entries()
    assert n.status is NotificationStatus.PENDING and n.attempts == 1
    assert n.next_attempt_at >= clock.now() + timedelta(seconds=30)
    assert h.notify() == 0  # belum jatuh tempo
    clock.advance(timedelta(seconds=31))
    assert h.notify() == 1
    assert h.app.outbox.get(n.id).status is NotificationStatus.SENT


def test_permanent_failure_is_dead_lettered(harness: Harness) -> None:
    h = harness
    h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
    h.press("Ya, lanjutkan")
    h.work()
    h.transport.fail_next.append(TransportError("bot diblokir", retryable=False))
    h.notify()
    (n,) = h.app.outbox.entries()
    assert n.status is NotificationStatus.DEAD and "diblokir" in (n.last_error or "")


def test_recipient_already_served_is_not_sent_again(make_app: AppFactory, clock: FakeClock) -> None:
    app = make_app(owner_ids=f"telegram:{OWNER_TG},telegram:2002")
    app.budget.activate_period(TG_OWNER)
    h = Harness(app)
    try:
        h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
        h.press("Ya, lanjutkan")
        h.work()
        # Penerima pertama berhasil, penerima kedua gagal sementara.
        original = h.transport.send
        calls = {"n": 0}

        async def flaky(chat_id: int, screen: object) -> int:
            calls["n"] += 1
            if chat_id == 2002 and calls["n"] == 2:
                raise TransportError("timeout", retryable=True)
            return await original(chat_id, screen)  # type: ignore[arg-type]

        h.transport.send = flaky  # type: ignore[method-assign]
        h.notify()
        (n,) = app.outbox.entries()
        assert n.delivered_to == (str(OWNER_TG),) and n.status is NotificationStatus.PENDING
        clock.advance(timedelta(minutes=5))
        h.notify()
        recipients = [
            m.chat_id for m in h.transport.messages.values() if "Topik siap dipilih" in m.text
        ]
        assert sorted(recipients) == [OWNER_TG, 2002]  # owner pertama tidak dikirimi dua kali
        assert app.outbox.get(n.id).status is NotificationStatus.SENT
    finally:
        h.close()


def test_stale_approval_notification_is_skipped(harness: Harness) -> None:
    h = harness
    h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
    h.press("Ya, lanjutkan")
    h.work()
    (approval,) = h.app.approvals.pending()
    h.app.workflow.cancel(approval.episode_id, TG_OWNER)  # diputuskan sebelum notifikasi terkirim
    h.notify()
    assert not any("Topik siap dipilih" in t for t in h.transport.texts())
    assert any("Episode ditutup (CANCELLED)" in t for t in h.transport.texts())


def test_failure_and_retry_notifications(make_app: AppFactory, clock: FakeClock) -> None:
    app = make_app(
        owner_ids=f"telegram:{OWNER_TG}",
        llm_provider_factory=lambda t: MockLLMProvider(
            t, faults={"topic_discovery": ["unavailable", "unavailable", "unavailable"]}
        ),
    )
    app.budget.activate_period(TG_OWNER)
    h = Harness(app)
    try:
        h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
        h.press("Ya, lanjutkan")
        for _ in range(4):
            h.work()
            clock.advance(timedelta(minutes=5))
        h.notify()
        kinds = [n.kind for n in app.outbox.entries()]
        assert kinds.count(NotificationKind.JOB_RETRY) == 2
        assert NotificationKind.EPISODE_FAILED in kinds
        texts = "\n".join(h.transport.texts())
        assert "gagal sementara" in texts and "percobaan 1/3" in texts
        failed = next(m for m in h.transport.messages.values() if "Episode gagal" in m.text)
        assert any("Ulangi" in b.text for b in failed.buttons())
        h.press("Ulangi", failed)
        h.press("Ya, lanjutkan")
        assert app.episodes.get(app.episodes.list_episodes()[0].id).status is S.DISCOVERING
    finally:
        h.close()
