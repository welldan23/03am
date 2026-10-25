"""Port sumber riset. Dokumen hanya boleh berasal dari provider ini — tidak pernah dari LLM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class SourceDocument:
    id: str
    title: str
    publisher: str
    url: str
    source_type: str
    published_date: date | None
    authors: tuple[str, ...]
    origin: str
    derived_from: tuple[str, ...]
    language: str
    text: str
    retrieved_via: str
    is_fixture: bool


class SourceProvider(Protocol):
    name: str

    def search(self, topic_key: str, queries: list[str], limit: int) -> list[SourceDocument]: ...
