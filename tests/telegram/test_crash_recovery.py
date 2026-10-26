"""Fault injection: crash di setiap titik lifecycle update Telegram (ADR-0013).

"Crash" = `SimulatedCrash` (BaseException) dilempar di titik tertentu. Transaksi yang sedang
terbuka di-rollback (sama seperti SQLite saat proses mati), objek bot di memori dibuang,
lalu bot "di-restart" (Harness baru, database yang sama) dan pemulihan dijalankan.

Yang diperiksa di setiap skenario: efek bisnis tepat sekali (keputusan approval, job, episode,
belanja), update tidak hilang, dan balasan akhirnya terkirim.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import timedelta
from typing import Any

import pytest

from studio.bootstrap import App
from studio.interfaces.telegram import processor as proc
from studio.interfaces.telegram.types import Inbound
from studio.modules.controller import InboxStatus, ReplyStatus
from studio.modules.episodes import EpisodeStatus as S
from studio.shared.clock import FakeClock
from tests.conftest import AppFactory
from tests.telegram.conftest import TG_OWNER
from tests.telegram.fakes import OWNER_TG, FakeTransport, Harness, g1_card, to_editorial

LEASE = timedelta(seconds=31)  # > update_lease_seconds (30)


class SimulatedCrash(BaseException):
    """Proses mati mendadak (bukan Exception biasa, jadi tidak tertangkap handler bot)."""


class Faults:
    def __init__(self) -> None:
        self.armed: dict[str, int] = {}
        self.hits: list[str] = []

    def arm(self, point: str, times: int = 1) -> None:
        self.armed[point] = times

    def __call__(self, point: str) -> None:
        if self.armed.get(point, 0) > 0:
            self.armed[point] -= 1
            self.hits.append(point)
            raise SimulatedCrash(point)


def _decisions(app: App) -> list[str]:
    return [e.data["decision"] for e in app.audit.entries(action="approval.decided")]


def _restart(old: Harness, *, owner: str = "bot-restart") -> Harness:
    """Bot baru di atas database yang sama; pesan Telegram lama tetap di transport."""
    old.close()
    return Harness(old.app, first_update_id=50_000, owner=owner, transport=old.transport)


def _crashing(h: Harness, faults: Faults, action: Any) -> None:
    with pytest.raises(SimulatedCrash):
        action()
    assert faults.hits


@pytest.fixture
def faults() -> Faults:
    return Faults()


@pytest.fixture
def fh(tg_app: App, faults: Faults) -> Any:
    h = Harness(tg_app, fault=faults)
    yield h
    h.close()


def _approve_g1_after_crash_at(
    point: str, h: Harness, faults: Faults, clock: FakeClock
) -> tuple[Harness, str, int]:
    episode_id = to_editorial(h)
    card = g1_card(h)
    decisions_before = len(_decisions(h.app))
    messages_before = len(h.transport.log)
    faults.arm(point)
    _crashing(h, faults, lambda: h.press("Approve", card))
    assert len(h.transport.log) == messages_before or point in (proc.AFTER_SEND,)
    restarted = _restart(h)
    return restarted, episode_id, decisions_before


# --- 1 & 2: crash sebelum commit → diproses ulang, tidak hilang ------------------------


@pytest.mark.parametrize("point", [proc.AFTER_RECEIVE, proc.BEFORE_COMMIT])
def test_crash_before_commit_is_reprocessed_exactly_once(
    fh: Harness, faults: Faults, clock: FakeClock, point: str
) -> None:
    h, episode_id, before = _approve_g1_after_crash_at(point, fh, faults, clock)
    try:
        app = h.app
        # Belum ada efek bisnis: rollback total (kode tombol belum hangus, approval pending).
        assert app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
        assert len(_decisions(app)) == before
        (item,) = [i for i in app.inbox.entries() if i.status is not InboxStatus.DELIVERED]
        assert item.status is InboxStatus.PROCESSING
        assert app.replies.for_update("telegram", item.update_id) == []
        # Lease pemroses yang mati masih berlaku → belum diambil.
        assert h.recover() == 0
        clock.advance(LEASE)
        assert h.recover() == 1
        assert app.episodes.get(episode_id).status is S.ESTIMATING_COST
        assert _decisions(app).count("approve") == 2  # G0 + G1, sekali saja
        assert app.inbox.get("telegram", item.update_id).status is InboxStatus.DELIVERED  # type: ignore[union-attr]
        assert "Disetujui" in h.transport.last().text
        # Pemulihan berikutnya tidak melakukan apa pun.
        clock.advance(LEASE)
        assert h.recover() == 0
        assert _decisions(app).count("approve") == 2
    finally:
        h.close()


# --- 3: crash setelah commit, sebelum balasan terkirim -----------------------------------


def test_crash_after_commit_delivers_reply_without_rerunning_action(
    fh: Harness, faults: Faults, clock: FakeClock
) -> None:
    h, episode_id, before = _approve_g1_after_crash_at(proc.AFTER_COMMIT, fh, faults, clock)
    try:
        app = h.app
        assert app.episodes.get(episode_id).status is S.ESTIMATING_COST  # sudah di-commit
        assert len(_decisions(app)) == before + 1
        pending = app.replies.entries(ReplyStatus.PENDING)
        assert pending and all(r.kind in ("answer", "edit") for r in pending)
        jobs_before = len(app.queue.list_jobs(episode_id=episode_id))
        assert h.recover() >= 1  # balasan tertunda langsung bisa dikirim
        assert "Disetujui" in h.transport.last().text
        assert app.replies.entries(ReplyStatus.PENDING) == []
        assert len(_decisions(app)) == before + 1
        assert len(app.queue.list_jobs(episode_id=episode_id)) == jobs_before
        statuses = {i.status for i in app.inbox.entries()}
        assert statuses == {InboxStatus.DELIVERED}
    finally:
        h.close()


# --- 4: crash saat Telegram send berlangsung (Telegram belum menerima) -------------------


def test_crash_during_send_resends_after_lease(
    fh: Harness, faults: Faults, clock: FakeClock
) -> None:
    h = fh
    faults.arm(proc.BEFORE_SEND)
    _crashing(
        h,
        faults,
        lambda: h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah"),
    )
    assert h.transport.messages == {}
    restarted = _restart(h)
    try:
        assert restarted.recover() == 0  # baris balasan masih diklaim pemroses lama
        clock.advance(LEASE)
        restarted.recover()
        confirms = [
            m for m in restarted.transport.messages.values() if "Buat dokumenter ini?" in m.text
        ]
        assert len(confirms) == 1
        assert restarted.app.db.scalar("SELECT COUNT(DISTINCT group_id) FROM ui_action_codes") == 1
    finally:
        restarted.close()


# --- 5: Telegram sudah menerima, crash sebelum "sent" tercatat --------------------------


def test_crash_after_telegram_accepted_send_may_duplicate_message_but_not_action(
    fh: Harness, faults: Faults, clock: FakeClock
) -> None:
    h = fh
    faults.arm(proc.AFTER_SEND)
    _crashing(
        h,
        faults,
        lambda: h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah"),
    )
    assert len(h.transport.messages) == 1  # Telegram SUDAH menerima pesannya
    restarted = _restart(h)
    try:
        clock.advance(LEASE)
        restarted.recover()
        confirms = [
            m for m in restarted.transport.messages.values() if "Buat dokumenter ini?" in m.text
        ]
        # Batas Bot API: sendMessage tidak punya idempotency key → pesan dikirim ulang (dobel).
        assert len(confirms) == 2 and confirms[0].keyboard == confirms[1].keyboard
        # Tapi aksinya tidak dijalankan ulang: hanya satu kartu (satu grup kode).
        app = restarted.app
        assert app.db.scalar("SELECT COUNT(DISTINCT group_id) FROM ui_action_codes") == 1
        restarted.press("Ya, lanjutkan", confirms[1])
        restarted.press("Ya, lanjutkan", confirms[0])  # tombol yang sama di pesan dobel
        assert len(app.episodes.list_episodes()) == 1
        assert len(app.queue.list_jobs()) == 1
    finally:
        restarted.close()


def test_crash_after_telegram_accepted_edit_is_idempotent(
    fh: Harness, faults: Faults, clock: FakeClock
) -> None:
    h = fh
    h.say("/menu")
    menu = h.transport.last()
    count = len(h.transport.messages)
    faults.arm(proc.AFTER_SEND)
    _crashing(h, faults, lambda: h.press("Budget", menu))
    restarted = _restart(h)
    try:
        clock.advance(LEASE)
        restarted.recover()
        # Baris pertama (jawaban callback) diulang tanpa efek; edit diulang ke pesan yang sama.
        assert len(restarted.transport.messages) == count
        assert "Budget" in restarted.transport.messages[menu.message_id].text
        assert {i.status for i in restarted.app.inbox.entries()} == {InboxStatus.DELIVERED}
    finally:
        restarted.close()


# --- 6: update yang sama datang lagi saat yang pertama masih diproses -------------------


def test_duplicate_update_while_first_is_processing(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    card = g1_card(h)
    inbound = Inbound(
        update_id=777,
        user_id=OWNER_TG,
        chat_id=OWNER_TG,
        chat_type="private",
        callback_id="cb-dup",
        callback_data=card.button("Approve").data,
        message_id=card.message_id,
    )

    async def both() -> None:
        await asyncio.gather(h.bot.handle(inbound), h.bot.handle(inbound))

    h.run(both())
    assert _decisions(h.app).count("approve") == 2  # G0 + G1 sekali
    # Duplikat tidak menjawab callback (callback_id sama → bisa merebut pop-up aslinya).
    assert [a for a in h.transport.answers if a[0] == "cb-dup"] == [("cb-dup", "", False)]
    item = h.app.inbox.get("telegram", 777)
    assert item is not None and item.status is InboxStatus.DELIVERED
    # Duplikat tidak merebut lease pemroses pertama (tidak ada kerja yang dibuang).
    assert item.lease_token == 1 and item.attempts == 1


# --- 7: restart dengan beberapa update masih PROCESSING ---------------------------------


def test_restart_recovers_all_stuck_updates_in_order(
    fh: Harness, faults: Faults, clock: FakeClock
) -> None:
    h = fh
    episode_id = to_editorial(h)
    card = g1_card(h)
    faults.arm(proc.AFTER_RECEIVE, times=2)
    _crashing(h, faults, lambda: h.say("/budget"))
    _crashing(h, faults, lambda: h.press("Approve", card))
    stuck = [i for i in h.app.inbox.entries() if i.status is InboxStatus.PROCESSING]
    assert len(stuck) == 2
    restarted = _restart(h)
    try:
        clock.advance(LEASE)
        assert restarted.recover() == 2
        texts = restarted.transport.texts()
        assert any("Budget" in t for t in texts) and any("Disetujui" in t for t in texts)
        assert restarted.app.episodes.get(episode_id).status is S.ESTIMATING_COST
        assert {i.status for i in restarted.app.inbox.entries()} == {InboxStatus.DELIVERED}
    finally:
        restarted.close()


def test_recovery_rechecks_allowlist(
    make_app: AppFactory, clock: FakeClock, faults: Faults
) -> None:
    app = make_app(owner_ids=f"telegram:{OWNER_TG}")
    app.budget.activate_period(TG_OWNER)
    h = Harness(app, fault=faults)
    faults.arm(proc.AFTER_RECEIVE)
    _crashing(h, faults, lambda: h.say("/budget"))
    h.close()
    # Owner dicabut dari allowlist sebelum bot hidup lagi.
    revoked = make_app(owner_ids="cli:owner")
    r = Harness(revoked, first_update_id=50_000, transport=h.transport)
    try:
        clock.advance(LEASE)
        r.recover()
        assert r.transport.messages == {}
        (item,) = revoked.inbox.entries()
        assert item.status is InboxStatus.FAILED and item.last_error == "tidak lagi berhak"
    finally:
        r.close()


# --- 8: callback approval dikirim ulang ---------------------------------------------------


def test_resent_approval_callback_never_decides_twice(
    fh: Harness, faults: Faults, clock: FakeClock
) -> None:
    h = fh
    episode_id = to_editorial(h)
    card = g1_card(h)
    first = h.press("Approve", card)
    # (a) Telegram mengirim ulang update yang sama setelah selesai → tidak ada efek/balasan baru.
    sent = len(h.transport.log)
    h.run(h.bot.handle(first))
    assert len(h.transport.log) == sent
    # (b) Dikirim ulang saat sudah di-commit tapi balasan belum terkirim → hanya kirim balasan.
    to_editorial(h)
    second_card = g1_card(h)
    faults.arm(proc.AFTER_COMMIT)
    _crashing(h, faults, lambda: h.press("Approve", second_card))
    stuck = [i for i in h.app.inbox.entries() if i.status is InboxStatus.COMMITTED]
    assert len(stuck) == 1
    original = proc.inbound_from_payload(stuck[0].payload)
    restarted = _restart(h)
    try:
        restarted.run(restarted.bot.handle(original))  # Telegram mengirim ulang update itu
        assert "Disetujui" in restarted.transport.last().text
        assert {i.status for i in restarted.app.inbox.entries()} == {InboxStatus.DELIVERED}
        # (c) Tombol yang sama ditekan lagi (update baru) → kode sekali pakai menolak.
        version = restarted.app.episodes.get(episode_id).version
        restarted.tap(card.button("Approve"), card)
        assert restarted.transport.answers[-1][2] is True  # alert penolakan
        assert restarted.app.episodes.get(episode_id).version == version
        assert _decisions(restarted.app).count("approve") == 4  # 2 episode × (G0 + G1)
    finally:
        restarted.close()


# --- 9: dua pemroses berebut update yang sama ---------------------------------------------


def test_stale_processor_cannot_commit_after_takeover(
    make_app: AppFactory, clock: FakeClock
) -> None:
    app_a = make_app(owner_ids=f"telegram:{OWNER_TG}")
    app_a.budget.activate_period(TG_OWNER)
    setup = Harness(app_a)
    episode_id = to_editorial(setup)
    card = g1_card(setup)
    setup.close()
    app_b = make_app(owner_ids=f"telegram:{OWNER_TG}")  # koneksi DB kedua (proses lain)
    a = Harness(app_a, owner="bot-A", transport=setup.transport, first_update_id=60_000)
    b = Harness(app_b, owner="bot-B", transport=setup.transport, first_update_id=70_000)
    try:
        inbound = Inbound(
            update_id=888,
            user_id=OWNER_TG,
            chat_id=OWNER_TG,
            chat_type="private",
            callback_id="cb-race",
            callback_data=card.button("Approve").data,
            message_id=card.message_id,
        )
        receipt = app_a.inbox.receive(
            "telegram",
            888,
            chat_id=str(OWNER_TG),
            user_id=str(OWNER_TG),
            payload=proc.inbound_to_payload(inbound),
            owner="bot-A",
        )
        assert receipt.claimed  # A mengklaim lalu "macet" (GC pause / jaringan lambat)
        clock.advance(LEASE)
        assert b.recover() == 1  # B mengambil alih (token 2) dan meng-commit
        sent = len(b.transport.log)
        a.run(a.processor._process(receipt.item, inbound, TG_OWNER))  # A bangun dengan token 1
        assert len(a.transport.log) == sent  # A tidak mengirim apa pun
        assert app_a.episodes.get(episode_id).status is S.ESTIMATING_COST
        assert _decisions(app_a).count("approve") == 2
        item = app_a.inbox.get("telegram", 888)
        assert item is not None and item.lease_token == 2 and item.status is InboxStatus.DELIVERED
    finally:
        a.close()
        b.close()


def test_two_processes_receiving_same_update_concurrently(make_app: AppFactory) -> None:
    app = make_app(owner_ids=f"telegram:{OWNER_TG}")
    app.budget.activate_period(TG_OWNER)
    setup = Harness(app)
    episode_id = to_editorial(setup)
    card = g1_card(setup)
    setup.close()
    transport = FakeTransport()
    workers = [
        Harness(make_app(owner_ids=f"telegram:{OWNER_TG}"), owner=f"bot-{i}", transport=transport)
        for i in range(4)
    ]
    inbound = Inbound(
        update_id=999,
        user_id=OWNER_TG,
        chat_id=OWNER_TG,
        chat_type="private",
        callback_id="cb-4x",
        callback_data=card.button("Approve").data,
        message_id=card.message_id,
    )
    barrier = threading.Barrier(len(workers))

    def run(h: Harness) -> None:
        barrier.wait()
        h.run(h.bot.handle(inbound))

    threads = [threading.Thread(target=run, args=(w,)) for w in workers]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert app.episodes.get(episode_id).status is S.ESTIMATING_COST
        assert _decisions(app).count("approve") == 2
        assert len([a for a in transport.answers if a[0] == "cb-4x"]) == 1
    finally:
        for w in workers:
            w.close()


# --- 10: SQLite busy saat pemulihan --------------------------------------------------------


def test_sqlite_busy_during_recovery_is_retried(
    fh: Harness, faults: Faults, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    h, episode_id, before = _approve_g1_after_crash_at(proc.AFTER_RECEIVE, fh, faults, clock)
    try:
        app = h.app
        real_claim = app.inbox.claim_due
        real_handle = h.engine.handle
        state = {"claim": 1, "handle": 1}

        def busy_claim(*args: Any, **kwargs: Any) -> Any:
            if state["claim"]:
                state["claim"] -= 1
                raise sqlite3.OperationalError("database is locked")
            return real_claim(*args, **kwargs)

        def busy_handle(*args: Any) -> Any:
            if state["handle"]:
                state["handle"] -= 1
                raise sqlite3.OperationalError("database is locked")
            return real_handle(*args)

        monkeypatch.setattr(app.inbox, "claim_due", busy_claim)
        monkeypatch.setattr(h.engine, "handle", busy_handle)
        clock.advance(LEASE)
        with pytest.raises(sqlite3.OperationalError):
            h.recover()  # klaim gagal: tidak ada yang berubah (loop recovery mencoba lagi)
        assert h.recover() == 1  # klaim berhasil, pemrosesan kena busy → dilepas + backoff
        assert app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
        stuck = [i for i in app.inbox.entries() if i.status is InboxStatus.RECEIVED]
        assert len(stuck) == 1 and "locked" in (stuck[0].last_error or "")
        clock.advance(timedelta(seconds=5))
        assert h.recover() == 1
        assert app.episodes.get(episode_id).status is S.ESTIMATING_COST
        assert len(_decisions(app)) == before + 1
    finally:
        h.close()


# --- invarian database ---------------------------------------------------------------------


def test_committed_update_can_never_be_reprocessed(harness: Harness) -> None:
    harness.say("/budget")
    (item,) = harness.app.inbox.entries()
    assert item.status is InboxStatus.DELIVERED
    with pytest.raises(sqlite3.IntegrityError, match="cannot be processed again"):
        harness.app.db.execute(
            "UPDATE ui_inbox SET status = 'processing' WHERE update_id = ?", (item.update_id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="require a committed"):
        harness.app.db.execute(
            "INSERT INTO ui_inbox (channel, update_id, chat_id, payload, status,"
            " next_attempt_at, received_at, updated_at) VALUES ('telegram', 5, '1', '{}',"
            " 'processing', 'x', 'x', 'x')"
        )
        harness.app.db.execute(
            "INSERT INTO ui_reply_outbox (channel, update_id, seq, kind, payload,"
            " next_attempt_at, created_at) VALUES ('telegram', 5, 0, 'send', '{}', 'x', 'x')"
        )


def test_reply_order_is_preserved_when_one_send_fails(harness: Harness, clock: FakeClock) -> None:
    from studio.interfaces.telegram.transport import TransportError

    h = harness
    h.say("/menu")
    menu = h.transport.last()
    h.transport.fail_next.append(TransportError("timeout", retryable=True))  # edit pertama gagal
    h.press("Budget", menu)
    rows = h.app.replies.for_update("telegram", h.app.inbox.entries()[-1].update_id)
    assert [r.status for r in rows] == [ReplyStatus.SENT, ReplyStatus.PENDING]
    clock.advance(timedelta(seconds=5))
    h.recover()
    assert "Budget" in h.transport.messages[menu.message_id].text
    assert {i.status for i in h.app.inbox.entries()} == {InboxStatus.DELIVERED}


def _committed_update_with_two_messages(h: Harness, update_id: int) -> None:
    """Update yang di-commit dengan dua balasan `send` berurutan (misal pesan panjang)."""
    inbound = Inbound(
        update_id=update_id, user_id=OWNER_TG, chat_id=OWNER_TG, chat_type="private", text="x"
    )
    receipt = h.app.inbox.receive(
        "telegram",
        update_id,
        chat_id=str(OWNER_TG),
        user_id=str(OWNER_TG),
        payload=proc.inbound_to_payload(inbound),
        owner=h.processor.owner,
    )
    rows = [("send", {"chat_id": OWNER_TG, "text": t, "keyboard": []}) for t in ("satu", "dua")]
    with h.app.db.transaction():
        h.app.inbox.commit("telegram", update_id, h.processor.owner, receipt.item.lease_token, rows)


def test_failed_send_holds_back_later_messages(harness: Harness, clock: FakeClock) -> None:
    from studio.interfaces.telegram.transport import TransportError

    h = harness
    _committed_update_with_two_messages(h, 4242)
    h.transport.fail_next.append(TransportError("timeout", retryable=True))
    h.run(h.processor.flush("telegram", 4242))
    assert h.transport.messages == {}  # "dua" tidak boleh mendahului "satu"
    clock.advance(timedelta(seconds=5))
    h.recover()
    assert [m.text for m in h.transport.messages.values()] == ["satu", "dua"]
    assert h.app.inbox.get("telegram", 4242).status is InboxStatus.DELIVERED  # type: ignore[union-attr]


def test_crash_after_last_reply_before_delivered_is_settled(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    _committed_update_with_two_messages(h, 4343)

    def crash(*args: Any) -> bool:
        raise SimulatedCrash("mark_delivered")

    monkeypatch.setattr(h.app.inbox, "mark_delivered", crash)
    with pytest.raises(SimulatedCrash):
        h.run(h.processor.flush("telegram", 4343))
    monkeypatch.undo()
    assert h.app.inbox.get("telegram", 4343).status is InboxStatus.COMMITTED  # type: ignore[union-attr]
    restarted = _restart(h)
    try:
        assert restarted.recover() == 1
        assert [m.text for m in restarted.transport.messages.values()] == [
            "satu",
            "dua",
        ]  # tanpa kirim ulang
        assert restarted.app.inbox.get("telegram", 4343).status is InboxStatus.DELIVERED  # type: ignore[union-attr]
    finally:
        restarted.close()


def test_slow_handler_in_same_process_is_fenced_by_token(
    harness: Harness, clock: FakeClock
) -> None:
    """Pemroses yang sama (owner sama) mengklaim ulang update karena handler pertama lebih lama
    dari lease. Hanya token terbaru yang boleh commit — pemanggilan lama ditolak."""
    h = harness
    episode_id = to_editorial(h)
    card = g1_card(h)
    inbound = Inbound(
        update_id=5151,
        user_id=OWNER_TG,
        chat_id=OWNER_TG,
        chat_type="private",
        callback_id="cb-slow",
        callback_data=card.button("Approve").data,
        message_id=card.message_id,
    )
    first = h.app.inbox.receive(
        "telegram",
        5151,
        chat_id=str(OWNER_TG),
        user_id=str(OWNER_TG),
        payload=proc.inbound_to_payload(inbound),
        owner=h.processor.owner,
    )
    clock.advance(LEASE)
    (second,) = h.app.inbox.claim_due(h.processor.owner)  # klaim ulang, token 2, belum diproses
    assert second.lease_token == first.item.lease_token + 1
    h.run(h.processor._process(first.item, inbound, TG_OWNER))  # pemanggilan lama (token 1)
    assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    item = h.app.inbox.get("telegram", 5151)
    assert item is not None and item.status is InboxStatus.PROCESSING and item.lease_token == 2
    h.run(h.processor._process(second, inbound, TG_OWNER))  # pemegang lease terbaru
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST
    assert _decisions(h.app).count("approve") == 2
