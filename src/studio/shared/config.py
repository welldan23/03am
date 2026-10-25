"""Konfigurasi runtime dari environment (prefix STUDIO_) dan file .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
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

    # --- Telegram (Fase 3) ---------------------------------------------------------
    # Token hanya dari environment / .env, tidak pernah dari file di repo. SecretStr supaya
    # tidak tercetak di repr, log, atau pesan error.
    telegram_bot_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("STUDIO_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
    )
    # Masa berlaku tombol aksi (kode sekali pakai). Tidak pernah melebihi masa approval.
    action_ttl_minutes: int = Field(default=360, ge=1, le=7 * 24 * 60)
    # Langkah percakapan (misal menunggu catatan revisi) kedaluwarsa setelah ini.
    conversation_step_ttl_minutes: int = Field(default=30, ge=1)
    # Dispatcher notifikasi: interval cek outbox saat sepi (detik). Dipercepat otomatis
    # setelah ada aksi di bot atau job selesai di worker yang sama.
    notify_idle_seconds: float = Field(default=10.0, gt=0, le=300)
    # Jalankan worker job di proses bot (thread terpisah, koneksi DB sendiri).
    telegram_run_worker: bool = True

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

    @property
    def telegram_owner_ids(self) -> tuple[str, ...]:
        """User ID Telegram (numerik) yang ada di allowlist, contoh `telegram:123456789`."""
        ids = []
        for owner in sorted(self.owner_id_set):
            channel, _, value = owner.partition(":")
            if channel == "telegram" and value.isdigit():
                ids.append(value)
        return tuple(ids)
