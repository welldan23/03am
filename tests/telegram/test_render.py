"""callback_data ≤ 64 byte, pemecahan pesan 4096 karakter, pagination, tampilan budget."""

from pathlib import Path

import pytest

from studio.bootstrap import App
from studio.interfaces.telegram import render
from studio.interfaces.telegram.callbacks import CallbackError, decode, encode
from studio.interfaces.telegram.types import MAX_CALLBACK_BYTES, MAX_MESSAGE_CHARS
from studio.modules.controller import Page
from tests.conftest import AppFactory, edit_budget
from tests.telegram.conftest import TG_OWNER
from tests.telegram.fakes import OWNER_TG


def test_callback_data_limit_is_enforced() -> None:
    ulid = "01M6FJ4Z80DSB6ZPTTXVK8HTQF"
    data = encode("r", ulid, "fact", 12)
    assert len(data.encode()) <= MAX_CALLBACK_BYTES
    assert decode(data).parts == (ulid, "fact", "12")
    with pytest.raises(CallbackError):
        encode("r", ulid, "x" * 40)
    with pytest.raises(CallbackError):
        encode("r", "a:b")  # pemisah tidak boleh disusupkan
    with pytest.raises(CallbackError):
        decode("x" * 65)


def test_long_messages_are_split_on_line_boundaries() -> None:
    text = "\n".join(f"baris {i} " + "x" * 90 for i in range(200))
    chunks = render.split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= MAX_MESSAGE_CHARS for c in chunks)
    assert "\n".join(chunks) == text
    giant = "y" * (MAX_MESSAGE_CHARS * 2 + 10)
    assert [len(c) for c in render.split_text(giant)] == [4096, 4096, 10]


@pytest.mark.parametrize(
    ("page", "expected"), [(0, [0, 1, 2]), (1, [3, 4, 5]), (3, [9]), (99, [9]), (-5, [0, 1, 2])]
)
def test_page_is_clamped(page: int, expected: list[int]) -> None:
    result = Page.of(list(range(10)), page, 3)
    assert result.items == expected and result.pages == 4 and result.total == 10


def test_pager_buttons() -> None:
    assert render.pager("pa", [], 0, 1) == []
    labels = [b.text for b in render.pager("pa", [], 1, 3)]
    assert labels == ["◀️", "2/3", "▶️"]


def test_budget_dashboard_shows_plan_from_config(tg_app: App) -> None:
    screen = render.budget_screen(tg_app.controller.budget_dashboard(TG_OWNER))
    for expected in (
        "Rp500.000",
        "Rp169.575",
        "OpenAI + Hermes</b>: Rp60.000",
        "Higgsfield</b>: Rp190.000",
        "TTS</b>: Rp25.000",
        "Cadangan</b>: Rp55.425",
        "17.850",
        "SIMULASI",
        "NONAKTIF",
    ):
        assert expected in screen.text, expected
    assert "terpakai simulasi Rp0 · real Rp0" in screen.text


def test_exchange_rate_comes_from_config_not_code(make_app: AppFactory, config_dir: Path) -> None:
    edit_budget(config_dir, lambda d: d["fx"].__setitem__("usd_idr", "18000"))
    app = make_app(owner_ids=f"telegram:{OWNER_TG}")
    screen = render.budget_screen(app.controller.budget_dashboard(TG_OWNER))
    assert "18.000" in screen.text and "17.850" not in screen.text
    assert "BELUM DIAKTIFKAN" in screen.text
    assert any("Aktifkan periode" in b.text for row in screen.keyboard for b in row)
