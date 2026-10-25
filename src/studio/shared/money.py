"""Uang: Rupiah = int, USD = int mikro-dolar, kurs = Decimal. Tidak ada float.

Konversi USD → IDR selalu dibulatkan ke atas supaya estimasi tidak pernah terlalu kecil.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal, InvalidOperation

USD_MICROS_PER_USD = 1_000_000


def parse_usd(value: str | int | Decimal) -> int:
    """Ubah nilai USD ('9.50') menjadi mikro-dolar (9_500_000) tanpa kehilangan presisi."""
    if isinstance(value, float):
        raise TypeError("nilai USD tidak boleh float; tulis sebagai string, contoh '9.50'")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"nilai USD tidak valid: {value!r}") from exc
    micros = amount * USD_MICROS_PER_USD
    if micros != micros.to_integral_value():
        raise ValueError(f"nilai USD lebih presisi dari 6 desimal: {value!r}")
    if micros < 0:
        raise ValueError("nilai USD tidak boleh negatif")
    return int(micros)


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("pembagi harus positif")
    return -(-numerator // denominator)


def apply_margin_ceil(amount_idr: int, margin_pct: int) -> int:
    """amount × (100 + margin) / 100, dibulatkan ke atas."""
    if margin_pct < 0:
        raise ValueError("margin tidak boleh negatif")
    return ceil_div(amount_idr * (100 + margin_pct), 100)


@dataclass(frozen=True)
class FxRate:
    """Kurs USD → IDR beserta asal-usulnya. Disimpan di setiap estimasi & transaksi."""

    usd_idr: Decimal
    as_of: date
    source: str

    def __post_init__(self) -> None:
        if self.usd_idr <= 0:
            raise ValueError("kurs harus positif")

    def to_idr(self, usd_micros: int) -> int:
        if usd_micros < 0:
            raise ValueError("jumlah USD tidak boleh negatif")
        idr = (Decimal(usd_micros) * self.usd_idr) / USD_MICROS_PER_USD
        return int(idr.to_integral_value(rounding=ROUND_CEILING))

    @property
    def as_text(self) -> str:
        return str(self.usd_idr)


def format_idr(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp{abs(amount):,}".replace(",", ".")


def format_usd(usd_micros: int) -> str:
    dollars, micros = divmod(usd_micros, USD_MICROS_PER_USD)
    text = f"{dollars}.{micros:06d}".rstrip("0")
    if text.endswith("."):
        text += "00"
    elif len(text.split(".")[1]) == 1:
        text += "0"
    return f"${text}"
