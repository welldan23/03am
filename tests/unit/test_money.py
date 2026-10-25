from datetime import date
from decimal import Decimal

import pytest

from studio.shared.money import (
    FxRate,
    apply_margin_ceil,
    ceil_div,
    format_idr,
    format_usd,
    parse_usd,
)

FX = FxRate(usd_idr=Decimal("17850"), as_of=date(2026, 10, 25), source="test")


def test_parse_usd_exact() -> None:
    assert parse_usd("9.50") == 9_500_000
    assert parse_usd("0.000001") == 1
    assert parse_usd(3) == 3_000_000


@pytest.mark.parametrize("bad", ["0.0000001", "-1", "abc"])
def test_parse_usd_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_usd(bad)


def test_parse_usd_rejects_float() -> None:
    with pytest.raises(TypeError):
        parse_usd(9.5)  # type: ignore[arg-type]


def test_vps_reference_cost_matches_owner_plan() -> None:
    assert FX.to_idr(parse_usd("9.50")) == 169_575


def test_usd_to_idr_rounds_up() -> None:
    assert FX.to_idr(1) == 1  # 0,01785 rupiah → dibulatkan ke atas
    assert FX.to_idr(0) == 0
    assert FX.to_idr(56) == 1  # 0,9996
    assert FX.to_idr(57) == 2  # 1,01745


def test_fx_must_be_positive() -> None:
    with pytest.raises(ValueError):
        FxRate(usd_idr=Decimal(0), as_of=date(2026, 1, 1), source="x")


def test_margin_and_ceil_div() -> None:
    assert apply_margin_ceil(22_197, 20) == 26_637
    assert apply_margin_ceil(100, 0) == 100
    assert ceil_div(7, 2) == 4
    with pytest.raises(ValueError):
        ceil_div(1, 0)


def test_formatting() -> None:
    assert format_idr(169_575) == "Rp169.575"
    assert format_idr(500_000) == "Rp500.000"
    assert format_idr(-1_500) == "-Rp1.500"
    assert format_usd(9_500_000) == "$9.50"
    assert format_usd(4_000) == "$0.004"
