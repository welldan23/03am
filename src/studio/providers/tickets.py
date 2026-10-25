"""Tiket belanja: bukti bahwa sebuah panggilan provider sudah direservasi di BudgetGuard.

Hanya `MeteredCaller` yang memegang `TicketAuthority` untuk menerbitkan tiket. Setiap adapter
provider wajib memverifikasi tiket sebelum bekerja, jadi tidak ada jalur yang bisa memanggil
provider (berbayar maupun mock) tanpa melewati reservasi anggaran.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from studio.providers.errors import InvalidTicketError


@dataclass(frozen=True)
class SpendTicket:
    request_fingerprint: str
    ledger_entry_id: str
    authorization_id: str
    signature: str


class TicketAuthority:
    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret or secrets.token_bytes(32)

    def _sign(self, fingerprint: str, ledger_entry_id: str, authorization_id: str) -> str:
        message = f"{fingerprint}|{ledger_entry_id}|{authorization_id}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def issue(self, fingerprint: str, ledger_entry_id: str, authorization_id: str) -> SpendTicket:
        return SpendTicket(
            fingerprint,
            ledger_entry_id,
            authorization_id,
            self._sign(fingerprint, ledger_entry_id, authorization_id),
        )

    def verify(self, ticket: SpendTicket | None, fingerprint: str) -> None:
        if ticket is None:
            raise InvalidTicketError("panggilan provider tanpa tiket belanja ditolak")
        expected = self._sign(fingerprint, ticket.ledger_entry_id, ticket.authorization_id)
        if ticket.request_fingerprint != fingerprint or not hmac.compare_digest(
            expected, ticket.signature
        ):
            raise InvalidTicketError("tiket belanja tidak cocok dengan request ini")
