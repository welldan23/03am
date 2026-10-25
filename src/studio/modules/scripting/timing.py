"""Estimasi durasi narasi dari kecepatan baca yang bisa dikonfigurasi."""

from __future__ import annotations

from studio.modules.research import word_count
from studio.modules.scripting.config import FormatSpec, NarrationConfig
from studio.modules.scripting.models import DocumentaryScript, ScriptDraft, ScriptSegment


def build_script(
    draft: ScriptDraft,
    *,
    format_name: str,
    spec: FormatSpec,
    target_duration_s: int,
    narration: NarrationConfig,
    revision: int,
    notes: str | None,
) -> DocumentaryScript:
    words_per_second = narration.words_per_minute / 60
    segments: list[ScriptSegment] = []
    cursor = 0.0
    for index, segment in enumerate(draft.segments, start=1):
        words = sum(word_count(line.text) for line in segment.lines)
        duration = round(words / words_per_second + narration.segment_pause_s, 2)
        segments.append(
            ScriptSegment(
                index=index,
                role=segment.role,
                visual_direction=segment.visual_direction,
                lines=segment.lines,
                word_count=words,
                start_s=round(cursor, 2),
                end_s=round(cursor + duration, 2),
                duration_s=duration,
            )
        )
        cursor += duration
    refs = sorted({ref for seg in segments for line in seg.lines for ref in line.claim_refs})
    return DocumentaryScript(
        title=draft.title,
        format=format_name,
        format_label=spec.label,
        target_duration_s=target_duration_s,
        words_per_minute=narration.words_per_minute,
        segments=segments,
        narration_text=" ".join(seg.text for seg in segments),
        word_count=sum(seg.word_count for seg in segments),
        estimated_duration_s=round(cursor, 1),
        claim_refs=refs,
        pronunciation_notes=draft.pronunciation_notes,
        revision=revision,
        notes=notes,
    )
