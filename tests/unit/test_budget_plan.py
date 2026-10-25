from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from studio.modules.budget import BudgetPlanError, load_plan, propose_reallocation
from studio.modules.budget.plan import BudgetPlan
from studio.shared.errors import ConfigError
from tests.conftest import REPO_ROOT, edit_budget


def _plan(config_dir: Path) -> BudgetPlan:
    return load_plan(config_dir / "budget.yaml")


def _set(path: list[str], value: Any) -> Any:
    def mutate(data: dict[str, Any]) -> None:
        node = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutate


def test_default_plan_matches_owner_budget() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    assert plan.fx.usd_idr == Decimal("17850")
    assert plan.monthly_budget_idr == 500_000
    assert plan.vps_cost_idr == 169_575
    alloc = plan.allocations_idr
    assert (alloc.higgsfield, alloc.openai, alloc.tts, alloc.reserve) == (
        190_000,
        60_000,
        25_000,
        55_425,
    )
    assert plan.total_planned_idr == 500_000
    assert plan.is_valid
    assert alloc.spendable_total == 275_000


def test_paid_activation_blocked_until_vps_actual_known() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    assert any("VPS aktual belum diisi" in p for p in plan.paid_activation_issues())


def test_fx_rate_is_configurable_and_can_invalidate_plan(config_dir: Path) -> None:
    edit_budget(config_dir, _set(["fx", "usd_idr"], "18000"))
    plan = _plan(config_dir)
    assert plan.vps_cost_idr == 171_000
    assert plan.total_planned_idr == 501_425
    assert not plan.is_valid
    assert "melebihi anggaran" in plan.issues()[0]


@pytest.mark.parametrize(
    "path",
    [["fx", "usd_idr"], ["vps", "planned_usd"]],
)
def test_decimal_values_must_not_be_float(config_dir: Path, path: list[str]) -> None:
    edit_budget(config_dir, _set(path, 17850.5))
    with pytest.raises(ConfigError, match="string"):
        _plan(config_dir)


def test_allocations_must_be_integer_rupiah(config_dir: Path) -> None:
    edit_budget(config_dir, _set(["allocations_idr", "tts"], 25000.5))
    with pytest.raises(ConfigError):
        _plan(config_dir)


def test_vps_actual_higher_blocks_all_spending(config_dir: Path) -> None:
    edit_budget(config_dir, _set(["vps", "actual_usd"], "11.00"))
    plan = _plan(config_dir)
    assert plan.vps_actual_idr == 196_350
    assert not plan.is_valid  # 196.350 + 330.425 > 500.000
    assert any("berbeda dari rencana" in p for p in plan.paid_activation_issues())


def test_vps_actual_lower_still_requires_recalculation(config_dir: Path) -> None:
    edit_budget(config_dir, _set(["vps", "actual_usd"], "8.00"))
    plan = _plan(config_dir)
    assert plan.is_valid
    assert plan.vps_needs_recalculation
    assert any("berbeda dari rencana" in p for p in plan.paid_activation_issues())


def test_vps_actual_equal_to_plan_allows_paid_activation(config_dir: Path) -> None:
    edit_budget(config_dir, _set(["vps", "actual_usd"], "9.50"))
    assert _plan(config_dir).paid_activation_issues() == []


def test_reallocation_takes_from_reserve_first() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    proposal = propose_reallocation(plan, Decimal("11.00"))
    assert proposal.new_vps_idr == 196_350
    assert proposal.changes == {"higgsfield": 0, "openai": 0, "tts": 0, "reserve": -26_775}
    assert proposal.plan.total_planned_idr == 500_000
    assert proposal.plan.paid_activation_issues() == []


def test_reallocation_cuts_variable_allocations_proportionally() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    proposal = propose_reallocation(plan, Decimal("15.00"))
    new = proposal.plan.allocations_idr
    assert new.reserve == 0
    assert proposal.plan.total_planned_idr == 500_000
    assert new.higgsfield < 190_000 and new.openai < 60_000 and new.tts < 25_000
    # Proporsional: Higgsfield menanggung pemotongan terbesar.
    assert -proposal.changes["higgsfield"] > -proposal.changes["openai"] > -proposal.changes["tts"]


def test_reallocation_cheaper_vps_goes_to_reserve() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    proposal = propose_reallocation(plan, Decimal("8.00"))
    assert proposal.changes["reserve"] == 169_575 - 142_800
    assert proposal.plan.total_planned_idr == 500_000


def test_reallocation_impossible_when_vps_exceeds_budget() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    with pytest.raises(BudgetPlanError):
        propose_reallocation(plan, Decimal("30.00"))


def test_period_uses_jakarta_timezone() -> None:
    plan = load_plan(REPO_ROOT / "config" / "budget.yaml")
    assert plan.period_of(datetime(2026, 10, 31, 18, 0, tzinfo=UTC)) == "2026-11"
    assert plan.period_of(datetime(2026, 10, 31, 16, 0, tzinfo=UTC)) == "2026-10"


def test_unknown_config_keys_are_rejected(config_dir: Path) -> None:
    edit_budget(config_dir, _set(["allocations_idr", "marketing"], 1000))
    with pytest.raises(ConfigError):
        _plan(config_dir)
