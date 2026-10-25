"""Tabel harga provider dan estimasi biaya (USD mikro → IDR, dibulatkan ke atas)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from studio.modules.budget.models import Category
from studio.shared.errors import ConfigError
from studio.shared.money import FxRate, apply_margin_ceil, ceil_div, parse_usd


class Price(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category
    unit: str
    per_units: int = Field(gt=0, strict=True)
    usd: Decimal = Field(ge=0)

    @field_validator("usd", mode="before")
    @classmethod
    def _no_float(cls, value: Any) -> Any:
        if isinstance(value, float):
            raise ValueError('tulis harga sebagai string, contoh "0.40"')
        return value

    @property
    def usd_micros(self) -> int:
        return parse_usd(self.usd)


class PricingTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    verified_at: date | None
    prices: dict[str, Price]

    def price(self, key: str) -> Price:
        try:
            return self.prices[key]
        except KeyError as exc:
            raise ConfigError(f"harga '{key}' tidak ada di tabel harga {self.version}") from exc

    def cost_usd_micros(self, key: str, quantity: int) -> int:
        if quantity < 0:
            raise ValueError("kuantitas tidak boleh negatif")
        price = self.price(key)
        return ceil_div(quantity * price.usd_micros, price.per_units)

    def ref(self, key: str) -> str:
        return f"{self.version}:{key}"

    def llm_call_usd_micros(self, tier: str, input_tokens: int, output_tokens: int) -> int:
        """Biaya satu panggilan LLM. Tiap putaran tool call / retry = satu panggilan."""
        return self.cost_usd_micros(f"openai.{tier}.input", input_tokens) + self.cost_usd_micros(
            f"openai.{tier}.output", output_tokens
        )


def load_pricing(path: Path) -> PricingTable:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"file tabel harga tidak ada: {path}") from exc
    try:
        return PricingTable.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"tabel harga tidak valid ({path}):\n{exc}") from exc


@dataclass(frozen=True)
class EstimateLine:
    price_key: str
    quantity: int
    label: str


@dataclass(frozen=True)
class EstimatedLine:
    price_key: str
    label: str
    category: Category
    quantity: int
    usd_micros: int
    idr: int


@dataclass(frozen=True)
class CostEstimate:
    lines: tuple[EstimatedLine, ...]
    fx: FxRate
    pricing_version: str
    margin_pct: int

    @property
    def total_idr(self) -> int:
        return sum(line.idr for line in self.lines)

    @property
    def cap_idr(self) -> int:
        return apply_margin_ceil(self.total_idr, self.margin_pct)

    def by_category(self) -> dict[Category, int]:
        totals: dict[Category, int] = {}
        for line in self.lines:
            totals[line.category] = totals.get(line.category, 0) + line.idr
        return totals

    def cap_by_category(self) -> dict[Category, int]:
        return {c: apply_margin_ceil(v, self.margin_pct) for c, v in self.by_category().items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [
                {
                    "price_key": line.price_key,
                    "label": line.label,
                    "category": line.category.value,
                    "quantity": line.quantity,
                    "usd_micros": line.usd_micros,
                    "idr": line.idr,
                }
                for line in self.lines
            ],
            "total_idr": self.total_idr,
            "cap_idr": self.cap_idr,
            "margin_pct": self.margin_pct,
            "fx_usd_idr": self.fx.as_text,
            "fx_as_of": self.fx.as_of.isoformat(),
            "fx_source": self.fx.source,
            "pricing_version": self.pricing_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostEstimate:
        return cls(
            lines=tuple(
                EstimatedLine(
                    price_key=line["price_key"],
                    label=line["label"],
                    category=Category(line["category"]),
                    quantity=line["quantity"],
                    usd_micros=line["usd_micros"],
                    idr=line["idr"],
                )
                for line in data["lines"]
            ),
            fx=FxRate(
                usd_idr=Decimal(data["fx_usd_idr"]),
                as_of=date.fromisoformat(data["fx_as_of"]),
                source=data["fx_source"],
            ),
            pricing_version=data["pricing_version"],
            margin_pct=data["margin_pct"],
        )


def estimate(
    pricing: PricingTable, lines: list[EstimateLine], *, fx: FxRate, margin_pct: int
) -> CostEstimate:
    estimated = []
    for line in lines:
        usd_micros = pricing.cost_usd_micros(line.price_key, line.quantity)
        estimated.append(
            EstimatedLine(
                price_key=line.price_key,
                label=line.label,
                category=pricing.price(line.price_key).category,
                quantity=line.quantity,
                usd_micros=usd_micros,
                idr=fx.to_idr(usd_micros),
            )
        )
    return CostEstimate(
        lines=tuple(estimated), fx=fx, pricing_version=pricing.version, margin_pct=margin_pct
    )
