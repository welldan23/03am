"""Handler tahap PLACEHOLDER (berjalan di dalam transaksi, tanpa I/O).

Sejak Fase 2, discovery → riset → cek fakta → naskah memakai mesin sungguhan (lihat
`stages.py`). Yang tersisa di sini: storyboard turunan naskah, estimasi biaya, aset, suara,
render, dan ekspor — semuanya contoh dengan biaya SIMULASI sampai Fase 4.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from studio.modules.artifacts import Artifact, ArtifactKind
from studio.modules.budget import AuthorizationKind, CostEstimate, EstimateLine
from studio.modules.episodes import Episode, EpisodeStatus

CHARS_PER_WORD = 6
SHOT_SECONDS = 5
MAX_HERO_SHOTS = 3


class StageContext(Protocol):
    @property
    def episode(self) -> Episode: ...

    @property
    def notes(self) -> str | None: ...

    def put(self, kind: ArtifactKind, content: dict[str, Any]) -> Artifact: ...

    def latest(self, kind: ArtifactKind) -> Artifact: ...

    def spend_llm(
        self,
        label: str,
        *,
        tier: str,
        input_tokens: int,
        output_tokens: int,
        authorization: AuthorizationKind,
    ) -> None: ...

    def spend_units(
        self, label: str, *, price_key: str, quantity: int, authorization: AuthorizationKind
    ) -> None: ...

    def estimate(self, lines: list[EstimateLine]) -> CostEstimate: ...


def _storyboard(ctx: StageContext) -> None:
    """Storyboard sementara diturunkan dari segmen naskah (storyboard visual sungguhan: Fase 4).

    Tidak memanggil provider: hanya membagi tiap segmen ke shot ±5 detik dan membawa arahan
    visual dari naskah.
    """
    script = ctx.latest(ArtifactKind.SCRIPT).content
    shots: list[dict[str, Any]] = []
    for segment in script["segments"]:
        count = max(1, math.ceil(float(segment["duration_s"]) / SHOT_SECONDS))
        for _ in range(count):
            index = len(shots) + 1
            shots.append(
                {
                    "index": index,
                    "segment": segment["role"],
                    "duration_s": SHOT_SECONDS,
                    "visual": "ai_video" if index <= MAX_HERO_SHOTS else "ai_image",
                    "direction": segment["visual_direction"],
                }
            )
    ctx.put(
        ArtifactKind.STORYBOARD,
        {
            "placeholder": True,
            "derived_from_script_revision": script.get("revision", 0),
            "notes": ctx.notes,
            "shots": shots,
        },
    )


def _estimate_cost(ctx: StageContext) -> None:
    shots = ctx.latest(ArtifactKind.STORYBOARD).content["shots"]
    words = int(ctx.latest(ArtifactKind.SCRIPT).content["word_count"])
    video_seconds = sum(s["duration_s"] for s in shots if s["visual"] == "ai_video")
    images = sum(1 for s in shots if s["visual"] == "ai_image")
    lines = [
        EstimateLine("higgsfield.video_second", video_seconds, "video hero"),
        EstimateLine("higgsfield.image", images, "gambar diam"),
        EstimateLine("tts.characters", words * CHARS_PER_WORD, "voice-over"),
    ]
    ctx.put(ArtifactKind.COST_ESTIMATE, ctx.estimate(lines).to_dict())


def _spend_estimate_lines(ctx: StageContext, category: str) -> None:
    estimate_content = ctx.latest(ArtifactKind.COST_ESTIMATE).content
    for line in estimate_content["lines"]:
        if line["category"] == category and line["quantity"] > 0:
            ctx.spend_units(
                line["price_key"],
                price_key=line["price_key"],
                quantity=line["quantity"],
                authorization=AuthorizationKind.PRODUCTION,
            )


def _generate_assets(ctx: StageContext) -> None:
    _spend_estimate_lines(ctx, "higgsfield")


def _generate_voice(ctx: StageContext) -> None:
    _spend_estimate_lines(ctx, "tts")


def _render(ctx: StageContext) -> None:
    ctx.put(
        ArtifactKind.RENDER,
        {
            "placeholder": True,
            "duration_s": ctx.episode.target_duration_s,
            "note": "Render FFmpeg sungguhan dibuat di Fase 4.",
        },
    )


def _export(ctx: StageContext) -> None:
    ctx.put(
        ArtifactKind.EXPORT,
        {
            "placeholder": True,
            "note": "Fase 1 tidak membuat file ekspor. Tidak ada publikasi ke platform mana pun.",
        },
    )


PLACEHOLDER_STAGES: Mapping[EpisodeStatus, Callable[[StageContext], None]] = {
    EpisodeStatus.STORYBOARDING: _storyboard,
    EpisodeStatus.ESTIMATING_COST: _estimate_cost,
    EpisodeStatus.GENERATING_ASSETS: _generate_assets,
    EpisodeStatus.GENERATING_VOICE: _generate_voice,
    EpisodeStatus.RENDERING: _render,
    EpisodeStatus.EXPORTING: _export,
}
