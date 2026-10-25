"""Utilitas teks bersama: normalisasi, kalimat, angka."""

from __future__ import annotations

import re

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_THOUSANDS = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    return " ".join(text.translate(_QUOTES).split())


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(normalize(text)) if s]


def numbers(text: str) -> set[str]:
    """Angka dalam teks, dinormalisasi: '36.000' → '36000', '4.800' → '4800'."""
    found = set()
    for raw in _NUMBER.findall(text):
        found.add(raw.replace(".", "") if _THOUSANDS.match(raw) else raw.replace(",", "."))
    return found


def words(text: str) -> list[str]:
    return _WORD.findall(normalize(text).lower())


def word_count(text: str) -> int:
    return len(normalize(text).split())


def truncate_words(text: str, limit: int) -> str:
    parts = normalize(text).split()
    return text if len(parts) <= limit else " ".join(parts[:limit]) + " …"
