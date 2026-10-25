"""Editorial gate deterministik + timing narasi yang bisa dikonfigurasi."""

from typing import Any, cast

import pytest

from studio.bootstrap import load_editorial_config
from studio.modules.calls import LLMClient
from studio.modules.research import (
    AssertionType,
    ClaimCategory,
    ClaimRecord,
    Importance,
    Level,
    ResearchBrief,
    TopicCandidate,
)
from studio.modules.scripting import (
    EditorialGate,
    NarrationConfig,
    ScriptDraft,
    ScriptingConfig,
    build_script,
)
from tests.conftest import REPO_ROOT

_, CONFIG = load_editorial_config(REPO_ROOT / "config" / "editorial.yaml")
GATE = EditorialGate(cast(LLMClient, None), CONFIG)  # check() tidak memanggil LLM
SPEC = CONFIG.format_spec("quick_files")


def _claim(
    claim_id: str, statement: str, category: ClaimCategory, conflicts: list[str] | None = None
) -> ClaimRecord:
    return ClaimRecord(
        id=claim_id,
        key=claim_id[2:],
        statement=statement,
        assertion_type=AssertionType.FACT,
        importance=Importance.CRITICAL,
        evidence_ids=[],
        category=category,
        conflicts_with=conflicts or [],
    )


CLAIMS = {
    "verified": _claim(
        "C-v",
        "Letusan terjadi pada 27 Agustus 1883 di Selat Sunda.",
        ClaimCategory.VERIFIED_FACT,
        ["C-d"],
    ),
    "disputed": _claim("C-d", "Korban mencapai 120.000 orang.", ClaimCategory.DISPUTED, ["C-v"]),
    "unverified": _claim("C-u", "Suhu global turun pada 1884.", ClaimCategory.UNVERIFIED),
    "hypothesis": _claim("C-h", "Langit merah mengilhami lukisan itu.", ClaimCategory.HYPOTHESIS),
}
BRIEF = ResearchBrief(
    topic=TopicCandidate(
        key="uji-topik",
        title="Topik Uji",
        topic_category="fenomena_alam",
        angle="a",
        hook_question="?",
        why_interesting="w",
        sensitivity=Level.RENDAH,
        sensitivity_reason="r",
        verifiability=Level.TINGGI,
        suggested_format="quick_files",
    ),
    objective="uji",
    verified_facts=[CLAIMS["verified"]],
    interpretations=[],
    hypotheses=[CLAIMS["hypothesis"]],
    disputed=[CLAIMS["disputed"]],
    unverified=[CLAIMS["unverified"]],
    timeline=[],
    sources=[],
    contradictions=[],
    open_questions=[],
    sensitivity=Level.RENDAH,
    sensitivity_reason="r",
)
SOURCE_TEXTS = {
    "S1": "Letusan besar itu terjadi pada pagi hari dan suaranya terdengar sangat jauh "
    "hingga ke pulau di tengah samudra yang luas sekali"
}

FILLER = (
    "Ini adalah kalimat pengantar yang tenang untuk mengisi durasi narasi dengan wajar "
    "tanpa memuat klaim baru apa pun."
)


def _script(
    overrides: dict[str, list[dict[str, Any]]] | None = None,
    *,
    roles: list[str] | None = None,
    target: int = 40,
) -> Any:
    lines: dict[str, list[dict[str, Any]]] = {
        "hook": [{"text": "Pada 27 Agustus 1883, Selat Sunda berguncang.", "claim_refs": ["C-v"]}],
        "context": [
            {"text": "Letusan itu terjadi di Selat Sunda.", "claim_refs": ["C-v"]},
            {"text": FILLER, "claim_refs": ["C-v"]},
        ],
        "conflict": [{"text": "Berapa sebenarnya korbannya?", "claim_refs": []}],
        "explanation": [
            {
                "text": "Sebagian tulisan menyebut 120.000 korban, tetapi angka itu "
                "tidak didukung arsip.",
                "claim_refs": ["C-d"],
            },
            {"text": FILLER, "claim_refs": ["C-v"]},
        ],
        "closing": [
            {
                "text": "Sebagian peneliti menduga langit merah mengilhami lukisan itu.",
                "claim_refs": ["C-h"],
            },
            {"text": FILLER, "claim_refs": []},
        ],
    }
    lines.update(overrides or {})
    draft = ScriptDraft.model_validate(
        {
            "title": "Uji",
            "segments": [
                {"role": r, "visual_direction": "v", "lines": lines[r]}
                for r in (roles or ["hook", "context", "conflict", "explanation", "closing"])
            ],
        }
    )
    return build_script(
        draft,
        format_name="quick_files",
        spec=SPEC,
        target_duration_s=target,
        narration=CONFIG.narration,
        revision=0,
        notes=None,
    )


def _codes(script: Any) -> dict[str, str]:
    return {i.code: i.severity.value for i in GATE.check(script, BRIEF, SOURCE_TEXTS, SPEC)}


def test_good_script_has_no_blocking_issues() -> None:
    codes = _codes(_script())
    assert "blocking" not in codes.values(), codes


def test_timing_uses_configured_words_per_minute() -> None:
    slow = CONFIG.model_copy(
        update={"narration": NarrationConfig(words_per_minute=120, segment_pause_s=0.4)}
    )
    base = _script()
    draft = ScriptDraft.model_validate(
        {
            "title": "x",
            "segments": [
                {"role": s.role, "visual_direction": "v", "lines": s.lines} for s in base.segments
            ],
        }
    )
    slower = build_script(
        draft,
        format_name="quick_files",
        spec=SPEC,
        target_duration_s=40,
        narration=slow.narration,
        revision=0,
        notes=None,
    )
    assert slower.estimated_duration_s > base.estimated_duration_s
    assert base.segments[0].start_s == 0 and base.segments[1].start_s == base.segments[0].end_s
    words = sum(s.word_count for s in base.segments)
    assert base.estimated_duration_s == pytest.approx(words / 2.5 + 0.4 * 5, abs=0.1)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (30, "quick_files"),
        (45, "quick_files"),
        (60, "quick_files"),
        (80, "archives"),
        (100, "archives"),
        (110, "deep_files"),
        (180, "deep_files"),
    ],
)
def test_format_for_duration(seconds: int, expected: str) -> None:
    assert CONFIG.format_for_duration(seconds) == expected


@pytest.mark.parametrize(
    ("override", "code"),
    [
        (
            {"hook": [{"text": "Pada 27 Agustus 1883 terjadi letusan.", "claim_refs": ["C-x"]}]},
            "UNKNOWN_CLAIM_REF",
        ),
        (
            {"closing": [{"text": "Suhu global turun pada 1884.", "claim_refs": ["C-u"]}]},
            "UNVERIFIED_CLAIM_USED",
        ),
        (
            {"explanation": [{"text": "Korban mencapai 120.000 orang.", "claim_refs": ["C-d"]}]},
            "UNHEDGED_CLAIM",
        ),
        (
            {"closing": [{"text": "Langit merah mengilhami lukisan itu.", "claim_refs": ["C-h"]}]},
            "UNHEDGED_CLAIM",
        ),
        (
            {"conflict": [{"text": "Lebih dari 5.000 kapal tenggelam.", "claim_refs": []}]},
            "UNSOURCED_FACT",
        ),
        (
            {
                "hook": [
                    {"text": "Pada 28 Agustus 1883, Selat Sunda berguncang.", "claim_refs": ["C-v"]}
                ]
            },
            "NUMBER_MISMATCH",
        ),
        (
            {"context": [{"text": "Semua berubah malam itu.", "claim_refs": []}]},
            "FACTUAL_SEGMENT_WITHOUT_REFS",
        ),
        (
            {
                "hook": [
                    {"text": "Ini PALING MENGERIKAN! Kamu tidak akan percaya!", "claim_refs": []}
                ]
            },
            "SENSATIONAL",
        ),
        (
            {
                "closing": [
                    {"text": 'Ia menulis "' + " ".join(["kata"] * 25) + '".', "claim_refs": []}
                ]
            },
            "LONG_QUOTE",
        ),
        (
            {
                "closing": [
                    {
                        "text": "Letusan besar itu terjadi pada pagi hari dan suaranya terdengar "
                        "sangat jauh hingga ke pulau di tengah samudra.",
                        "claim_refs": [],
                    }
                ]
            },
            "VERBATIM_SOURCE_TEXT",
        ),
    ],
    ids=[
        "unknown-ref",
        "unverified",
        "unhedged-disputed",
        "unhedged-hypothesis",
        "unsourced",
        "number-mismatch",
        "segment-no-refs",
        "sensational",
        "long-quote",
        "verbatim",
    ],
)
def test_blocking_rules(override: dict[str, list[dict[str, Any]]], code: str) -> None:
    assert _codes(_script(override)).get(code) == "blocking"


def test_contradictory_claims_both_asserted_is_blocking() -> None:
    script = _script(
        {
            "explanation": [
                {"text": "Korban mencapai 120.000 orang.", "claim_refs": ["C-d"]},
                {"text": FILLER, "claim_refs": ["C-v"]},
            ]
        }
    )
    assert _codes(script).get("CONTRADICTION") == "blocking"


def test_structure_must_follow_documentary_arc() -> None:
    script = _script(roles=["context", "hook", "conflict", "explanation", "closing"])
    assert _codes(script).get("STRUCTURE") == "blocking"


def test_too_long_for_target_or_format_is_blocking() -> None:
    long_lines = {"closing": [{"text": FILLER, "claim_refs": []}] * 8}
    assert _codes(_script(long_lines)).get("TOO_LONG") == "blocking"
    assert _codes(_script(target=30)).get("TOO_LONG") == "blocking"


def test_too_short_and_ambiguous_are_warnings_only() -> None:
    short = _script({"closing": [{"text": "Konon langit memerah.", "claim_refs": []}]}, target=45)
    codes = _codes(short)
    assert codes.get("TOO_SHORT") == "warning"
    assert codes.get("AMBIGUOUS_ATTRIBUTION") == "warning"


def test_single_sensational_term_is_only_a_warning() -> None:
    script = _script(
        {
            "closing": [
                {"text": "Kisah ini sungguh mencekam.", "claim_refs": []},
                {"text": FILLER, "claim_refs": []},
            ]
        }
    )
    codes = _codes(script)
    assert codes.get("SENSATIONAL_TERM") == "warning" and "SENSATIONAL" not in codes


def test_scripting_config_rejects_bad_format_ranges() -> None:
    raw = CONFIG.model_dump()
    raw["formats"]["quick_files"]["default_s"] = 99
    with pytest.raises(ValueError):
        ScriptingConfig.model_validate(raw)
