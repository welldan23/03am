"""Adapter LLM mock: deterministik, offline, tanpa API key.

Respons diambil dari fixture YAML (`fixtures/llm/<task>/<nama>.yaml`). Fixture adalah data
uji yang ditulis manusia, bukan keluaran model. Mock tetap memverifikasi tiket belanja
seperti adapter asli, dan bisa disetel untuk mensimulasikan gangguan (timeout, tidak
tersedia, JSON rusak) per task.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

import yaml

from studio.providers.errors import (
    ProviderRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from studio.providers.llm.ports import BillingMode, LLMRequest, LLMResponse
from studio.providers.tickets import SpendTicket, TicketAuthority

Fault = Literal["timeout", "unavailable", "rejected", "invalid_json"]

PACKAGE_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"

# Kalau fixture revisi tidak ada, revisi memakai fixture naskah awal untuk topik yang sama.
_FALLBACK_TASK = {"script_revision": "script_generation"}


class MockLLMProvider:
    name = "mock-llm"
    billing_mode: BillingMode = "simulated"

    def __init__(
        self,
        tickets: TicketAuthority,
        *,
        fixture_dirs: Iterable[Path] = (),
        overrides: Mapping[str, str] | None = None,
        faults: Mapping[str, Iterable[Fault]] | None = None,
        chars_per_token: int = 4,
        idempotent_replay: bool = False,
    ) -> None:
        self._tickets = tickets
        self._dirs = [*fixture_dirs, PACKAGE_FIXTURES]
        self._overrides = dict(overrides or {})
        self._faults: dict[str, deque[Fault]] = defaultdict(deque)
        for task, plan in (faults or {}).items():
            self._faults[task].extend(plan)
        self._chars_per_token = chars_per_token
        self.idempotent_replay = idempotent_replay
        self.calls: list[LLMRequest] = []

    def _find(self, task: str, names: list[str]) -> dict[str, Any] | None:
        for directory in self._dirs:
            for name in names:
                path = directory / task / f"{name}.yaml"
                if path.is_file():
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        raise ProviderRejectedError(f"fixture rusak: {path}")
                    return data
        return None

    def _fixture_response(self, request: LLMRequest) -> Any:
        names = [n for n in (self._overrides.get(request.task), request.context_key) if n]
        names.append("default")
        data = self._find(request.task, names)
        if data is None and request.task in _FALLBACK_TASK:
            data = self._find(_FALLBACK_TASK[request.task], names)
        if data is None:
            raise ProviderRejectedError(
                f"fixture mock tidak tersedia untuk task '{request.task}' "
                f"(konteks '{request.context_key}')"
            )
        if "responses" in data:
            responses = data["responses"]
            key = request.variant if request.variant in responses else "default"
            if key not in responses:
                raise ProviderRejectedError(
                    f"fixture '{request.task}/{request.context_key}' tidak punya varian "
                    f"'{request.variant}'"
                )
            return responses[key]
        return data["response"]

    def complete(self, request: LLMRequest, ticket: SpendTicket) -> LLMResponse:
        self._tickets.verify(ticket, request.fingerprint)
        self.calls.append(request)
        fault = self._faults[request.task].popleft() if self._faults[request.task] else None
        if fault == "unavailable":
            raise ProviderUnavailableError("mock: provider tidak tersedia (request tidak terkirim)")
        if fault == "rejected":
            raise ProviderRejectedError("mock: request ditolak provider")
        if fault == "timeout":
            raise ProviderTimeoutError("mock: timeout setelah request terkirim")
        text = (
            '{"rusak": '
            if fault == "invalid_json"
            else json.dumps(self._fixture_response(request), ensure_ascii=False)
        )
        prompt_chars = len(request.system) + len(request.user)
        return LLMResponse(
            text=text,
            input_tokens=math.ceil(prompt_chars / self._chars_per_token),
            output_tokens=min(
                request.max_output_tokens, math.ceil(len(text) / self._chars_per_token)
            ),
            model=f"mock-{request.tier}",
        )
