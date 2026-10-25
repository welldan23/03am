"""Editorial quality gate sebelum naskah diajukan ke G1.

Semua keputusan lulus/gagal bersifat deterministik. Review LLM hanya menambah saran
(advisory) dan tidak bisa membuat naskah lulus. Approval G1 tetap hanya milik owner.
"""

from __future__ import annotations

import re

from studio.modules.calls import CallScope, LLMClient
from studio.modules.research import (
    ClaimCategory,
    ClaimRecord,
    ResearchBrief,
    Severity,
    normalize,
    numbers,
    words,
)
from studio.modules.scripting.config import FormatSpec, ScriptingConfig
from studio.modules.scripting.models import (
    REQUIRED_STRUCTURE,
    DocumentaryScript,
    EditorialIssue,
    EditorialReport,
    ReviewNote,
    ScriptLine,
    ScriptReviewOutput,
    SegmentRole,
)

_QUOTED = re.compile(r'"([^"]+)"')
_ALLCAPS = re.compile(r"\b[A-Z]{4,}\b")
_STOPWORDS = frozenset(
    [
        "yang",
        "dan",
        "atau",
        "dari",
        "pada",
        "untuk",
        "dengan",
        "dalam",
        "itu",
        "ini",
        "adalah",
        "juga",
        "tidak",
        "namun",
        "tetapi",
        "karena",
        "sebagai",
        "oleh",
        "akan",
        "sudah",
        "telah",
        "lebih",
        "bisa",
        "kita",
        "mereka",
        "para",
        "sebuah",
        "satu",
    ]
)
_HEDGE_REQUIRED = {
    ClaimCategory.DISPUTED: "diperdebatkan",
    ClaimCategory.HYPOTHESIS: "hipotesis",
    ClaimCategory.INTERPRETATION: "interpretasi",
}
_INSTRUCTIONS = {
    "STRUCTURE": "Susun ulang naskah dengan urutan hook, context, conflict, explanation, closing.",
    "UNKNOWN_CLAIM_REF": "Hapus rujukan ke klaim yang tidak ada di research brief.",
    "UNVERIFIED_CLAIM_USED": "Hapus kalimat yang memakai klaim belum terverifikasi.",
    "UNHEDGED_CLAIM": "Tambahkan bahasa kehati-hatian (misalnya 'diduga', 'menurut', 'masih "
    "diperdebatkan') pada klaim yang bukan fakta terverifikasi.",
    "UNSOURCED_FACT": "Beri rujukan klaim pada setiap kalimat yang memuat angka atau tanggal, atau "
    "hapus angkanya.",
    "NUMBER_MISMATCH": "Samakan angka di narasi dengan angka pada klaim yang dirujuk.",
    "FACTUAL_SEGMENT_WITHOUT_REFS": "Segmen konteks/penjelasan wajib berdasar klaim dari brief.",
    "TOO_LONG": "Pangkas naskah agar sesuai batas durasi format dan target episode.",
    "SENSATIONAL": "Ganti kata sensasional dengan bahasa editorial yang tenang.",
    "LONG_QUOTE": "Ringkas kutipan langsung yang panjang menjadi parafrase.",
    "VERBATIM_SOURCE_TEXT": "Parafrasekan kalimat yang menyalin teks sumber kata per kata.",
    "CONTRADICTION": "Jangan menyajikan dua klaim yang saling bertentangan sebagai fakta pasti.",
}


def _has_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", text.lower()) is not None


def _content_words(text: str) -> set[str]:
    return {w for w in words(text) if len(w) >= 4 and w not in _STOPWORDS}


def _longest_common_run(line_words: list[str], source_words: list[str]) -> int:
    best = 0
    previous = [0] * (len(source_words) + 1)
    for a in line_words:
        current = [0] * (len(source_words) + 1)
        for j, b in enumerate(source_words, start=1):
            if a == b:
                current[j] = previous[j - 1] + 1
                best = max(best, current[j])
        previous = current
    return best


class EditorialGate:
    def __init__(self, llm: LLMClient, config: ScriptingConfig) -> None:
        self._llm = llm
        self._config = config
        self._rules = config.editorial

    def _hedged(self, text: str) -> bool:
        return any(_has_term(text, marker) for marker in self._rules.hedge_markers)

    def check(
        self,
        script: DocumentaryScript,
        brief: ResearchBrief,
        source_texts: dict[str, str],
        spec: FormatSpec,
    ) -> list[EditorialIssue]:
        issues: list[EditorialIssue] = []

        def add(code: str, severity: Severity, message: str, **where: int | str | None) -> None:
            issues.append(EditorialIssue(code=code, severity=severity, message=message, **where))

        roles = [segment.role for segment in script.segments]
        if roles != REQUIRED_STRUCTURE:
            add(
                "STRUCTURE",
                Severity.BLOCKING,
                f"struktur naskah {[r.value for r in roles]} tidak sesuai urutan wajib",
            )

        claims: dict[str, ClaimRecord] = {c.id: c for c in brief.all_claims()}
        source_words = {sid: words(text) for sid, text in source_texts.items()}
        unhedged_refs: set[str] = set()
        sensational = 0

        for segment in script.segments:
            segment_refs = {ref for line in segment.lines for ref in line.claim_refs}
            if segment.role in (SegmentRole.CONTEXT, SegmentRole.EXPLANATION) and not segment_refs:
                add(
                    "FACTUAL_SEGMENT_WITHOUT_REFS",
                    Severity.BLOCKING,
                    f"segmen {segment.role.value} tidak merujuk klaim apa pun",
                    segment_index=segment.index,
                )
            for line_index, line in enumerate(segment.lines, start=1):
                where: dict[str, int | str | None] = {
                    "segment_index": segment.index,
                    "line_index": line_index,
                }
                sensational += self._check_style(line, add, where)
                self._check_copyright(line, source_words, add, where)
                used = [claims[ref] for ref in line.claim_refs if ref in claims]
                for ref in line.claim_refs:
                    if ref not in claims:
                        add(
                            "UNKNOWN_CLAIM_REF",
                            Severity.BLOCKING,
                            f"rujukan {ref} tidak ada di research brief",
                            claim_id=ref,
                            **where,
                        )
                hedged = self._hedged(line.text)
                for claim in used:
                    if claim.category is ClaimCategory.UNVERIFIED:
                        add(
                            "UNVERIFIED_CLAIM_USED",
                            Severity.BLOCKING,
                            f"klaim {claim.id} belum terverifikasi tetapi dipakai di narasi",
                            claim_id=claim.id,
                            **where,
                        )
                    elif claim.category in _HEDGE_REQUIRED and not hedged:
                        add(
                            "UNHEDGED_CLAIM",
                            Severity.BLOCKING,
                            f"klaim {claim.id} berstatus {_HEDGE_REQUIRED[claim.category]} "
                            "tetapi disampaikan sebagai fakta pasti",
                            claim_id=claim.id,
                            **where,
                        )
                    if not hedged:
                        unhedged_refs.add(claim.id)
                line_numbers = numbers(line.text)
                if line_numbers and not line.claim_refs:
                    add(
                        "UNSOURCED_FACT",
                        Severity.BLOCKING,
                        f"kalimat memuat angka {sorted(line_numbers)} tanpa rujukan klaim",
                        **where,
                    )
                elif line_numbers:
                    known = set().union(*(numbers(c.statement) for c in used)) if used else set()
                    missing = sorted(line_numbers - known)
                    if missing:
                        add(
                            "NUMBER_MISMATCH",
                            Severity.BLOCKING,
                            f"angka {missing} tidak ada di klaim yang dirujuk",
                            **where,
                        )
                if used:
                    line_words = _content_words(line.text)
                    claim_words = set().union(*(_content_words(c.statement) for c in used))
                    if line_words and (
                        len(line_words & claim_words) / len(line_words)
                        < self._rules.min_claim_overlap
                    ):
                        add(
                            "CLAIM_NARRATION_MISMATCH",
                            Severity.WARNING,
                            "isi kalimat tampak tidak sesuai dengan klaim yang dirujuk",
                            **where,
                        )
                elif segment.role in (
                    SegmentRole.CONTEXT,
                    SegmentRole.EXPLANATION,
                ) and not line.text.rstrip().endswith("?"):
                    add(
                        "UNREFERENCED_SENTENCE",
                        Severity.WARNING,
                        "kalimat di segmen faktual tanpa rujukan klaim",
                        **where,
                    )
                if not line.claim_refs:
                    for term in self._rules.ambiguous_terms:
                        if _has_term(line.text, term):
                            add(
                                "AMBIGUOUS_ATTRIBUTION",
                                Severity.WARNING,
                                f"atribusi samar '{term}' tanpa rujukan sumber",
                                **where,
                            )

        for claim_id in sorted(unhedged_refs):
            for other in claims[claim_id].conflicts_with:
                if other in unhedged_refs and claim_id < other:
                    add(
                        "CONTRADICTION",
                        Severity.BLOCKING,
                        f"{claim_id} dan {other} saling bertentangan tetapi keduanya disajikan "
                        "sebagai fakta pasti",
                        claim_id=claim_id,
                    )

        if sensational >= self._rules.sensational_blocking_threshold:
            add(
                "SENSATIONAL",
                Severity.BLOCKING,
                f"{sensational} penanda sensasional "
                f"(batas {self._rules.sensational_blocking_threshold})",
            )

        tolerance = self._rules.duration_tolerance_pct / 100
        estimate = script.estimated_duration_s
        upper = min(spec.max_s, script.target_duration_s * (1 + tolerance))
        lower = max(spec.min_s, script.target_duration_s * (1 - tolerance))
        if estimate > upper:
            add(
                "TOO_LONG",
                Severity.BLOCKING,
                f"estimasi {estimate}s melebihi batas {upper:.0f}s ({spec.label}, target "
                f"{script.target_duration_s}s)",
            )
        elif estimate < lower:
            add(
                "TOO_SHORT",
                Severity.WARNING,
                f"estimasi {estimate}s di bawah {lower:.0f}s ({spec.label}, target "
                f"{script.target_duration_s}s)",
            )
        return issues

    def _check_style(self, line: ScriptLine, add, where) -> int:  # type: ignore[no-untyped-def]
        count = 0
        for term in self._rules.sensational_terms:
            if _has_term(line.text, term) or (not term.isalpha() and term in line.text):
                count += 1
                add("SENSATIONAL_TERM", Severity.WARNING, f"kata sensasional '{term}'", **where)
        if "!" in line.text:
            count += line.text.count("!")
            add("SENSATIONAL_TERM", Severity.WARNING, "tanda seru dalam narasi", **where)
        for shout in _ALLCAPS.findall(line.text):
            count += 1
            add("SENSATIONAL_TERM", Severity.WARNING, f"huruf kapital semua '{shout}'", **where)
        return count

    def _check_copyright(self, line: ScriptLine, source_words, add, where) -> None:  # type: ignore[no-untyped-def]
        for quoted in _QUOTED.findall(normalize(line.text)):
            if len(quoted.split()) > self._rules.max_quote_words:
                add(
                    "LONG_QUOTE",
                    Severity.BLOCKING,
                    f"kutipan langsung {len(quoted.split())} kata (maks "
                    f"{self._rules.max_quote_words})",
                    **where,
                )
        line_words = words(line.text)
        for source_id, tokens in source_words.items():
            run = _longest_common_run(line_words, tokens)
            if run >= self._rules.verbatim_block_words:
                add(
                    "VERBATIM_SOURCE_TEXT",
                    Severity.BLOCKING,
                    f"{run} kata berturut-turut sama persis dengan {source_id}",
                    **where,
                )
            elif run >= self._rules.verbatim_warn_words:
                add(
                    "NEAR_VERBATIM",
                    Severity.WARNING,
                    f"{run} kata berturut-turut mirip {source_id}; pertimbangkan parafrase",
                    **where,
                )

    def review(
        self,
        scope: CallScope,
        script: DocumentaryScript,
        brief: ResearchBrief,
        source_texts: dict[str, str],
        spec: FormatSpec,
        *,
        sub_key: str,
    ) -> tuple[EditorialReport, list[dict[str, object]]]:
        issues = self.check(script, brief, source_texts, spec)
        advisory = self._llm.run(
            scope,
            "script_quality_review",
            data={"script": script.model_dump(mode="json")},
            schema=ScriptReviewOutput,
            context_key=brief.topic.key,
            sub_key=sub_key,
        )
        blocking_codes = sorted({i.code for i in issues if i.severity is Severity.BLOCKING})
        report = EditorialReport(
            passed=not blocking_codes,
            script_revision=script.revision,
            issues=issues,
            advisory_notes=list(advisory.value.notes),
            revision_instructions=[_INSTRUCTIONS[c] for c in blocking_codes if c in _INSTRUCTIONS],
            metrics={
                "estimated_duration_s": script.estimated_duration_s,
                "target_duration_s": script.target_duration_s,
                "format": script.format,
                "word_count": script.word_count,
                "blocking": len([i for i in issues if i.severity is Severity.BLOCKING]),
                "warnings": len([i for i in issues if i.severity is Severity.WARNING]),
            },
        )
        return report, list(advisory.calls)


__all__ = ["EditorialGate", "ReviewNote"]
