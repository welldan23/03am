"""Error provider dibedakan menurut APA YANG DIKETAHUI tentang tagihan.

- `ProviderUnavailableError`: request tidak pernah sampai ke provider → tidak tertagih, aman
  diulang.
- `ProviderRejectedError`: provider menolak secara pasti (validasi, kuota) → tidak tertagih.
- `ProviderTimeoutError`: request mungkin sudah diproses → hasil & tagihan TIDAK DIKETAHUI.
  Tidak boleh diulang secara buta.
"""

from studio.shared.errors import StudioError


class ProviderError(StudioError):
    retryable: bool = False


class ProviderUnavailableError(ProviderError):
    retryable = True


class ProviderRejectedError(ProviderError):
    retryable = False


class ProviderTimeoutError(ProviderError):
    retryable = False


class InvalidTicketError(ProviderError):
    """Panggilan provider tanpa tiket belanja yang sah dari MeteredCaller."""
