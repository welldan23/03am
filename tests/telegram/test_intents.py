"""Intent router deterministik: contoh kalimat dari brief + kasus ambigu."""

import pytest

from studio.bootstrap import load_editorial_config
from studio.interfaces.telegram.intents import IntentName, RuleBasedIntentParser
from studio.modules.episodes import Category, DocumentaryFormat
from studio.modules.scripting import SegmentRole
from tests.conftest import REPO_ROOT

_, SCRIPTING = load_editorial_config(REPO_ROOT / "config" / "editorial.yaml")
PARSER = RuleBasedIntentParser(SCRIPTING)


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Cari topik sejarah yang menarik.", IntentName.CREATE),
        ("Buat dokumenter tentang Krakatau.", IntentName.CREATE),
        ("Pilih format 90 detik.", IntentName.SET_FORMAT),
        ("Tunjukkan hasil risetnya.", IntentName.SHOW_RESEARCH),
        ("Ringkas bagian pembuka.", IntentName.SHOW_SEGMENT),
        ("Naskahnya terlalu kaku, buat lebih natural.", IntentName.REVISE_SCRIPT),
        ("Apa sumber untuk klaim ini?", IntentName.CLAIM_SOURCES),
        ("Berapa estimasi biaya episode ini?", IntentName.EPISODE_COST),
        ("Tampilkan episode yang belum saya approve.", IntentName.LIST_PENDING),
        ("Budget bulan ini berapa?", IntentName.BUDGET),
        ("status produksi", IntentName.STATUS),
        ("daftar episode aktif", IntentName.LIST_EPISODES),
        ("bantuan", IntentName.HELP),
        ("batal", IntentName.CANCEL_STEP),
        ("halo apa kabar", IntentName.UNKNOWN),
    ],
)
def test_brief_examples_are_routed(text: str, name: IntentName) -> None:
    assert PARSER.parse(text).name is name


def test_slots_are_extracted() -> None:
    intent = PARSER.parse("Buat dokumenter tentang Krakatau, format 90 detik, kategori sejarah")
    assert intent.topic == "Krakatau"
    assert intent.format is DocumentaryFormat.ARCHIVES and intent.duration_s == 90
    assert intent.category is Category.SEJARAH
    assert PARSER.parse("Cari topik sejarah yang menarik.").category is Category.SEJARAH
    assert PARSER.parse("Ringkas bagian penutup").segment is SegmentRole.CLOSING
    assert PARSER.parse("Apa sumber klaim C-krak-sound?").claim_id == "C-krak-sound"
    assert PARSER.parse("Naskahnya terlalu kaku").notes == "Naskahnya terlalu kaku"


@pytest.mark.parametrize(
    ("text", "seconds", "fmt"),
    [
        ("format 40 detik", 40, DocumentaryFormat.QUICK_FILES),
        ("150 detik saja", 150, DocumentaryFormat.DEEP_FILES),
    ],
)
def test_duration_maps_to_the_containing_format(
    text: str, seconds: int, fmt: DocumentaryFormat
) -> None:
    intent = PARSER.parse(text)
    assert intent.duration_s == seconds and intent.format is fmt


@pytest.mark.parametrize(
    ("text", "ambiguity"),
    [
        ("format 60 detik", "duration"),  # di antara rentang format → jangan menebak
        ("quick files 120 detik", "duration"),  # format & durasi bertentangan
        ("quick atau deep", "format"),
        ("misteri sejarah", "category"),
    ],
)
def test_ambiguous_slots_are_left_empty(text: str, ambiguity: str) -> None:
    intent = PARSER.parse(text)
    assert ambiguity in intent.ambiguities
    if ambiguity in ("duration", "format"):
        assert intent.format is None and intent.duration_s is None
    else:
        assert intent.category is None


@pytest.mark.parametrize(
    "text", ["setujui", "Setuju saja", "approve semuanya", "tolak", "oke setujui episode itu"]
)
def test_decisions_are_never_taken_from_free_text(text: str) -> None:
    assert PARSER.parse(text).name is IntentName.DECISION_BY_TEXT


def test_episode_reference_by_short_id() -> None:
    assert PARSER.parse("tunjukkan riset #ABC123").episode_ref == "ABC123"


@pytest.mark.parametrize(
    "text",
    [
        "Buat dokumenter tentang naskah kuno Nusantara",
        "Tolong bikin video tentang biaya perang dunia",
        "buatkan satu episode tentang sumber mata air",
    ],
)
def test_create_at_sentence_start_wins_over_topic_words(text: str) -> None:
    intent = PARSER.parse(text)
    assert intent.name is IntentName.CREATE and intent.topic
