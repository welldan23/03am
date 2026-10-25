"""Log terstruktur (JSON) dengan redaksi secret.

Dua lapis redaksi:
1. nilai pada kunci yang namanya mengandung kata sensitif selalu diganti `***`;
2. nilai env var sensitif yang muncul di string mana pun ikut disensor.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "***"
SENSITIVE_MARKERS = ("token", "key", "secret", "password", "authorization")


def is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


def secret_values_from_env(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    env = os.environ if environ is None else environ
    # Nilai pendek (misal "1") terlalu umum untuk disensor sebagai substring.
    return frozenset(v for k, v in env.items() if is_sensitive_name(k) and len(v) >= 6)


def _scrub(value: Any, secrets: frozenset[str]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if is_sensitive_name(str(k)) else _scrub(v, secrets))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_scrub(item, secrets) for item in value]
    return value


class RedactSecrets:
    def __init__(self, secrets: frozenset[str] | None = None) -> None:
        self._secrets = secret_values_from_env() if secrets is None else secrets

    def __call__(
        self, logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        for key in list(event_dict):
            if is_sensitive_name(key):
                event_dict[key] = REDACTED
            else:
                event_dict[key] = _scrub(event_dict[key], self._secrets)
        return event_dict


def configure_logging(level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            RedactSecrets(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
