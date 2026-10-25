"""Rencana anggaran bulanan dari `config/budget.yaml` (ADR-0010)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from studio.modules.budget.models import BudgetPlanError, Category
from studio.shared.errors import ConfigError
from studio.shared.hashing import content_hash
from studio.shared.money import FxRate, format_idr, parse_usd


def _no_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError('tulis angka desimal sebagai string, contoh "9.50"')
    return value


class FxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    usd_idr: Decimal = Field(gt=0)
    as_of: date
    source: str

    _check_float = field_validator("usd_idr", mode="before")(_no_float)


class VpsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    planned_usd: Decimal = Field(ge=0)
    actual_usd: Decimal | None = Field(default=None, ge=0)

    _check_float = field_validator("planned_usd", "actual_usd", mode="before")(_no_float)


class Allocations(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    higgsfield: int = Field(ge=0)
    openai: int = Field(ge=0)
    tts: int = Field(ge=0)
    reserve: int = Field(ge=0)

    def for_category(self, category: Category) -> int:
        return int(getattr(self, category.value))

    @property
    def spendable_total(self) -> int:
        return self.higgsfield + self.openai + self.tts

    @property
    def total(self) -> int:
        return self.spendable_total + self.reserve


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operational_cap_idr: int = Field(ge=0)
    preproduction_cap_idr: int = Field(ge=0)
    production_margin_pct: int = Field(ge=0, le=100)


class BudgetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    monthly_budget_idr: int = Field(gt=0, strict=True)
    timezone: str
    fx: FxConfig
    vps: VpsConfig
    allocations_idr: Allocations
    limits: Limits

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"timezone tidak dikenal: {value}") from exc
        return value

    # --- turunan -----------------------------------------------------------

    @property
    def fx_rate(self) -> FxRate:
        return FxRate(usd_idr=self.fx.usd_idr, as_of=self.fx.as_of, source=self.fx.source)

    @property
    def vps_cost_idr(self) -> int:
        """Biaya VPS yang dipakai untuk alokasi (berdasarkan `planned_usd`)."""
        return self.fx_rate.to_idr(parse_usd(self.vps.planned_usd))

    @property
    def vps_actual_idr(self) -> int | None:
        if self.vps.actual_usd is None:
            return None
        return self.fx_rate.to_idr(parse_usd(self.vps.actual_usd))

    @property
    def total_planned_idr(self) -> int:
        return self.vps_cost_idr + self.allocations_idr.total

    @property
    def worst_case_total_idr(self) -> int:
        """Total dengan biaya VPS terbesar antara rencana dan aktual."""
        vps = max(self.vps_cost_idr, self.vps_actual_idr or 0)
        return vps + self.allocations_idr.total

    def period_of(self, moment: datetime) -> str:
        return moment.astimezone(ZoneInfo(self.timezone)).strftime("%Y-%m")

    @property
    def vps_needs_recalculation(self) -> bool:
        return self.vps.actual_usd is not None and self.vps.actual_usd != self.vps.planned_usd

    def issues(self) -> list[str]:
        """Masalah yang membuat SEMUA belanja baru (simulasi maupun nyata) ditolak."""
        if self.worst_case_total_idr > self.monthly_budget_idr:
            return [
                f"total rencana {format_idr(self.worst_case_total_idr)} melebihi anggaran "
                f"bulanan {format_idr(self.monthly_budget_idr)}"
            ]
        return []

    @property
    def is_valid(self) -> bool:
        return not self.issues()

    def paid_activation_issues(self) -> list[str]:
        """Syarat tambahan sebelum provider berbayar boleh diaktifkan."""
        problems = self.issues()
        if self.vps.actual_usd is None:
            problems.append("biaya VPS aktual belum diisi (vps.actual_usd); VPS belum dibeli")
        elif self.vps_needs_recalculation:
            problems.append(
                "biaya VPS aktual berbeda dari rencana; jalankan `studio budget recalc` dan "
                "setujui alokasi baru"
            )
        return problems

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @property
    def plan_hash(self) -> str:
        return content_hash(self.snapshot())


def load_plan(path: Path) -> BudgetPlan:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"file rencana anggaran tidak ada: {path}") from exc
    try:
        return BudgetPlan.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"rencana anggaran tidak valid ({path}):\n{exc}") from exc


@dataclass(frozen=True)
class ReallocationProposal:
    plan: BudgetPlan
    old_vps_idr: int
    new_vps_idr: int
    changes: dict[str, int]


def propose_reallocation(plan: BudgetPlan, actual_vps_usd: Decimal) -> ReallocationProposal:
    """Usulan alokasi baru untuk biaya VPS aktual. Tidak menulis config apa pun.

    Kelebihan biaya diambil dari cadangan dulu, lalu dari alokasi variabel secara
    proporsional (pembulatan largest-remainder supaya totalnya pas). Kalau VPS lebih murah,
    selisihnya masuk cadangan.
    """
    new_vps_idr = plan.fx_rate.to_idr(parse_usd(actual_vps_usd))
    alloc = plan.allocations_idr
    reserve = alloc.reserve
    variable = {c: alloc.for_category(c) for c in Category}

    room = plan.monthly_budget_idr - new_vps_idr - reserve - sum(variable.values())
    if room >= 0:
        reserve += room
    else:
        need = -room
        from_reserve = min(need, reserve)
        reserve -= from_reserve
        need -= from_reserve
        total_variable = sum(variable.values())
        if need > total_variable:
            raise BudgetPlanError("biaya VPS aktual melebihi seluruh anggaran bulanan")
        if need > 0:
            shares = {c: need * v // total_variable for c, v in variable.items()}
            leftover = need - sum(shares.values())
            by_remainder = sorted(
                variable, key=lambda c: (need * variable[c]) % total_variable, reverse=True
            )
            for category in by_remainder[:leftover]:
                shares[category] += 1
            variable = {c: v - shares[c] for c, v in variable.items()}

    new_alloc = Allocations(
        higgsfield=variable[Category.HIGGSFIELD],
        openai=variable[Category.OPENAI],
        tts=variable[Category.TTS],
        reserve=reserve,
    )
    new_plan = plan.model_copy(
        update={
            "vps": VpsConfig(planned_usd=actual_vps_usd, actual_usd=actual_vps_usd),
            "allocations_idr": new_alloc,
        }
    )
    changes = {
        name: getattr(new_alloc, name) - getattr(alloc, name)
        for name in ("higgsfield", "openai", "tts", "reserve")
    }
    return ReallocationProposal(
        plan=new_plan, old_vps_idr=plan.vps_cost_idr, new_vps_idr=new_vps_idr, changes=changes
    )
