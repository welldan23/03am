"""Konfigurasi runtime dari environment (prefix STUDIO_) dan file .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STUDIO_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    # Dipisah koma, contoh: "cli:owner,telegram:123456"
    owner_ids: str = ""
    log_level: str = "INFO"
    paid_providers_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("PAID_PROVIDERS_ENABLED", "STUDIO_PAID_PROVIDERS_ENABLED"),
    )
    worker_lease_seconds: int = Field(default=300, ge=5)
    job_max_attempts: int = Field(default=3, ge=1)
    approval_ttl_hours: int = Field(default=72, ge=1)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def budget_config_path(self) -> Path:
        return self.config_dir / "budget.yaml"

    @property
    def pricing_config_path(self) -> Path:
        return self.config_dir / "pricing.yaml"

    @property
    def llm_config_path(self) -> Path:
        return self.config_dir / "llm.yaml"

    @property
    def editorial_config_path(self) -> Path:
        return self.config_dir / "editorial.yaml"

    @property
    def owner_id_set(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.owner_ids.split(",") if part.strip())
