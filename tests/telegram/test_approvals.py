"""Approval G0–G3 lewat inline keyboard: kode sekali pakai, replay, klik ganda konkuren,
kartu basi setelah revisi, approval/tombol kedaluwarsa, dan revisi lewat workflow."""

import threading
from datetime import timedelta
from pathlib import Path

from studio.interfaces.telegram import texts
from studio.interfaces.telegram.types import MAX_CALLBACK_BYTES
from studio.modules.artifacts import ArtifactKind
from studio.modules.budget import Mode
from studio.modules.controller import Outcome
from studio.modules.episodes import EpisodeStatus as S
from studio.shared.clock import FakeClock
from tests.conftest import AppFactory
from tests.telegram.conftest import TG_OWNER
from tests.telegram.fakes import OWNER_TG, Harness, g1_card, to_editorial


def _decisions(h: Harness) -> list[str]:
    return [e.data["decision"] for e in h.app.audit.entries(action="approval.decided")]


def test_every_button_fits_callback_limit_and_carries_no_secrets(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    h.say("Tunjukkan hasil risetnya.")
    h.say("Tampilkan naskahnya")
    for message in h.transport.messages.values():
        for b in message.buttons():
            assert len(b.data.encode()) <= MAX_CALLBACK_BYTES, b
            if b.data.startswith("a:"):
                assert len(b.data) == 2 + 13  # kode acak pendek, bukan token/ID approval
    stored = h.app.db.query_all("SELECT payload FROM ui_action_codes")
    assert stored and all("token" not in row["payload"] for row in stored)


def test_card_button_replay_is_refused(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    card = g1_card(h)
    approve = card.button("Approve")
    h.tap(approve, card)
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST
    version = h.app.episodes.get(episode_id).version
    h.tap(approve, card)  # klik ulang tombol yang sama (update baru)
    h.tap(card.button("Reject") if card.buttons() else approve, card)
    assert h.transport.answers[-1][2] is True  # alert penolakan
    assert h.app.episodes.get(episode_id).version == version
    assert _decisions(h).count("approve") == 2  # G0 + G1, bukan tiga


def test_duplicate_telegram_update_is_processed_once(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    card = g1_card(h)
    first = h.tap(card.button("Approve"), card, update_id=9999)
    h.tap(card.button("Approve"), card, update_id=first.update_id)  # Telegram kirim ulang
    assert _decisions(h).count("approve") == 2
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST


def test_concurrent_double_click_executes_once(make_app: AppFactory, tmp_path: Path) -> None:
    """Dua koneksi database (mis. dua proses bot) menekan kode yang sama bersamaan."""
    first = make_app(owner_ids=f"telegram:{OWNER_TG}")
    first.budget.activate_period(TG_OWNER)
    h = Harness(first)
    try:
        episode_id = to_editorial(h)
        approval = first.approvals.pending(episode_id)[0]
        card = first.controller.approval_card(TG_OWNER, approval.id)
        code = card.codes["approve"]
        apps = [make_app(owner_ids=f"telegram:{OWNER_TG}") for _ in range(4)]
        barrier = threading.Barrier(len(apps))
        outcomes: list[Outcome] = []
        lock = threading.Lock()

        def click(app: object) -> None:
            barrier.wait()
            result = app.controller.press(TG_OWNER, code)  # type: ignore[attr-defined]
            with lock:
                outcomes.append(result.outcome)

        threads = [threading.Thread(target=click, args=(a,)) for a in apps]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(o.value for o in outcomes) == ["done", "refused", "refused", "refused"]
        assert first.episodes.get(episode_id).status is S.ESTIMATING_COST
        assert len(first.audit.entries(episode_id=episode_id, action="approval.decided")) == 2
    finally:
        h.close()


def test_old_card_is_refused_after_content_is_revised(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    old_card = g1_card(h)
    version_before = h.app.episodes.get(episode_id).version
    h.say("Naskahnya terlalu kaku, buat lebih natural.")
    h.press("Ya, lanjutkan")
    episode = h.app.episodes.get(episode_id)
    assert episode.status is S.SCRIPTING and episode.version > version_before
    h.tap(old_card.button("Approve"), old_card)
    assert h.transport.answers[-1][2] is True
    h.work_and_notify()
    new_card = g1_card(h)
    assert new_card.message_id != old_card.message_id
    # Editorial gate dijalankan ulang untuk naskah baru (revisi 2, catatan owner terbawa).
    script = h.app.controller.script(TG_OWNER, episode_id).script
    assert script.notes == "Naskahnya terlalu kaku, buat lebih natural."
    assert len(h.app.artifacts.versions(episode_id, ArtifactKind.EDITORIAL_REPORT)) == 2
    statuses = [
        a.status.value for a in h.app.approvals.for_episode(episode_id) if a.gate.value == "G1"
    ]
    assert sorted(statuses) == ["pending", "revision_requested"]
    h.press("Approve", new_card)
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST


def test_request_revision_via_buttons(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    card = g1_card(h)
    h.press("Request Revision", card)
    revise = h.transport.last()
    labels = [b.text for b in revise.buttons()]
    assert "Tulis ulang naskah" in labels and "Riset ulang" in labels and "⬅️ Kembali" in labels
    # Tombol kartu lama sudah hangus (satu kartu = satu grup kode)
    h.tap(card.buttons()[0] if card.buttons() else revise.button("Kembali"), card)
    h.press("Tulis ulang naskah", revise)
    assert texts.ASK_REVISION_NOTES.split("(")[0] in h.transport.last().text
    assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL  # belum diputuskan
    h.say("Perlambat tempo bagian penutup.")
    episode = h.app.episodes.get(episode_id)
    assert episode.status is S.SCRIPTING
    revised = [
        e for e in h.app.audit.entries(action="approval.decided") if e.data["decision"] == "revise"
    ]
    assert revised[0].data["notes"] == "Perlambat tempo bagian penutup."
    h.work_and_notify()
    assert (
        h.app.controller.script(TG_OWNER, episode_id).script.notes
        == "Perlambat tempo bagian penutup."
    )


def test_revision_notes_step_survives_restart_and_can_be_cancelled(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    h.press("Request Revision", g1_card(h))
    h.press("Tulis ulang naskah")
    restarted = Harness(h.app, first_update_id=10_000)  # bot baru; state dari SQLite
    try:
        restarted.say("batal")
        assert texts.STEP_CANCELLED in restarted.transport.last().text
        restarted.say("Perlambat tempo")
        assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    finally:
        restarted.close()


def test_expired_approval_offers_reissue(harness: Harness, clock: FakeClock) -> None:
    h = harness
    episode_id = to_editorial(h)
    approval = h.app.approvals.pending(episode_id)[0]
    card = h.app.controller.approval_card(TG_OWNER, approval.id)
    clock.advance(timedelta(hours=73))  # approval TTL 72 jam
    result = h.app.controller.press(TG_OWNER, card.codes["approve"])
    assert result.outcome is Outcome.REFUSED  # kode tombol ikut kedaluwarsa (≤ masa approval)
    # Lewat bot: daftar menandai kedaluwarsa → buka → langsung ditawari terbit ulang
    h.say("Tampilkan episode yang belum saya approve.")
    assert "sudah kedaluwarsa" in h.transport.last().text
    h.press("G1")
    assert "Terbitkan ulang approval?" in h.transport.last().text
    h.press("Ya, lanjutkan")
    fresh = h.app.approvals.pending(episode_id)
    assert len(fresh) == 1 and fresh[0].id != approval.id
    h.press("Approve")
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST


def test_action_code_expires_after_ttl(harness: Harness, clock: FakeClock) -> None:
    h = harness
    to_editorial(h)
    card = g1_card(h)
    clock.advance(timedelta(minutes=h.app.settings.action_ttl_minutes + 1))
    h.press("Approve", card)
    assert "kedaluwarsa" in h.transport.answers[-1][1]


def test_g2_and_g3_cards_are_labelled_as_simulation(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    h.press("Approve", g1_card(h))
    h.work_and_notify()
    g2 = next(m for m in reversed(list(h.transport.messages.values())) if "G2" in m.text)
    assert texts.SIMULATION_NOTE in g2.text
    h.press("Approve", g2)
    h.work_and_notify()
    g3 = next(m for m in reversed(list(h.transport.messages.values())) if "G3" in m.text)
    assert texts.SIMULATION_NOTE in g3.text
    h.press("Approve", g3)
    h.work_and_notify()
    assert h.app.episodes.get(episode_id).status is S.EXPORTED
    assert "Episode selesai" in "\n".join(h.transport.texts())
    assert h.app.budget.status(Mode.REAL).used_idr == 0


def test_reject_closes_episode(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    h.press("Reject", g1_card(h))
    assert h.app.episodes.get(episode_id).status is S.REJECTED
    h.work_and_notify()
    assert "Episode ditutup (REJECTED)" in "\n".join(h.transport.texts())


def test_failed_script_revision_goes_through_retry(make_app: AppFactory, tmp_path: Path) -> None:
    from studio.providers.llm.mock import MockLLMProvider
    from tests.integration.test_script_pipeline import _fixtures

    app = make_app(
        owner_ids=f"telegram:{OWNER_TG}",
        llm_provider_factory=lambda t: MockLLMProvider(
            t,
            fixture_dirs=[_fixtures(tmp_path, revision_bad=True)],
            overrides={"script_generation": "buruk", "script_revision": "buruk"},
        ),
    )
    app.budget.activate_period(TG_OWNER)
    h = Harness(app)
    try:
        episode_id = to_editorial(h)
        episode = app.episodes.get(episode_id)
        assert episode.status is S.FAILED and episode.failed_from is S.SCRIPTING
        failed = next(m for m in h.transport.messages.values() if "Episode gagal" in m.text)
        h.press("Revisi naskah", failed)
        h.say("Hapus klaim suhu global dan hindari kata sensasional.")
        confirm = h.transport.last()
        assert "tahap naskah diulang dengan catatan ini" in confirm.text
        h.press("Ya, lanjutkan", confirm)
        episode = app.episodes.get(episode_id)
        assert episode.status is S.SCRIPTING
        jobs = [j for j in app.queue.list_jobs(episode_id=episode_id) if j.status.value == "queued"]
        assert jobs[0].payload["notes"] == "Hapus klaim suhu global dan hindari kata sensasional."
        # Naskah yang diulang tetap melewati editorial gate (dan gagal lagi dengan fixture buruk).
        h.work_and_notify()
        assert app.episodes.get(episode_id).status is S.FAILED
        assert app.approvals.pending(episode_id) == []
    finally:
        h.close()


def test_resent_text_update_is_ignored(harness: Harness) -> None:
    """Telegram mengirim ulang update teks yang sama (restart/timeout) → diproses sekali."""
    from studio.interfaces.telegram.types import Inbound

    h = harness
    inbound = Inbound(
        update_id=777,
        user_id=OWNER_TG,
        chat_id=OWNER_TG,
        chat_type="private",
        text="Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah",
    )
    h.run(h.bot.handle(inbound))
    h.run(h.bot.handle(inbound))
    confirms = [m for m in h.transport.messages.values() if "Buat dokumenter ini?" in m.text]
    assert len(confirms) == 1
    assert h.app.db.scalar("SELECT COUNT(*) FROM ui_action_codes") == 2  # satu kartu (ya/batal)


def test_g2_detail_shows_estimate_per_category_fx_and_remaining(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    h.press("Approve", g1_card(h))
    h.work_and_notify()
    g2 = next(m for m in reversed(list(h.transport.messages.values())) if "G2" in m.text)
    assert "Batas belanja yang disetujui" in g2.text
    h.press("Detail", g2)
    detail = h.transport.last().text
    for expected in (
        "Estimasi produksi (G2, simulasi)",
        "Higgsfield",
        "sisa anggaran",
        "batas maksimum",
        "Kurs USD/IDR 17.850",
    ):
        assert expected in detail, expected
