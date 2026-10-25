"""Penilaian kualitas sumber + kelompok independensi."""

from __future__ import annotations

from collections.abc import Iterable

from studio.modules.research.config import ResearchConfig
from studio.modules.research.injection import InjectionScan, scan
from studio.modules.research.models import SOURCE_TIER, SourceRecord, SourceType
from studio.providers.sources.ports import SourceDocument
from studio.shared.hashing import sha256_hex

_BASE_SCORE = {1: 95, 2: 85, 3: 75, 4: 55, 5: 25}


def _source_type(raw: str) -> SourceType:
    try:
        return SourceType(raw)
    except ValueError:
        return SourceType.OTHER


def assess(
    document: SourceDocument, config: ResearchConfig, *, retrieved_at: str
) -> tuple[SourceRecord, InjectionScan]:
    source_type = _source_type(document.source_type)
    tier = SOURCE_TIER[source_type]
    notes: list[str] = []
    score = _BASE_SCORE[tier]
    if document.published_date is None:
        score -= 15
        notes.append("tanggal publikasi tidak diketahui")
    if not document.authors:
        score -= 10
        notes.append("penulis/lembaga penanggung jawab tidak disebut")
    injection = scan(document.text, config)
    if injection.suspected:
        score = 0
        notes.append("terindikasi berisi instruksi tersembunyi (prompt injection); dikarantina")
    record = SourceRecord(
        id=document.id,
        title=document.title,
        publisher=document.publisher,
        url=document.url,
        source_type=source_type,
        tier=tier,
        quality_score=max(score, 0),
        published_date=document.published_date.isoformat() if document.published_date else None,
        authors=list(document.authors),
        origin=document.origin,
        derived_from=list(document.derived_from),
        independence_group=document.origin,  # disempurnakan oleh assign_groups()
        retrieved_via=document.retrieved_via,
        retrieved_at=retrieved_at,
        is_fixture=document.is_fixture,
        content_hash=sha256_hex(document.text),
        injection_suspected=injection.suspected,
        injection_markers=injection.markers,
        quarantined=injection.suspected,
        notes=notes,
    )
    return record, injection


def assign_groups(records: Iterable[SourceRecord]) -> list[SourceRecord]:
    """Gabungkan sumber yang tidak independen: penerbit/asal sama atau saling turunan.

    Jumlah sumber ≠ jumlah sumber independen: artikel yang merangkum artikel lain masuk ke
    kelompok yang sama dengan sumber aslinya.
    """
    records = list(records)
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    for record in records:
        union(f"src:{record.id}", f"origin:{record.origin}")
        for upstream in record.derived_from:
            union(f"src:{record.id}", f"src:{upstream}")
    return [
        record.model_copy(update={"independence_group": find(f"src:{record.id}")})
        for record in records
    ]
