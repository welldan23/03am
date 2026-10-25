"""BudgetGuard: satu-satunya pintu untuk belanja (Studio maupun Hermes).

reserve → commit (biaya aktual) / release (gagal) / commit_at_reserved (hasil tidak jelas).
Semua pengecekan berjalan di satu transaksi `BEGIN IMMEDIATE`, jadi dua reservasi yang
bersamaan tidak bisa sama-sama lolos melewati batas.
"""

from __future__ import annotations

from decimal import Decimal

from studio.infra.db import Database
from studio.modules.audit import AuditLog
from studio.modules.budget.models import (
    AuthorizationKind,
    AuthorizationStatus,
    BudgetExceededError,
    Category,
    HermesPurpose,
    LedgerEntry,
    LedgerStateError,
    LedgerStatus,
    Mode,
    Source,
    SpendRequest,
)
from studio.modules.budget.plan import BudgetPlan
from studio.modules.budget.repository import BudgetRepository
from studio.shared.actors import Actor
from studio.shared.clock import Clock, to_iso
from studio.shared.errors import ConflictError, NotFoundError
from studio.shared.hashing import canonical_json
from studio.shared.ids import new_id
from studio.shared.money import FxRate, format_idr

_GUARD_ACTOR = Actor.system("budget-guard")


class BudgetGuard:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        audit: AuditLog,
        plan: BudgetPlan,
        *,
        paid_providers_enabled: bool,
    ) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit
        self._plan = plan
        self._paid_enabled = paid_providers_enabled
        self._repo = BudgetRepository(db)

    def _check(self, request: SpendRequest, period: str) -> tuple[str | None, int, str]:
        """Kembalikan (alasan_tolak | None, biaya_idr, kurs)."""
        if request.mode is Mode.REAL:
            if not self._paid_enabled:
                return "kill switch aktif: PAID_PROVIDERS_ENABLED=false", 0, ""
            activation = self._plan.paid_activation_issues()
            if activation:
                return "syarat aktivasi berbayar belum terpenuhi: " + "; ".join(activation), 0, ""

        plan_issues = self._plan.issues()
        if plan_issues:
            return "rencana anggaran tidak valid: " + "; ".join(plan_issues), 0, ""

        snapshot = self._repo.get_period(period)
        if snapshot is None or snapshot.status != "active":
            return f"periode anggaran {period} belum diaktifkan owner", 0, ""

        amount = snapshot.fx_rate.to_idr(request.usd_micros)

        try:
            auth = self._repo.get_authorization(request.authorization_id)
        except NotFoundError:
            return "otorisasi tidak dikenal: tidak ada izin belanja dari owner", amount, ""
        if request.source is Source.HERMES:
            # Hermes hanya boleh memakai LLM, dari otorisasi operasional bulan berjalan.
            if request.category is not Category.OPENAI:
                return "Hermes hanya boleh belanja kategori openai", amount, ""
            if auth.kind is not AuthorizationKind.OPERATIONAL:
                return "Hermes hanya boleh memakai otorisasi operasional", amount, ""
            if request.purpose not in {p.value for p in HermesPurpose}:
                return f"purpose Hermes tidak dikenal: {request.purpose}", amount, ""
        if auth.status is not AuthorizationStatus.ACTIVE:
            return f"otorisasi {auth.kind.value} sudah dicabut", amount, snapshot.fx_usd_idr
        if auth.kind is AuthorizationKind.OPERATIONAL and auth.period != period:
            return (
                f"otorisasi operasional bukan untuk periode {period}",
                amount,
                snapshot.fx_usd_idr,
            )
        if auth.episode_id is not None and auth.episode_id != request.episode_id:
            return "otorisasi milik episode lain", amount, snapshot.fx_usd_idr

        auth_used = self._repo.authorization_usage(auth.id, request.mode)
        if auth_used + amount > auth.max_idr:
            return (
                f"batas otorisasi {auth.kind.value} terlampaui: terpakai {format_idr(auth_used)} "
                f"+ {format_idr(amount)} > {format_idr(auth.max_idr)}",
                amount,
                snapshot.fx_usd_idr,
            )

        committed, reserved = self._repo.category_usage(period, request.mode, request.category)
        allocation = snapshot.allocation(request.category)
        if committed + reserved + amount > allocation:
            return (
                f"alokasi {request.category.value} bulan {period} tidak cukup: sisa "
                f"{format_idr(allocation - committed - reserved)}, dibutuhkan {format_idr(amount)}",
                amount,
                snapshot.fx_usd_idr,
            )

        total_used = self._repo.total_usage(period, request.mode)
        if total_used + amount > snapshot.spendable_total:
            return (
                "total anggaran yang bisa dibelanjakan bulan ini habis",
                amount,
                snapshot.fx_usd_idr,
            )
        return None, amount, snapshot.fx_usd_idr

    def reserve(self, request: SpendRequest) -> LedgerEntry:
        """Pesan anggaran sebelum memanggil provider. Idempoten per `idempotency_key`."""
        now = self._clock.now()
        period = self._plan.period_of(now)
        denial: str | None = None
        with self._db.transaction():
            existing = self._repo.ledger_by_key(request.idempotency_key)
            if existing is not None:
                if not request.same_spend_as(existing):
                    raise ConflictError(
                        f"idempotency key {request.idempotency_key} dipakai untuk belanja berbeda"
                    )
                if existing.status is LedgerStatus.RELEASED:
                    # Retry = panggilan baru dengan key baru (ADR-0009), bukan memakai ulang.
                    raise ConflictError(
                        f"idempotency key {request.idempotency_key} sudah dilepas; pakai key baru"
                    )
                return existing

            denial, amount, fx_text = self._check(request, period)
            if denial is not None:
                self._audit.record(
                    actor=_GUARD_ACTOR,
                    action="budget.denied",
                    entity_type="spend_request",
                    entity_id=request.idempotency_key,
                    episode_id=request.episode_id,
                    data={
                        "reason": denial,
                        "category": request.category.value,
                        "source": request.source.value,
                        "purpose": request.purpose,
                        "mode": request.mode.value,
                        "usd_micros": request.usd_micros,
                    },
                )
            else:
                entry_id = new_id(self._clock)
                stamp = to_iso(now)
                self._repo.insert_ledger(
                    {
                        "id": entry_id,
                        "idempotency_key": request.idempotency_key,
                        "period": period,
                        "mode": request.mode.value,
                        "category": request.category.value,
                        "source": request.source.value,
                        "purpose": request.purpose,
                        "authorization_id": request.authorization_id,
                        "episode_id": request.episode_id,
                        "status": "reserved",
                        "reserved_usd_micros": request.usd_micros,
                        "reserved_idr": amount,
                        "fx_usd_idr": fx_text,
                        "price_ref": request.price_ref,
                        "meta": canonical_json(request.meta or {}),
                        "created_at": stamp,
                        "updated_at": stamp,
                    }
                )
                self._audit.record(
                    actor=_GUARD_ACTOR,
                    action="budget.reserved",
                    entity_type="ledger_entry",
                    entity_id=entry_id,
                    episode_id=request.episode_id,
                    data={
                        "idr": amount,
                        "category": request.category.value,
                        "source": request.source.value,
                        "purpose": request.purpose,
                        "mode": request.mode.value,
                        "fx_usd_idr": fx_text,
                    },
                )
                return self._repo.ledger_get(entry_id)
        # Penolakan sudah tercatat (kecuali pemanggil me-rollback transaksi luarnya).
        raise BudgetExceededError(denial or "belanja ditolak")

    def commit(self, entry_id: str, actual_usd_micros: int) -> LedgerEntry:
        """Catat biaya aktual. Kalau melebihi reservasi, tandai `overrun` (uang sudah keluar)."""
        if actual_usd_micros < 0:
            raise ValueError("biaya aktual tidak boleh negatif")
        with self._db.transaction():
            entry = self._repo.ledger_get(entry_id)
            if entry.status.value != "reserved":
                raise LedgerStateError(f"entri {entry_id} berstatus {entry.status.value}")
            fx = FxRate(
                usd_idr=Decimal(entry.fx_usd_idr),
                as_of=entry.created_at.date(),
                source="kurs entri ledger",
            )
            actual_idr = fx.to_idr(actual_usd_micros)
            overrun = actual_idr > entry.reserved_idr
            updated = self._repo.mark_committed(
                entry_id,
                usd_micros=actual_usd_micros,
                idr=actual_idr,
                overrun=overrun,
                at=to_iso(self._clock.now()),
            )
            if updated != 1:  # pragma: no cover - dijaga BEGIN IMMEDIATE
                raise LedgerStateError(f"entri {entry_id} berubah saat di-commit")
            if overrun:
                # Uang sudah keluar: dicatat apa adanya, reservasi berikutnya akan tertahan
                # oleh sisa alokasi yang sekarang lebih kecil (bisa negatif).
                self._audit.record(
                    actor=_GUARD_ACTOR,
                    action="budget.overrun",
                    entity_type="ledger_entry",
                    entity_id=entry_id,
                    episode_id=entry.episode_id,
                    data={
                        "reserved_idr": entry.reserved_idr,
                        "actual_idr": actual_idr,
                        "excess_idr": actual_idr - entry.reserved_idr,
                        "category": entry.category.value,
                        "source": entry.source.value,
                    },
                )
            self._audit.record(
                actor=_GUARD_ACTOR,
                action="budget.committed",
                entity_type="ledger_entry",
                entity_id=entry_id,
                episode_id=entry.episode_id,
                data={"idr": actual_idr, "reserved_idr": entry.reserved_idr, "overrun": overrun},
            )
            return self._repo.ledger_get(entry_id)

    def commit_at_reserved(self, entry_id: str) -> LedgerEntry:
        """Hasil panggilan tidak jelas (misal timeout setelah terkirim): anggap tertagih penuh."""
        entry = self._repo.ledger_get(entry_id)
        return self.commit(entry_id, entry.reserved_usd_micros)

    def release(self, entry_id: str) -> LedgerEntry:
        with self._db.transaction():
            entry = self._repo.ledger_get(entry_id)
            if self._repo.mark_released(entry_id, to_iso(self._clock.now())) != 1:
                raise LedgerStateError(f"entri {entry_id} berstatus {entry.status.value}")
            self._audit.record(
                actor=_GUARD_ACTOR,
                action="budget.released",
                entity_type="ledger_entry",
                entity_id=entry_id,
                episode_id=entry.episode_id,
                data={"reserved_idr": entry.reserved_idr},
            )
            return self._repo.ledger_get(entry_id)

    def spend(self, request: SpendRequest, actual_usd_micros: int | None = None) -> LedgerEntry:
        """Reserve + commit sekaligus (untuk mock yang biayanya langsung diketahui)."""
        with self._db.transaction():
            entry = self.reserve(request)
            if entry.status is LedgerStatus.COMMITTED:
                return entry  # idempoten: belanja yang sama sudah pernah dicatat
            return self.commit(
                entry.id, request.usd_micros if actual_usd_micros is None else actual_usd_micros
            )
