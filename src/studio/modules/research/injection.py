"""Deteksi & netralisasi prompt injection di dokumen sumber.

Lapisan pertahanan:
1. kalimat yang cocok dengan pola injeksi dihapus sebelum teks dikirim ke LLM;
2. sumber yang terindikasi dikarantina: buktinya tidak dihitung untuk verifikasi;
3. teks sumber selalu dibungkus sebagai DATA (lihat `calls.wrap_data`) dan LLM tidak punya
   alat atau wewenang apa pun — keluaran hanya JSON yang divalidasi skema.
"""

from __future__ import annotations

from dataclasses import dataclass

from studio.modules.research.config import ResearchConfig
from studio.modules.research.text import sentences

REDACTION = "[DIHAPUS: diduga instruksi tersembunyi di dalam sumber]"


@dataclass(frozen=True)
class InjectionScan:
    suspected: bool
    markers: list[str]
    sanitized_text: str


def scan(text: str, config: ResearchConfig) -> InjectionScan:
    markers: list[str] = []
    kept: list[str] = []
    for sentence in sentences(text):
        hits = [rx.pattern for rx in config.injection_regexes if rx.search(sentence)]
        if hits:
            markers.extend(hits)
            if not kept or kept[-1] != REDACTION:
                kept.append(REDACTION)
        else:
            kept.append(sentence)
    return InjectionScan(bool(markers), sorted(set(markers)), " ".join(kept))
