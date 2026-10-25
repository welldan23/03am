"""MeteredCaller: satu-satunya jalur ke provider LLM (TD-01 + ADR-0009).

Alur satu panggilan:
1. Transaksi singkat: heartbeat lease, cek catatan panggilan dengan idempotency key yang sama.
   - sudah `succeeded`  → pakai ulang respons tersimpan (tidak membayar lagi);
   - masih `in_flight`  → worker sebelumnya mati di tengah panggilan: hasil TIDAK DIKETAHUI.
     Tanpa jaminan idempotensi dari provider, panggilan TIDAK diulang; biaya dicatat sebesar
     reservasi dan tahap gagal dengan alasan jelas;
   - `unknown`          → tetap ditolak (menunggu keputusan owner);
   - `failed`           → boleh dicoba lagi sebagai attempt baru (tidak tertagih sebelumnya).
2. Reservasi anggaran lewat BudgetGuard (transaksi sendiri, penolakan teraudit), lalu catat
   panggilan `in_flight` bersama tiket belanja.
3. Panggil provider DI LUAR transaksi (tidak ada write lock SQLite yang ditahan).
4. Transaksi singkat: commit biaya aktual + simpan respons. Hasil ini adalah FAKTA biaya dan
   boleh dipakai ulang lewat key yang sama, tetapi menerima hasil TAHAP (artefak, transisi)
   tetap hanya lewat `Lease.finish` dengan cek fencing token & versi episode.
"""

from __future__ import annotations

import math
import sqlite3

from studio.infra.db import Database
from studio.infra.jobs import LeaseLostError
from studio.modules.audit import AuditLog
from studio.modules.budget import (
    AuthorizationKind,
    BudgetGuard,
    BudgetService,
    Category,
    Mode,
    PricingTable,
    Source,
    SpendAuthorization,
    SpendRequest,
)
from studio.modules.calls.models import (
    CallScope,
    CallStatus,
    MissingAuthorizationError,
    NonRetryableProviderCallError,
    ProviderCall,
    ProviderCallFailedError,
    ProviderOutcomeUnknownError,
)
from studio.modules.calls.repository import ProviderCallRepository
from studio.providers.errors import ProviderError, ProviderTimeoutError
from studio.providers.llm.ports import LLMProvider, LLMRequest, LLMResponse
from studio.providers.tickets import TicketAuthority
from studio.shared.actors import Actor
from studio.shared.clock import Clock, to_iso
from studio.shared.errors import ConflictError
from studio.shared.hashing import canonical_json
from studio.shared.ids import new_id

_ACTOR = Actor.system("metered-caller")


class MeteredCaller:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        audit: AuditLog,
        guard: BudgetGuard,
        budget: BudgetService,
        pricing: PricingTable,
        provider: LLMProvider,
        tickets: TicketAuthority,
        *,
        chars_per_token: int,
    ) -> None:
        self._db = db
        self._clock = clock
        self._audit = audit
        self._guard = guard
        self._budget = budget
        self._pricing = pricing
        self._provider = provider
        self._tickets = tickets
        self._chars_per_token = chars_per_token
        self._repo = ProviderCallRepository(db)

    @property
    def mode(self) -> Mode:
        return Mode.SIMULATED if self._provider.billing_mode == "simulated" else Mode.REAL

    def estimate_input_tokens(self, request: LLMRequest) -> int:
        return math.ceil((len(request.system) + len(request.user)) / self._chars_per_token)

    def calls_for_episode(self, episode_id: str) -> list[ProviderCall]:
        return self._repo.for_episode(episode_id)

    def _authorization(self, scope: CallScope) -> SpendAuthorization:
        if scope.authorization is AuthorizationKind.OPERATIONAL:
            auth = self._budget.operational_authorization()
        elif scope.episode_id is None:
            auth = None
        else:
            auth = self._budget.episode_authorization(scope.episode_id, scope.authorization)
        if auth is None:
            reason = f"tidak ada otorisasi {scope.authorization.value} yang aktif"
            with self._db.transaction():
                self._audit.record(
                    actor=_ACTOR,
                    action="budget.denied",
                    entity_type="provider_call",
                    entity_id=scope.key_prefix,
                    episode_id=scope.episode_id,
                    data={"reason": reason},
                )
            raise MissingAuthorizationError(reason)
        return auth

    def call(
        self,
        scope: CallScope,
        request: LLMRequest,
        *,
        purpose: str,
        source: Source = Source.STUDIO,
    ) -> tuple[LLMResponse, ProviderCall, bool]:
        """Jalankan satu panggilan termeter. Mengembalikan (respons, catatan, dipakai_ulang)."""
        scope.lease.require_outside_transaction("panggilan provider")
        key = request.idempotency_key
        fingerprint = request.fingerprint
        unknown: ProviderOutcomeUnknownError | None = None

        # --- 1. cek catatan lama (transaksi singkat) -------------------------------
        with self._db.transaction():
            scope.lease.heartbeat()
            existing = self._repo.by_key(key)
            if existing is not None and existing.request_fingerprint != fingerprint:
                raise ConflictError(f"idempotency key {key} dipakai untuk request berbeda")
            if existing is not None and existing.status is CallStatus.SUCCEEDED:
                self._audit.record(
                    actor=_ACTOR,
                    action="provider_call.reused",
                    entity_type="provider_call",
                    entity_id=existing.id,
                    episode_id=existing.episode_id,
                    data={"task": existing.task},
                )
            elif existing is not None and existing.status is CallStatus.UNKNOWN:
                unknown = ProviderOutcomeUnknownError(
                    f"hasil panggilan {existing.task} sebelumnya tidak diketahui; tidak diulang "
                    "otomatis — owner perlu memutuskan"
                )
            elif (
                existing is not None
                and existing.status is CallStatus.IN_FLIGHT
                and not self._provider.idempotent_replay
            ):
                # Worker sebelumnya mati di tengah panggilan. Mengulang = risiko bayar dua kali.
                self._repo.settle(
                    existing.id,
                    attempt=existing.attempt,
                    status=CallStatus.UNKNOWN,
                    at=to_iso(self._clock.now()),
                    error="worker berhenti saat panggilan berjalan; hasil tidak diketahui",
                )
                self._guard.commit_at_reserved(existing.ledger_entry_id)
                self._audit.record(
                    actor=_ACTOR,
                    action="provider_call.unknown",
                    entity_type="provider_call",
                    entity_id=existing.id,
                    episode_id=existing.episode_id,
                    data={"task": existing.task, "reason": "in_flight saat recovery"},
                )
                unknown = ProviderOutcomeUnknownError(
                    f"panggilan {existing.task} terputus di tengah jalan; biaya dicatat sebesar "
                    "reservasi dan panggilan tidak diulang otomatis"
                )
        if unknown is not None:
            raise unknown
        if existing is not None and existing.status is CallStatus.SUCCEEDED:
            if existing.response is None:  # pragma: no cover - dijaga CHECK constraint
                raise ConflictError("panggilan sukses tanpa respons")
            return _response_of(existing), existing, True

        # --- 2. reservasi + catat in_flight ----------------------------------------
        if existing is not None and existing.status is CallStatus.IN_FLIGHT:
            call = existing  # provider menjamin idempotensi: replay dengan key yang sama
        else:
            call = self._reserve_and_record(scope, request, purpose, source, existing)

        # --- 3. panggil provider di luar transaksi ---------------------------------
        ticket = self._tickets.issue(fingerprint, call.ledger_entry_id, call.authorization_id)
        try:
            response = self._provider.complete(request, ticket)
        except ProviderTimeoutError as exc:
            self._settle_unknown(call, f"{type(exc).__name__}: {exc}")
            raise ProviderOutcomeUnknownError(
                f"panggilan {request.task} timeout setelah terkirim; biaya dicatat sebesar "
                "reservasi dan tidak diulang otomatis"
            ) from exc
        except ProviderError as exc:
            self._settle_failed(call, f"{type(exc).__name__}: {exc}")
            error_cls = ProviderCallFailedError if exc.retryable else NonRetryableProviderCallError
            raise error_cls(f"panggilan {request.task} gagal: {exc}") from exc

        # --- 4. catat hasil & biaya aktual (transaksi singkat) ---------------------
        actual_usd = self._pricing.llm_call_usd_micros(
            request.tier, response.input_tokens, response.output_tokens
        )
        with self._db.transaction():
            current = self._repo.get(call.id)
            if current.status is not CallStatus.IN_FLIGHT or current.attempt != call.attempt:
                # Worker lain sudah menangani panggilan ini (kita basi); catatannya yang berlaku.
                raise LeaseLostError(f"hasil panggilan {call.id} datang terlambat (worker basi)")
            entry = self._guard.commit(call.ledger_entry_id, actual_usd)
            settled = self._repo.settle(
                call.id,
                attempt=call.attempt,
                status=CallStatus.SUCCEEDED,
                at=to_iso(self._clock.now()),
                response=canonical_json(
                    {
                        "text": response.text,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "model": response.model,
                    }
                ),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                actual_cost_idr=entry.actual_idr,
                model=response.model,
            )
            if settled != 1:  # pragma: no cover - dijaga pengecekan di atas + BEGIN IMMEDIATE
                raise LeaseLostError(f"hasil panggilan {call.id} datang terlambat (worker basi)")
        return response, self._repo.get(call.id), False

    def _reserve_and_record(
        self,
        scope: CallScope,
        request: LLMRequest,
        purpose: str,
        source: Source,
        existing: ProviderCall | None,
    ) -> ProviderCall:
        auth = self._authorization(scope)
        attempt = 1 if existing is None else existing.attempt + 1
        estimated_input = self.estimate_input_tokens(request)
        estimated_usd = self._pricing.llm_call_usd_micros(
            request.tier, estimated_input, request.max_output_tokens
        )
        # Reservasi di transaksinya sendiri: penolakan budget selalu tercatat di audit.
        entry = self._guard.reserve(
            SpendRequest(
                idempotency_key=f"llm:{request.idempotency_key}#a{attempt}",
                category=Category.OPENAI,
                source=source,
                purpose=purpose,
                mode=self.mode,
                authorization_id=auth.id,
                usd_micros=estimated_usd,
                price_ref=self._pricing.ref(f"openai.{request.tier}"),
                episode_id=scope.episode_id,
                meta={
                    "task": request.task,
                    "estimated_input_tokens": estimated_input,
                    "max_output_tokens": request.max_output_tokens,
                },
            )
        )
        now = to_iso(self._clock.now())
        try:
            with self._db.transaction():
                if existing is None:
                    call_id = new_id(self._clock)
                    self._repo.insert(
                        {
                            "id": call_id,
                            "idempotency_key": request.idempotency_key,
                            "episode_id": scope.episode_id,
                            "job_id": scope.lease.job.id,
                            "lease_token": scope.lease.token,
                            "provider": self._provider.name,
                            "task": request.task,
                            "purpose": purpose,
                            "mode": self.mode.value,
                            "request_fingerprint": request.fingerprint,
                            "request": canonical_json(
                                {
                                    "task": request.task,
                                    "tier": request.tier,
                                    "system": request.system,
                                    "user": request.user,
                                    "max_output_tokens": request.max_output_tokens,
                                    "context_key": request.context_key,
                                    "variant": request.variant,
                                }
                            ),
                            "status": CallStatus.IN_FLIGHT.value,
                            "attempt": 1,
                            "ledger_entry_id": entry.id,
                            "authorization_id": auth.id,
                            "estimated_input_tokens": estimated_input,
                            "max_output_tokens": request.max_output_tokens,
                            "estimated_cost_idr": entry.reserved_idr,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                else:
                    call_id = existing.id
                    if (
                        self._repo.restart_failed(
                            call_id,
                            attempt=attempt,
                            ledger_entry_id=entry.id,
                            lease_token=scope.lease.token,
                            at=now,
                        )
                        != 1
                    ):
                        raise ConflictError(f"panggilan {call_id} berubah saat dicoba ulang")
                self._audit.record(
                    actor=_ACTOR,
                    action="provider_call.started",
                    entity_type="provider_call",
                    entity_id=call_id,
                    episode_id=scope.episode_id,
                    data={
                        "task": request.task,
                        "attempt": attempt,
                        "ledger_entry_id": entry.id,
                        "estimated_cost_idr": entry.reserved_idr,
                    },
                )
        except (sqlite3.IntegrityError, ConflictError):
            self._guard.release(entry.id)  # tidak jadi dipanggil → reservasi dilepas
            raise
        return self._repo.get(call_id)

    def _settle_unknown(self, call: ProviderCall, error: str) -> None:
        with self._db.transaction():
            if (
                self._repo.settle(
                    call.id,
                    attempt=call.attempt,
                    status=CallStatus.UNKNOWN,
                    at=to_iso(self._clock.now()),
                    error=error,
                )
                == 1
            ):
                self._guard.commit_at_reserved(call.ledger_entry_id)
                self._audit.record(
                    actor=_ACTOR,
                    action="provider_call.unknown",
                    entity_type="provider_call",
                    entity_id=call.id,
                    episode_id=call.episode_id,
                    data={"task": call.task, "error": error},
                )

    def _settle_failed(self, call: ProviderCall, error: str) -> None:
        with self._db.transaction():
            if (
                self._repo.settle(
                    call.id,
                    attempt=call.attempt,
                    status=CallStatus.FAILED,
                    at=to_iso(self._clock.now()),
                    error=error,
                )
                == 1
            ):
                self._guard.release(call.ledger_entry_id)
                self._audit.record(
                    actor=_ACTOR,
                    action="provider_call.failed",
                    entity_type="provider_call",
                    entity_id=call.id,
                    episode_id=call.episode_id,
                    data={"task": call.task, "error": error},
                )


def _response_of(call: ProviderCall) -> LLMResponse:
    data = call.response or {}
    return LLMResponse(
        text=str(data["text"]),
        input_tokens=int(data["input_tokens"]),
        output_tokens=int(data["output_tokens"]),
        model=str(data["model"]),
    )
