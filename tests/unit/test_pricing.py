import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from studio.modules.budget import Category, CostEstimate, EstimateLine, estimate, load_pricing
from studio.shared.errors import ConfigError
from studio.shared.money import FxRate
from tests.conftest import REPO_ROOT

PRICING = load_pricing(REPO_ROOT / "config" / "pricing.yaml")
FX = FxRate(usd_idr=Decimal("17850"), as_of=date(2026, 10, 25), source="test")


def test_pricing_is_marked_placeholder_until_verified() -> None:
    assert PRICING.verified_at is None
    assert "placeholder" in PRICING.version


def test_unit_cost_rounds_up_to_micro_dollar() -> None:
    assert PRICING.cost_usd_micros("openai.fast.input", 1) == 1  # 0,4 mikro → 1
    assert PRICING.cost_usd_micros("openai.fast.input", 1_000_000) == 400_000
    assert PRICING.cost_usd_micros("higgsfield.video_second", 15) == 1_050_000


def test_llm_call_cost_counts_input_and_output() -> None:
    cost = PRICING.llm_call_usd_micros("smart", input_tokens=3000, output_tokens=1000)
    assert cost == 6_000 + 8_000


def test_unknown_price_key_is_config_error() -> None:
    with pytest.raises(ConfigError):
        PRICING.cost_usd_micros("openai.mega.input", 1)


def test_estimate_records_fx_and_pricing_version() -> None:
    result = estimate(
        PRICING,
        [
            EstimateLine("higgsfield.video_second", 15, "video"),
            EstimateLine("higgsfield.image", 9, "gambar"),
            EstimateLine("tts.characters", 900, "suara"),
        ],
        fx=FX,
        margin_pct=20,
    )
    assert [line.idr for line in result.lines] == [18_743, 3_213, 241]
    assert result.total_idr == 22_197
    assert result.cap_idr == 26_637
    assert result.by_category() == {Category.HIGGSFIELD: 21_956, Category.TTS: 241}
    data = result.to_dict()
    assert data["fx_usd_idr"] == "17850"
    assert data["fx_as_of"] == "2026-10-25"
    assert data["pricing_version"] == PRICING.version
    assert CostEstimate.from_dict(data) == result


MONEY_FILES = [
    *sorted((REPO_ROOT / "src/studio/modules/budget").glob("*.py")),
    REPO_ROOT / "src/studio/shared/money.py",
]


@pytest.mark.parametrize("path", MONEY_FILES, ids=lambda p: p.name)
def test_no_float_in_money_code(path: Path) -> None:
    """Uang harus int/Decimal: tidak ada literal float, `float(...)`, atau anotasi float."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            offenders.append(f"literal {node.value} baris {node.lineno}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
        ):
            offenders.append(f"float() baris {node.lineno}")
        annotations = []
        if isinstance(node, ast.arg | ast.AnnAssign) and node.annotation is not None:
            annotations.append(node.annotation)
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            annotations.append(node.returns)
        for annotation in annotations:
            if "float" in ast.unparse(annotation):
                offenders.append(f"anotasi float baris {annotation.lineno}")
    assert offenders == []
