"""Alur Telegram end-to-end dengan fake transport (offline): buat dokumenter → G0 → riset →
naskah → G1, review riset/naskah, percakapan natural, dan klarifikasi saat ambigu."""

from studio.interfaces.telegram import texts
from studio.modules.episodes import DocumentaryFormat
from studio.modules.episodes import EpisodeStatus as S
from studio.modules.notifications import NotificationStatus
from tests.conftest import AppFactory
from tests.telegram.conftest import TG_OWNER
from tests.telegram.fakes import OWNER_TG, Harness, create_episode, g0_card, g1_card, to_editorial


def test_start_shows_main_menu(harness: Harness) -> None:
    harness.say("/start")
    labels = [b.text for b in harness.transport.last().buttons()]
    for item in (
        "Buat Dokumenter",
        "Episode Aktif",
        "Ide Topik",
        "Review Riset",
        "Review Naskah",
        "Approval",
        "Status Produksi",
        "Budget",
        "Pengaturan",
    ):
        assert any(item in label for label in labels), item
    for command in ("/help", "/menu", "/status", "/episodes", "/budget"):
        harness.say(command)
        assert harness.transport.last().text


def test_create_documentary_with_buttons(harness: Harness) -> None:
    h = harness
    h.say("/menu")
    h.press("Buat Dokumenter")
    assert texts.ASK_FORMAT in h.transport.last().text
    h.press("Deep Files")
    assert texts.ASK_CATEGORY in h.transport.last().text
    h.press("Sains")
    assert "Buat dokumenter ini?" in h.transport.last().text
    assert h.app.episodes.list_episodes() == []  # belum ada apa pun sebelum konfirmasi
    h.press("Ya, lanjutkan")
    (episode,) = h.app.episodes.list_episodes()
    assert episode.format is DocumentaryFormat.DEEP_FILES and episode.target_duration_s == 135
    assert episode.status is S.DISCOVERING
    h.work_and_notify()
    card = g0_card(h)
    assert "Topik siap dipilih" in card.text and "Dentuman Krakatau 1883" in card.text
    assert h.app.episodes.get(episode.id).status is S.AWAITING_TOPIC


def test_full_flow_to_g1_with_notifications(harness: Harness) -> None:
    h = harness
    episode_id = create_episode(h, "Cari topik sejarah yang menarik")
    assert h.app.episodes.get(episode_id).idea is None
    h.press("✅ 1", g0_card(h))
    assert "Topik dipilih: Dentuman Krakatau 1883" in h.transport.last().text
    h.work_and_notify()
    joined = "\n".join(h.transport.texts())
    for marker in (
        "Riset dimulai",
        "ResearchBrief selesai",
        "Naskah selesai",
        "G1 menunggu approval",
    ):
        assert marker in joined, marker
    assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    assert all(n.status is NotificationStatus.SENT for n in h.app.outbox.entries())
    # G1 tetap keputusan owner — dan tidak ada yang otomatis
    assert h.app.approvals.pending(episode_id)[0].gate.value == "G1"
    h.press("Approve", g1_card(h))
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST


def test_research_and_script_review_with_pagination(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    h.say("Tunjukkan hasil risetnya.")
    summary = h.transport.last()
    assert "ResearchBrief" in summary.text and "Mutu riset" in summary.text
    h.press("✅ 8", summary)  # fakta terverifikasi
    page1 = h.transport.last()
    assert "Fakta terverifikasi (8)" in page1.text and "1/2" in [b.text for b in page1.buttons()]
    h.press("▶️", page1)
    assert "<b>5.</b>" in h.transport.last().text
    h.press("Ringkasan riset")
    h.press("Sumber (9)")
    assert "fixture.03am.invalid" in h.transport.last().text
    h.press("Ringkasan riset")
    h.press("⚖️ 2")
    disputed = h.transport.last().text
    assert "dibantah" in disputed
    h.say("Ringkas bagian pembuka.")
    hook = h.transport.last()
    assert "Hook" in hook.text and "C-krak-sound" in hook.text
    h.press("Context ▶️", hook)
    assert "Context" in h.transport.last().text
    h.say("Tampilkan naskahnya")
    overview = h.transport.last()
    assert "Estimasi" in overview.text and "Editorial gate: ✅ LULUS" in overview.text
    h.press("Editorial", overview)
    assert "Laporan editorial" in h.transport.last().text
    assert (
        h.app.conversations.get("telegram", str(OWNER_TG), TG_OWNER.label).current_episode_id
        == episode_id
    )


def test_claim_sources_and_cost(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    h.say("Apa sumber untuk klaim ini?")
    picker = h.transport.last()
    assert texts.ASK_CLAIM in picker.text  # "klaim ini" ambigu → bot menawarkan pilihan
    h.press("1.", picker)
    assert "Sumber klaim" in h.transport.last().text
    h.say("Apa sumber klaim C-krak-sound?")
    detail = h.transport.last().text
    assert "KRK-S3" in detail and "❝" in detail and "fixture.03am.invalid" in detail
    h.say("Berapa estimasi biaya episode ini?")
    cost = h.transport.last().text
    assert "Pra-produksi" in cost and "dari batas Rp5.000" in cost and "simulasi" in cost


def test_ambiguity_asks_instead_of_guessing(harness: Harness) -> None:
    h = harness
    h.say("format 60 detik")
    reply = h.transport.last().text
    assert "tidak cocok dengan format mana pun" in reply and texts.ASK_FORMAT in reply
    h.say("misteri sejarah")
    assert "lebih dari satu kategori" in h.transport.last().text
    assert h.app.episodes.list_episodes() == []


def test_episode_is_not_guessed_when_several_exist(harness: Harness, make_app: AppFactory) -> None:
    h = harness
    first = to_editorial(h)
    second = to_editorial(h)
    # konteks percakapan sekarang = episode kedua; buang konteks untuk menguji pertanyaan balik
    conv = h.app.conversations.get("telegram", str(OWNER_TG), TG_OWNER.label)
    h.app.conversations.save(type(conv)(conv.channel, conv.chat_id, conv.actor))
    h.say("Tunjukkan hasil risetnya.")
    ask = h.transport.last()
    assert texts.ASK_EPISODE in ask.text
    assert {first[-6:], second[-6:]} <= {b.text[-6:] for b in ask.buttons()} | {
        line.split("#")[-1][:6] for line in ask.text.splitlines() if "#" in line
    }


def test_decisions_by_text_are_refused(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    h.say("setujui saja")
    assert texts.DECISION_BY_TEXT.split(".")[0] in h.transport.last().text
    assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL


def test_episode_list_pagination(harness: Harness) -> None:
    h = harness
    for _ in range(6):
        h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
        h.press("Ya, lanjutkan")
    h.say("/episodes")
    first = h.transport.last()
    assert "Episode aktif</b> (6)" in first.text and "1/2" in [b.text for b in first.buttons()]
    h.press("▶️", first)
    assert "2/2" in [b.text for b in h.transport.last().buttons()]


def test_create_requires_active_budget_period(make_app: AppFactory) -> None:
    app = make_app(owner_ids=f"telegram:{OWNER_TG}")
    h = Harness(app)
    try:
        h.say("Buat dokumenter tentang Krakatau, format 40 detik, kategori sejarah")
        h.press("Ya, lanjutkan")
        assert any("belum diaktifkan" in text for _, text, _ in h.transport.answers)
        assert app.episodes.list_episodes() == []
        h.say("/budget")
        h.press("Aktifkan periode")
        h.press("Ya, lanjutkan")
        assert app.budget.period() is not None
        assert app.audit.entries(action="budget.period_activated")[0].actor == TG_OWNER.label
    finally:
        h.close()
