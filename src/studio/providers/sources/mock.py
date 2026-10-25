"""Pustaka sumber fixture (offline).

Semua dokumen di sini adalah FIXTURE uji: penerbitnya fiktif dan ditandai "(FIXTURE)",
URL-nya memakai domain `.invalid` (RFC 2606) sehingga jelas tidak bisa dianggap rujukan
nyata. Isi faktualnya ditulis konservatif untuk keperluan uji alur riset.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from studio.providers.sources.ports import SourceDocument

PACKAGE_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
FIXTURE_URL_PREFIX = "https://fixture.03am.invalid/"


def _document(raw: dict[str, Any], origin_file: str) -> SourceDocument:
    url = str(raw["url"])
    if not url.startswith(FIXTURE_URL_PREFIX):
        raise ValueError(f"URL fixture harus diawali {FIXTURE_URL_PREFIX}: {url}")
    published = raw.get("published_date")
    return SourceDocument(
        id=str(raw["id"]),
        title=str(raw["title"]),
        publisher=str(raw["publisher"]),
        url=url,
        source_type=str(raw["source_type"]),
        published_date=published
        if isinstance(published, date) or published is None
        else date.fromisoformat(str(published)),
        authors=tuple(raw.get("authors", [])),
        origin=str(raw["origin"]),
        derived_from=tuple(raw.get("derived_from", [])),
        language=str(raw.get("language", "id")),
        text=" ".join(str(raw["text"]).split()),
        retrieved_via=f"fixture:{origin_file}",
        is_fixture=True,
    )


class FixtureSourceLibrary:
    name = "fixture-sources"

    def __init__(self, fixture_dirs: list[Path] | None = None) -> None:
        self._library: dict[str, list[SourceDocument]] = {}
        for directory in [*(fixture_dirs or []), PACKAGE_FIXTURES]:
            for path in sorted(directory.glob("*.yaml")):
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                topic = str(data["topic_key"])
                if topic in self._library:
                    continue  # direktori pertama menang (override test)
                self._library[topic] = [_document(d, path.name) for d in data["documents"]]

    def search(self, topic_key: str, queries: list[str], limit: int) -> list[SourceDocument]:
        documents = self._library.get(topic_key, [])
        terms = {t.lower() for q in queries for t in q.split() if len(t) > 3}
        scored = []
        for index, doc in enumerate(documents):
            haystack = f"{doc.title} {doc.text}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((-score, index, doc))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [doc for _, _, doc in scored[:limit]]
