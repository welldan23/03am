from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from studio.shared.clock import from_iso
from studio.shared.errors import NonRetryableError, StudioError
from studio.shared.money import FxRate


class Category(StrEnum):
    """Kategori belanja yang punya alokasi bulanan."""

    OPENAI = "openai"
    HIGGSFIELD = "higgsfield"
    TTS = "tts"


class Mode(StrEnum):
    SIMULATED = "simulated"  # mock provider
    REAL = "real"  # provider berbayar


class Source(StrEnum):
    STUDIO = "studio"
    HERMES = "hermes"


class LedgerStatus(StrEnum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"


class AuthorizationKind(StrEnum):
    OPERATIONAL = "operational"
    PREPRODUCTION = "preproduction"
    PRODUCTION = "production"


class AuthorizationStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class BudgetError(NonRetryableError):
    pass


class BudgetExceededError(BudgetError):
    """Belanja ditolak guard. `reason` menjelaskan aturan mana yang menolak."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BudgetPlanError(StudioError):
    pass


class LedgerStateError(StudioError):
    pass


@dataclass(frozen=True)
class SpendRequest:
    idempotency_key: str
    category: Category
    source: Source
    purpose: str
    mode: Mode
    authorization_id: str
    usd_micros: int
    price_ref: str
    episode_id: str | None = None
    meta: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.usd_micros < 0:
            raise ValueError("biaya tidak boleh negatif")
        if not self.idempotency_key:
            raise ValueError("idempotency_key wajib diisi")


@dataclass(frozen=True)
class LedgerEntry:
    id: str
    idempotency_key: str
    period: str
    mode: Mode
    category: Category
    source: Source
    purpose: str
    authorization_id: str
    episode_id: str | None
    status: LedgerStatus
    reserved_usd_micros: int
    reserved_idr: int
    actual_usd_micros: int | None
    actual_idr: int | None
    fx_usd_idr: str
    price_ref: str
    overrun: bool
    meta: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> LedgerEntry:
        return cls(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            period=row["period"],
            mode=Mode(row["mode"]),
            category=Category(row["category"]),
            source=Source(row["source"]),
            purpose=row["purpose"],
            authorization_id=row["authorization_id"],
            episode_id=row["episode_id"],
            status=LedgerStatus(row["status"]),
            reserved_usd_micros=row["reserved_usd_micros"],
            reserved_idr=row["reserved_idr"],
            actual_usd_micros=row["actual_usd_micros"],
            actual_idr=row["actual_idr"],
            fx_usd_idr=row["fx_usd_idr"],
            price_ref=row["price_ref"],
            overrun=bool(row["overrun"]),
            meta=json.loads(row["meta"]),
            created_at=from_iso(row["created_at"]),
        )


@dataclass(frozen=True)
class SpendAuthorization:
    id: str
    kind: AuthorizationKind
    period: str | None
    episode_id: str | None
    approval_id: str | None
    max_idr: int
    status: AuthorizationStatus
    created_by: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SpendAuthorization:
        return cls(
            id=row["id"],
            kind=AuthorizationKind(row["kind"]),
            period=row["period"],
            episode_id=row["episode_id"],
            approval_id=row["approval_id"],
            max_idr=row["max_idr"],
            status=AuthorizationStatus(row["status"]),
            created_by=row["created_by"],
        )


@dataclass(frozen=True)
class BudgetPeriod:
    period: str
    status: str
    plan: dict[str, Any]
    plan_hash: str
    fx_usd_idr: str
    activated_by: str
    activated_at: datetime

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> BudgetPeriod:
        return cls(
            period=row["period"],
            status=row["status"],
            plan=json.loads(row["plan"]),
            plan_hash=row["plan_hash"],
            fx_usd_idr=row["fx_usd_idr"],
            activated_by=row["activated_by"],
            activated_at=from_iso(row["activated_at"]),
        )

    @property
    def fx_rate(self) -> FxRate:
        fx = self.plan["fx"]
        return FxRate(
            usd_idr=Decimal(fx["usd_idr"]),
            as_of=date.fromisoformat(fx["as_of"]),
            source=fx["source"],
        )

    def allocation(self, category: Category) -> int:
        return int(self.plan["allocations_idr"][category.value])

    @property
    def spendable_total(self) -> int:
        return sum(self.allocation(c) for c in Category)


@dataclass(frozen=True)
class CategoryUsage:
    category: Category
    allocation_idr: int
    committed_idr: int
    reserved_idr: int

    @property
    def used_idr(self) -> int:
        return self.committed_idr + self.reserved_idr

    @property
    def remaining_idr(self) -> int:
        return self.allocation_idr - self.used_idr
