"""Intent router deterministik (Fase 3): teks bebas → maksud + slot, tanpa LLM.

Router ini sengaja hanya MENEBAK MAKSUD, tidak pernah memutuskan. Keputusan sensitif
(approve/reject) tidak bisa lewat teks sama sekali; episode/format/kategori yang ambigu
dikembalikan sebagai slot kosong supaya bot bertanya balik.

`IntentParser` adalah port: di Fase 5 Hermes bisa menggantikan atau melengkapi
`RuleBasedIntentParser` tanpa mengubah `ConversationEngine` maupun Studio Controller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from studio.modules.episodes import Category, DocumentaryFormat
from studio.modules.scripting import ScriptingConfig, SegmentRole


class IntentName(StrEnum):
    HELP = "help"
    MENU = "menu"
    CREATE = "create"  # buat dokumenter / cari topik
    SET_FORMAT = "set_format"
    SET_CATEGORY = "set_category"
    SHOW_RESEARCH = "show_research"
    SHOW_SCRIPT = "show_script"
    SHOW_SEGMENT = "show_segment"
    REVISE_SCRIPT = "revise_script"
    CLAIM_SOURCES = "claim_sources"
    EPISODE_COST = "episode_cost"
    BUDGET = "budget"
    LIST_PENDING = "list_pending"
    LIST_EPISODES = "list_episodes"
    STATUS = "status"
    DECISION_BY_TEXT = "decision_by_text"  # "setujui saja" → ditolak, harus lewat tombol
    CANCEL_STEP = "cancel_step"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Intent:
    name: IntentName
    format: DocumentaryFormat | None = None
    duration_s: int | None = None
    category: Category | None = None
    topic: str | None = None
    claim_id: str | None = None
    episode_ref: str | None = None
    segment: SegmentRole | None = None
    notes: str | None = None
    ambiguities: tuple[str, ...] = field(default_factory=tuple)


class IntentParser(Protocol):
    def parse(self, text: str) -> Intent: ...


_CATEGORY_WORDS: dict[Category, tuple[str, ...]] = {
    Category.SEJARAH: ("sejarah", "history", "historis", "kerajaan", "perang dunia"),
    Category.GEOPOLITIK: ("geopolitik", "politik", "perbatasan", "konflik antarnegara"),
    Category.SAINS: ("sains", "science", "ilmiah", "ilmu pengetahuan", "teknologi", "vulkan"),
    Category.GEOGRAFI: ("geografi", "geografis", "peta", "pulau", "benua"),
    Category.MISTERI: ("misteri", "mystery", "misterius", "teka-teki", "belum terpecahkan"),
}

_FORMAT_WORDS: dict[DocumentaryFormat, tuple[str, ...]] = {
    DocumentaryFormat.QUICK_FILES: ("quick files", "quick file", "quick", "singkat", "pendek"),
    DocumentaryFormat.ARCHIVES: ("the archives", "archives", "archive", "arsip"),
    DocumentaryFormat.DEEP_FILES: ("deep files", "deep file", "deep", "panjang", "mendalam"),
}

_SEGMENT_WORDS: dict[SegmentRole, tuple[str, ...]] = {
    SegmentRole.HOOK: ("pembuka", "pembukaan", "hook", "awal", "intro"),
    SegmentRole.CONTEXT: ("konteks", "context", "latar"),
    SegmentRole.CONFLICT: ("konflik", "conflict", "pertanyaan"),
    SegmentRole.EXPLANATION: ("penjelasan", "explanation", "inti", "isi"),
    SegmentRole.CLOSING: ("penutup", "penutupan", "closing", "akhir", "ending"),
}

_CLAIM_ID = re.compile(r"\b(C-[a-z0-9][a-z0-9-]{1,63})\b", re.IGNORECASE)
_EPISODE_ID = re.compile(r"(?:\b([0-9A-HJKMNP-TV-Z]{26})|#([0-9A-Za-z]{4,26}))\b")
_DURATION = re.compile(r"\b(\d{2,3})\s*(?:detik|dtk|det|s|sec|second|seconds)\b")
_TOPIC_AFTER = re.compile(r"\b(?:tentang|soal|mengenai)\s+(.+)$")
_CREATE_START = re.compile(
    r"^(?:tolong\s+|coba\s+|ayo\s+)?(?:buat|bikin|buatkan|bikinin)\s+(?:\w+\s+){0,2}?"
    r"(?:dokumenter|video|film|episode)"
)
_TOPIC_STOP = re.compile(
    r"[,;]|\s(?:dengan\s|pakai\s|format|durasi|kategori|\d{2,3}\s*(?:detik|dtk))", re.IGNORECASE
)


# Akhiran klitik bahasa Indonesia: "risetnya", "naskahmu", "bukankah".
_SUFFIX = r"(?:nya|lah|kah|mu|ku)?"


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(w)}{_SUFFIX}(?![\w-])", text) for w in words)


def _topic_of(raw: str, lowered: str) -> str | None:
    match = _TOPIC_AFTER.search(lowered)
    if not match:
        return None
    topic = raw[match.start(1) : match.end(1)]
    # Berhenti di koma / kata kunci slot lain: "Krakatau, format 90 detik".
    return _TOPIC_STOP.split(topic, maxsplit=1)[0].strip(" .?!") or None


class RuleBasedIntentParser:
    def __init__(self, scripting: ScriptingConfig) -> None:
        self._formats = scripting.formats

    def _format_for(self, seconds: int) -> DocumentaryFormat | None:
        matches = [name for name, spec in self._formats.items() if spec.contains(seconds)]
        return DocumentaryFormat(matches[0]) if len(matches) == 1 else None

    def parse(self, text: str) -> Intent:
        raw = " ".join(text.split())
        t = raw.lower()
        if not t:
            return Intent(IntentName.UNKNOWN)

        claim = _CLAIM_ID.search(raw)
        episode = _EPISODE_ID.search(raw)
        episode_ref = (episode.group(1) or episode.group(2)) if episode else None
        categories = [c for c in Category if _has(t, *_CATEGORY_WORDS[c])]
        formats = [f for f in DocumentaryFormat if _has(t, *_FORMAT_WORDS[f])]
        segments = [s for s in SegmentRole if _has(t, *_SEGMENT_WORDS[s])]
        duration_match = _DURATION.search(t)
        duration = int(duration_match.group(1)) if duration_match else None

        ambiguities: list[str] = []
        category = categories[0] if len(categories) == 1 else None
        if len(categories) > 1:
            ambiguities.append("category")
        fmt = formats[0] if len(formats) == 1 else None
        if len(formats) > 1:
            ambiguities.append("format")
        if duration is not None:
            by_duration = self._format_for(duration)
            if by_duration is None or (fmt is not None and fmt is not by_duration):
                ambiguities.append("duration")
                fmt, duration = (fmt if by_duration is None else None), None
            else:
                fmt = by_duration

        def with_slots(name: IntentName, topic: str | None = None) -> Intent:
            return Intent(
                name,
                format=fmt,
                duration_s=duration,
                category=category,
                topic=topic,
                episode_ref=episode_ref,
                ambiguities=tuple(ambiguities),
            )

        if t in {"batal", "cancel", "stop", "tidak jadi", "gak jadi", "nggak jadi"}:
            return Intent(IntentName.CANCEL_STEP)
        # "Buat dokumenter tentang …" di awal kalimat selalu permintaan membuat, apa pun
        # topiknya (topik boleh mengandung kata seperti "naskah" atau "biaya").
        if _CREATE_START.match(t):
            return with_slots(IntentName.CREATE, _topic_of(raw, t))

        if _has(t, "bantuan", "help", "tolong", "bisa apa", "cara pakai"):
            return Intent(IntentName.HELP)
        if t in {"menu", "menu utama", "home"}:
            return Intent(IntentName.MENU)

        # Keputusan approval TIDAK pernah diambil dari teks bebas.
        if re.fullmatch(
            r"(ya|oke|ok|iya|yes|lanjut)?\s*(setuju|setujui|approve|acc|tolak|reject)\b.*", t
        ) and not _has(t, "belum", "tampilkan", "lihat", "daftar"):
            return Intent(IntentName.DECISION_BY_TEXT, episode_ref=episode_ref)

        if _has(t, "sumber") and (claim or _has(t, "klaim", "claim", "fakta ini")):
            return Intent(
                IntentName.CLAIM_SOURCES,
                claim_id=claim.group(1) if claim else None,
                episode_ref=episode_ref,
            )
        if _has(t, "biaya", "ongkos", "harga", "estimasi") and not _has(t, "budget", "anggaran"):
            return Intent(IntentName.EPISODE_COST, episode_ref=episode_ref)
        if _has(t, "budget", "anggaran", "dana", "sisa uang"):
            return Intent(IntentName.BUDGET)
        if (_has(t, "belum") and _has(t, "approve", "approval", "setujui", "disetujui")) or _has(
            t, "menunggu approval", "perlu approval", "daftar approval", "approval"
        ):
            return Intent(IntentName.LIST_PENDING)

        script_word = _has(t, "naskah", "script", "skrip", "narasi")
        if (_has(t, "ringkas", "rangkum", "ringkasan") or (script_word and segments)) and segments:
            return Intent(IntentName.SHOW_SEGMENT, segment=segments[0], episode_ref=episode_ref)
        if script_word and _has(
            t, "kaku", "revisi", "ubah", "perbaiki", "terlalu", "lebih", "ganti", "kurang"
        ):
            return Intent(IntentName.REVISE_SCRIPT, notes=raw, episode_ref=episode_ref)
        if script_word:
            return Intent(IntentName.SHOW_SCRIPT, episode_ref=episode_ref)
        if _has(t, "riset", "research", "brief", "hasil riset", "fakta"):
            return Intent(IntentName.SHOW_RESEARCH, episode_ref=episode_ref)
        if _has(t, "status", "progres", "progress", "sedang dikerjakan", "produksi"):
            return Intent(IntentName.STATUS)
        if _has(t, "episode") and _has(t, "daftar", "semua", "aktif", "list", "tampilkan", "lihat"):
            return Intent(IntentName.LIST_EPISODES)

        wants_new = _has(t, "buat", "bikin", "buatkan", "bikinin") and _has(
            t, "dokumenter", "episode", "video", "film"
        )
        wants_topics = _has(t, "cari", "carikan", "ide", "usul", "saran") and _has(
            t, "topik", "ide", "tema"
        )
        if wants_new or wants_topics:
            return with_slots(IntentName.CREATE, _topic_of(raw, t))
        if (
            fmt is not None
            or duration is not None
            or "duration" in ambiguities
            or _has(t, "format")
        ):
            return with_slots(IntentName.SET_FORMAT)
        if category is not None or "category" in ambiguities:
            return with_slots(IntentName.SET_CATEGORY)
        return with_slots(IntentName.UNKNOWN)
