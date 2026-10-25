"""Port LLM. Business logic hanya mengenal tipe di file ini."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from studio.providers.tickets import SpendTicket
from studio.shared.hashing import content_hash

BillingMode = Literal["simulated", "real"]


@dataclass(frozen=True)
class LLMRequest:
    task: str
    tier: str
    system: str
    user: str
    max_output_tokens: int
    timeout_s: float
    idempotency_key: str
    # Petunjuk konteks (misalnya kunci topik) — dipakai mock untuk memilih fixture dan oleh
    # provider asli untuk logging; tidak memengaruhi isi prompt.
    context_key: str = ""
    variant: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return content_hash(
            {
                "task": self.task,
                "tier": self.tier,
                "system": self.system,
                "user": self.user,
                "max_output_tokens": self.max_output_tokens,
                "idempotency_key": self.idempotency_key,
                "context_key": self.context_key,
                "variant": self.variant,
            }
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    name: str
    billing_mode: BillingMode
    # True kalau provider menjamin request dengan idempotency key yang sama tidak diproses
    # (dan ditagih) dua kali. Hanya provider seperti ini yang boleh di-replay setelah crash.
    idempotent_replay: bool

    def complete(self, request: LLMRequest, ticket: SpendTicket) -> LLMResponse: ...
