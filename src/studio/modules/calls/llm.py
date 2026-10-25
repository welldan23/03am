"""LLMClient: prompt + routing tier + validasi skema, semua lewat MeteredCaller.

Business logic hanya memanggil `LLMClient.run(...)`. Mengganti mock dengan provider asli
cukup dengan memasang adapter `LLMProvider` lain di bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from studio.modules.calls.caller import MeteredCaller
from studio.modules.calls.models import CallScope, LLMOutputError
from studio.providers.llm.ports import LLMRequest
from studio.shared.errors import ConfigError
from studio.shared.hashing import canonical_json

DATA_OPEN = "<<<DATA"
DATA_CLOSE = "DATA>>>"


class LLMTaskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tier: str
    max_output_tokens: int = Field(gt=0)
    timeout_s: float = Field(gt=0)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chars_per_token: int = Field(gt=0)
    json_retries: int = Field(ge=0, le=3)
    tasks: dict[str, LLMTaskConfig]

    def task(self, name: str) -> LLMTaskConfig:
        try:
            return self.tasks[name]
        except KeyError as exc:
            raise ConfigError(f"task LLM '{name}' tidak dikonfigurasi di llm.yaml") from exc


def load_llm_config(path: Path) -> LLMConfig:
    try:
        return LLMConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValidationError) as exc:
        raise ConfigError(f"konfigurasi LLM tidak valid ({path}): {exc}") from exc


class PromptLibrary:
    def __init__(self, package: str = "studio.prompts") -> None:
        root = resources.files(package)
        self._system = root.joinpath("_system.md").read_text(encoding="utf-8").strip()
        self._tasks = {
            entry.name.removesuffix(".md"): entry.read_text(encoding="utf-8").strip()
            for entry in root.iterdir()
            if entry.name.endswith(".md") and not entry.name.startswith("_")
        }

    def system(self) -> str:
        return self._system

    def task(self, name: str) -> str:
        try:
            return self._tasks[name]
        except KeyError as exc:
            raise ConfigError(f"template prompt '{name}.md' tidak ada") from exc


def wrap_data(data: dict[str, Any]) -> str:
    """Bungkus data tak tepercaya dengan penanda jelas. Penanda di dalam data dinetralkan."""
    body = canonical_json(data).replace(DATA_OPEN, "<DATA").replace(DATA_CLOSE, "DATA>")
    return f"{DATA_OPEN}\n{body}\n{DATA_CLOSE}"


@dataclass(frozen=True)
class TaskResult[M: BaseModel]:
    value: M
    calls: list[dict[str, Any]]


class LLMClient:
    def __init__(self, caller: MeteredCaller, config: LLMConfig, prompts: PromptLibrary) -> None:
        self._caller = caller
        self._config = config
        self._prompts = prompts

    def run[M: BaseModel](
        self,
        scope: CallScope,
        task: str,
        *,
        data: dict[str, Any],
        schema: type[M],
        context_key: str,
        variant: str = "",
        sub_key: str = "main",
    ) -> TaskResult[M]:
        settings = self._config.task(task)
        user = f"{self._prompts.task(task)}\n\n{wrap_data(data)}"
        calls: list[dict[str, Any]] = []
        last_error = ""
        for attempt in range(self._config.json_retries + 1):
            retry_suffix = "" if attempt == 0 else f":json-retry{attempt}"
            prompt = (
                user
                if attempt == 0
                else (
                    f"{user}\n\nRespons sebelumnya tidak valid terhadap skema ({last_error}). "
                    "Kirim ulang hanya JSON yang valid."
                )
            )
            request = LLMRequest(
                task=task,
                tier=settings.tier,
                system=self._prompts.system(),
                user=prompt,
                max_output_tokens=settings.max_output_tokens,
                timeout_s=settings.timeout_s,
                idempotency_key=f"{scope.key_prefix}:{task}:{sub_key}{retry_suffix}",
                context_key=context_key,
                variant=variant,
            )
            # Setiap retry = panggilan baru yang dimeter terpisah (ADR-0009).
            response, call, reused = self._caller.call(
                scope, request, purpose=task if attempt == 0 else f"{task}.retry"
            )
            calls.append(call.ref(reused=reused))
            try:
                return TaskResult(schema.model_validate_json(response.text), calls)
            except ValidationError as exc:
                last_error = f"{exc.error_count()} kesalahan validasi"
        raise LLMOutputError(
            f"keluaran LLM untuk '{task}' tidak sesuai skema setelah "
            f"{self._config.json_retries + 1} percobaan ({last_error})"
        )
