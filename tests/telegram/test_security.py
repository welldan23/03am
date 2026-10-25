"""Owner authentication & otorisasi: allowlist user ID, chat pribadi, callback tidak dipercaya."""

import io
import logging

import pytest
import structlog

from studio.interfaces.telegram import texts
from studio.modules.controller import EpisodeFilter, StudioController
from studio.modules.episodes import EpisodeStatus as S
from studio.shared.actors import Actor
from studio.shared.config import Settings
from studio.shared.errors import NotAuthorizedError
from studio.shared.logging import SecretFilter, configure_logging, get_logger
from tests.conftest import OWNER, AppFactory
from tests.telegram.conftest import TG_OWNER
from tests.telegram.fakes import OWNER_TG, STRANGER_TG, Harness, g1_card, to_editorial

FAKE_TOKEN = "123456789:AAFakeTokenUntukTestSajaYangPanjang0"


def test_stranger_gets_nothing_and_is_audited(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    before = len(h.transport.messages)
    for text in (
        "/start",
        "Tunjukkan hasil risetnya.",
        "/budget",
        "Tampilkan episode yang belum saya approve.",
    ):
        h.say(text, user_id=STRANGER_TG)
    stranger_messages = [m for m in h.transport.messages.values() if m.chat_id == STRANGER_TG]
    # Hanya satu balasan generik (dibatasi), tanpa isi episode/riset/budget.
    assert [m.text for m in stranger_messages] == [texts.NOT_OWNER]
    assert len(h.transport.messages) == before + 1
    entries = h.app.audit.entries(action="telegram.unauthorized")
    assert len(entries) == 1 and entries[0].entity_id == str(STRANGER_TG)
    # Tidak ada state yang dibuat untuk orang asing.
    assert (
        h.app.db.scalar(
            "SELECT COUNT(*) FROM ui_conversations WHERE chat_id = ?", (str(STRANGER_TG),)
        )
        == 0
    )


def test_stranger_cannot_press_owner_buttons(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    card = g1_card(h)
    h.tap(card.button("Approve"), card, user_id=STRANGER_TG)
    assert h.transport.answers[-1][1] == texts.NOT_OWNER
    assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    # Tombol owner tetap berfungsi untuk owner (tidak terpakai oleh percobaan orang asing).
    h.press("Approve", card)
    assert h.app.episodes.get(episode_id).status is S.ESTIMATING_COST


def test_group_chats_are_ignored(harness: Harness) -> None:
    h = harness
    to_editorial(h)
    count = len(h.transport.messages)
    h.say("/start", chat_type="group")
    h.say("Tunjukkan hasil risetnya.", chat_type="supergroup")
    assert len(h.transport.messages) == count
    card = g1_card(h)
    h.tap(card.button("Approve"), card, chat_type="group")
    assert h.transport.answers[-1][1] == texts.NOT_PRIVATE
    assert h.app.approvals.pending()[0].status.value == "pending"


def test_identity_is_numeric_user_id_from_allowlist(make_app: AppFactory) -> None:
    app = make_app(owner_ids=f"cli:owner,telegram:{OWNER_TG}")
    controller: StudioController = app.controller
    assert controller.is_owner(controller.actor_for("telegram", OWNER_TG))
    assert not controller.is_owner(controller.actor_for("telegram", STRANGER_TG))
    # Username / format lain tidak pernah menjadi identitas.
    assert not controller.is_owner(controller.actor_for("telegram", "studio_owner"))
    assert Settings(
        _env_file=None, owner_ids="telegram:42,telegram:abc,cli:x"
    ).telegram_owner_ids == ("42",)


def test_controller_refuses_non_owner_reads_and_writes(tg_app: object) -> None:
    from studio.bootstrap import App

    assert isinstance(tg_app, App)
    controller = tg_app.controller
    stranger = Actor.owner(f"telegram:{STRANGER_TG}")
    director = Actor.director("hermes")
    for actor in (stranger, director):
        with pytest.raises(NotAuthorizedError):
            controller.list_episodes(actor, EpisodeFilter.ALL)
        with pytest.raises(NotAuthorizedError):
            controller.budget_dashboard(actor)
        with pytest.raises(NotAuthorizedError):
            controller.pending_approvals(actor)
        with pytest.raises(NotAuthorizedError):
            controller.press(actor, "aaaaaaaaaaaaa")


def test_forged_callbacks_are_refused(harness: Harness) -> None:
    h = harness
    episode_id = to_editorial(h)
    card = g1_card(h)
    for forged in (
        "a:aaaaaaaaaaaaa",
        "a:",
        "zz:what",
        "e:" + "X" * 26,
        "ap:01NOTANAPPROVAL0000000000",
    ):
        h.tap(forged, card)
    assert h.app.episodes.get(episode_id).status is S.AWAITING_EDITORIAL
    assert any(
        "tidak dikenal" in text.lower() or "tidak ditemukan" in text.lower()
        for _, text, _ in h.transport.answers
    )
    refused = h.app.audit.entries(action="ui.action_refused")
    assert refused and all(e.data["reason"] == "unknown" for e in refused)


def test_action_codes_are_bound_to_the_owner_who_received_them(make_app: AppFactory) -> None:
    app = make_app(owner_ids=f"telegram:{OWNER_TG},telegram:2002")
    app.budget.activate_period(TG_OWNER)
    other = Actor.owner("telegram:2002")
    card = app.controller.confirm_activate_budget(TG_OWNER)
    result = app.controller.press(other, card.codes["yes"])
    assert result.outcome.value == "refused" and "bukan untuk akun Anda" in result.message
    assert app.controller.press(TG_OWNER, card.codes["yes"]).outcome.value == "done"


def test_cli_owner_cannot_impersonate_telegram_owner() -> None:
    from studio.interfaces.cli.main import parse_actor
    from studio.shared.errors import StudioError

    with pytest.raises(StudioError):
        parse_actor(f"telegram:{OWNER_TG}")
    assert OWNER.id == "cli:owner"


def test_bot_token_never_appears_in_logs_or_repr(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(_env_file=None, telegram_bot_token=FAKE_TOKEN)
    assert FAKE_TOKEN not in repr(settings) and FAKE_TOKEN not in str(settings.model_dump())
    # structlog (konfigurasi global dipulihkan supaya test lain tidak menulis ke stderr capsys)
    try:
        configure_logging("INFO", extra_secrets=frozenset({FAKE_TOKEN}))
        get_logger("test").warning(
            "request.failed", url=f"https://api.telegram.org/bot{FAKE_TOKEN}/getMe"
        )
        assert FAKE_TOKEN not in capsys.readouterr().err
    finally:
        structlog.reset_defaults()
        for target in (logging.getLogger(), *logging.getLogger().handlers):
            for f in [f for f in target.filters if isinstance(f, SecretFilter)]:
                target.removeFilter(f)
    # logging standar (aiogram/aiohttp)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretFilter(frozenset({FAKE_TOKEN})))
    logger = logging.getLogger("aiogram.test")
    logger.addHandler(handler)
    try:
        logger.error("gagal %s", f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage")
        try:
            raise RuntimeError(f"boom {FAKE_TOKEN}")
        except RuntimeError:
            logger.exception("crash")
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert FAKE_TOKEN not in output and "***" in output


def test_bot_settings_check_without_network() -> None:
    from studio.interfaces.telegram.runner import check_bot_settings

    assert len(check_bot_settings(Settings(_env_file=None))) == 2
    assert (
        check_bot_settings(
            Settings(
                _env_file=None, telegram_bot_token=FAKE_TOKEN, owner_ids=f"telegram:{OWNER_TG}"
            )
        )
        == []
    )
    bad = check_bot_settings(
        Settings(
            _env_file=None, telegram_bot_token="tanpa-titik-dua", owner_ids=f"telegram:{OWNER_TG}"
        )
    )
    assert bad and "format" in bad[0]


def test_g0_requires_owner_choice_via_card(harness: Harness) -> None:
    h = harness
    to_editorial(h)  # G0 dipilih lewat tombol kartu
    decided = h.app.audit.entries(action="approval.decided")
    assert decided[0].actor == TG_OWNER.label and decided[0].data["data"]["choice"] == 1
    # Kartu G0 diganti hasil keputusan (tanpa tombol) supaya tidak bisa ditekan lagi.
    assert not any("G0 · Pilih topik" in m.text for m in h.transport.messages.values())
    chosen = next(m for m in h.transport.messages.values() if "Topik dipilih" in m.text)
    assert not any("✅ 1" in b.text for b in chosen.buttons())


def test_user_text_cannot_inject_html(harness: Harness) -> None:
    h = harness
    h.say("Buat dokumenter tentang <b>Krakatau</b> & <script>, format 40 detik, kategori sejarah")
    confirm = h.transport.last().text
    assert (
        "&lt;b&gt;Krakatau&lt;/b&gt; &amp; &lt;script&gt;" in confirm and "<script>" not in confirm
    )
    h.say("tunjukkan riset #<i>zz</i>")
    assert "<i>zz" not in h.transport.last().text
