"""Hierarki error domain. Semua error yang disengaja turunan `StudioError`."""


class StudioError(Exception):
    """Error dasar 03:AM."""


class NonRetryableError(StudioError):
    """Error yang tidak akan sembuh dengan retry (misalnya budget habis)."""


class ConfigError(StudioError):
    """Konfigurasi tidak valid atau tidak aman."""


class NotFoundError(StudioError):
    """Entitas tidak ditemukan."""


class NotAuthorizedError(NonRetryableError):
    """Actor tidak berhak melakukan aksi ini."""


class ConflictError(StudioError):
    """Data sudah berubah sejak dibaca (optimistic locking) atau duplikat yang bertentangan."""
