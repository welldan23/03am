"""Use case anggaran: aktivasi periode, otorisasi belanja, laporan pemakaian."""

from __future__ import annotations

from dataclasses import dataclass

from studio.infra.db import Database
from studio.modules.audit import AuditLog
from studio.modules.budget.models import (
    AuthorizationKind,
    BudgetExceededError,
    BudgetPeriod,
    BudgetPlanError,
    Category,
    CategoryUsage,
    LedgerEntry,
    Mode,
    SpendAuthorization,
)
from studio.modules.budget.plan import BudgetPlan
from studio.modules.budget.pricing import CostEstimate
from studio.modules.budget.repository import BudgetRepository
from studio.shared.actors import Actor, OwnerPolicy
from studio.shared.clock import Clock, to_iso
from studio.shared.hashing import canonical_json
from studio.shared.ids import new_id
from studio.shared.money import format_idr


@dataclass(frozen=True)
class BudgetStatus:
    period: str
    mode: Mode
    active: bool
    categories: tuple[CategoryUsage, ...]
    by_source: dict[str, int]
    spendable_total_idr: int

    @property
    def used_idr(self) -> int:
        return sum(c.used_idr for c in self.categories)


class BudgetService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        audit: AuditLog,
        owners: OwnerPolicy,
        plan: BudgetPlan,
    ) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit
        self._owners = owners
        self._plan = plan
        self._repo = BudgetRepository(db)

    @property
    def plan(self) -> BudgetPlan:
        return self._plan

    def current_period(self) -> str:
        return self._plan.period_of(self._clock.now())

    def period(self, period: str | None = None) -> BudgetPeriod | None:
        return self._repo.get_period(period or self.current_period())

    def activate_period(self, actor: Actor, period: str | None = None) -> BudgetPeriod:
        """Owner menyetujui rencana untuk satu bulan. Snapshot alokasi + kurs disimpan."""
        self._owners.require_owner(actor, "mengaktifkan periode anggaran")
        issues = self._plan.issues()
        if issues:
            raise BudgetPlanError("rencana tidak valid: " + "; ".join(issues))
        period = period or self.current_period()
        now = to_iso(self._clock.now())
        cap = self._plan.limits.operational_cap_idr
        with self._db.transaction():
            previous = self._repo.get_period(period)
            self._repo.upsert_period(
                period=period,
                plan=canonical_json(self._plan.snapshot()),
                plan_hash=self._plan.plan_hash,
                fx=self._plan.fx_rate.as_text,
                activated_by=actor.label,
                at=now,
            )
            operational = self._repo.operational_for_period(period)
            if operational is None:
                self._repo.insert_authorization(
                    authorization_id=new_id(self._clock),
                    kind=AuthorizationKind.OPERATIONAL,
                    period=period,
                    episode_id=None,
                    approval_id=None,
                    max_idr=cap,
                    created_by=actor.label,
                    at=now,
                )
            else:
                # Batas diperbarui, pemakaian yang sudah ada tetap terhitung.
                self._repo.update_authorization_max(operational.id, cap)
            self._audit.record(
                actor=actor,
                action="budget.period_reactivated" if previous else "budget.period_activated",
                entity_type="budget_period",
                entity_id=period,
                data={
                    "plan_hash": self._plan.plan_hash,
                    "fx_usd_idr": self._plan.fx_rate.as_text,
                    "operational_cap_idr": cap,
                    "allocations_idr": self._plan.allocations_idr.model_dump(),
                },
            )
        result = self._repo.get_period(period)
        if result is None:  # pragma: no cover - baru saja di-upsert
            raise RuntimeError("periode hilang setelah aktivasi")
        return result

    # --- otorisasi ---------------------------------------------------------

    def operational_authorization(self, period: str | None = None) -> SpendAuthorization | None:
        return self._repo.operational_for_period(period or self.current_period())

    def episode_authorization(
        self, episode_id: str, kind: AuthorizationKind
    ) -> SpendAuthorization | None:
        return self._repo.active_for_episode(episode_id, kind)

    def authorize_episode(
        self,
        *,
        episode_id: str,
        kind: AuthorizationKind,
        approval_id: str,
        max_idr: int,
        actor: Actor,
    ) -> SpendAuthorization:
        """Dipanggil saat owner menyetujui G0 (pra-produksi) atau G2 (produksi)."""
        self._owners.require_owner(actor, f"membuat otorisasi {kind.value}")
        if kind is AuthorizationKind.OPERATIONAL:
            raise ValueError("otorisasi operasional dibuat lewat aktivasi periode")
        now = to_iso(self._clock.now())
        authorization_id = new_id(self._clock)
        with self._db.transaction():
            existing = self._repo.active_for_episode(episode_id, kind)
            if existing is not None:
                self._repo.revoke_authorization(existing.id, "diganti otorisasi baru", now)
            self._repo.insert_authorization(
                authorization_id=authorization_id,
                kind=kind,
                period=None,
                episode_id=episode_id,
                approval_id=approval_id,
                max_idr=max_idr,
                created_by=actor.label,
                at=now,
            )
            self._audit.record(
                actor=actor,
                action="budget.authorization_created",
                entity_type="spend_authorization",
                entity_id=authorization_id,
                episode_id=episode_id,
                data={"kind": kind.value, "max_idr": max_idr, "approval_id": approval_id},
            )
        return self._repo.get_authorization(authorization_id)

    def revoke(
        self,
        *,
        actor: Actor,
        reason: str,
        episode_id: str | None = None,
        approval_ids: list[str] | None = None,
    ) -> list[SpendAuthorization]:
        if episode_id is None and approval_ids is None:
            raise ValueError("isi episode_id atau approval_ids")
        now = to_iso(self._clock.now())
        with self._db.transaction():
            targets = self._repo.authorizations(episode_id=episode_id, approval_ids=approval_ids)
            for auth in targets:
                if auth.kind is AuthorizationKind.OPERATIONAL:
                    continue
                self._repo.revoke_authorization(auth.id, reason, now)
                self._audit.record(
                    actor=actor,
                    action="budget.authorization_revoked",
                    entity_type="spend_authorization",
                    entity_id=auth.id,
                    episode_id=auth.episode_id,
                    data={"kind": auth.kind.value, "reason": reason},
                )
        return [t for t in targets if t.kind is not AuthorizationKind.OPERATIONAL]

    # --- laporan & pengecekan ----------------------------------------------

    def status(self, mode: Mode, period: str | None = None) -> BudgetStatus:
        period = period or self.current_period()
        snapshot = self._repo.get_period(period)
        categories = []
        for category in Category:
            allocation = (
                snapshot.allocation(category)
                if snapshot
                else self._plan.allocations_idr.for_category(category)
            )
            committed, reserved = self._repo.category_usage(period, mode, category)
            categories.append(CategoryUsage(category, allocation, committed, reserved))
        return BudgetStatus(
            period=period,
            mode=mode,
            active=snapshot is not None and snapshot.status == "active",
            categories=tuple(categories),
            by_source=self._repo.usage_by_source(period, mode),
            spendable_total_idr=(
                snapshot.spendable_total if snapshot else self._plan.allocations_idr.spendable_total
            ),
        )

    def authorization_used(self, authorization_id: str, mode: Mode) -> int:
        return self._repo.authorization_usage(authorization_id, mode)

    def check_affordable(self, estimate: CostEstimate, mode: Mode) -> None:
        """Tolak approval G2 kalau batas produksi melebihi sisa alokasi bulan ini."""
        status = self.status(mode)
        if not status.active:
            raise BudgetExceededError(f"periode anggaran {status.period} belum diaktifkan owner")
        remaining = {c.category: c.remaining_idr for c in status.categories}
        problems = [
            f"{category.value}: butuh {format_idr(needed)}, sisa {format_idr(remaining[category])}"
            for category, needed in estimate.cap_by_category().items()
            if needed > remaining[category]
        ]
        if problems:
            raise BudgetExceededError(
                "anggaran tidak cukup untuk produksi — " + "; ".join(problems)
            )

    def ledger(
        self, *, period: str | None = None, episode_id: str | None = None
    ) -> list[LedgerEntry]:
        return self._repo.ledger(period=period, episode_id=episode_id)
