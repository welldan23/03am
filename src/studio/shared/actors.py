"""Siapa yang melakukan sebuah aksi. Keputusan manusia hanya sah dari `owner` di allowlist."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from studio.shared.errors import NotAuthorizedError


class ActorKind(StrEnum):
    OWNER = "owner"
    DIRECTOR = "director"
    SYSTEM = "system"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: str

    @classmethod
    def owner(cls, owner_id: str) -> Actor:
        return cls(ActorKind.OWNER, owner_id)

    @classmethod
    def director(cls, name: str = "hermes") -> Actor:
        return cls(ActorKind.DIRECTOR, name)

    @classmethod
    def system(cls, name: str = "workflow") -> Actor:
        return cls(ActorKind.SYSTEM, name)

    @property
    def label(self) -> str:
        return f"{self.kind.value}:{self.id}"

    def __str__(self) -> str:
        return self.label


class OwnerPolicy:
    """Allowlist owner. Kosong = tidak ada yang boleh mengambil keputusan (default aman)."""

    def __init__(self, owner_ids: frozenset[str]) -> None:
        self._owner_ids = owner_ids

    def is_owner(self, actor: Actor) -> bool:
        return actor.kind is ActorKind.OWNER and actor.id in self._owner_ids

    def require_owner(self, actor: Actor, action: str) -> None:
        if not self.is_owner(actor):
            raise NotAuthorizedError(
                f"{actor.label} tidak berhak melakukan '{action}'; hanya owner di allowlist"
            )
