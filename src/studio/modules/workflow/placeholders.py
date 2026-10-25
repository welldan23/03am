"""Handler tahap PLACEHOLDER untuk Fase 1.

Tidak ada AI, riset, atau render sungguhan di sini. Tiap tahap hanya membuat artefak contoh
dan mencatat biaya SIMULASI lewat BudgetGuard, supaya state machine, approval, dan ledger
bisa diuji end-to-end. Fase 2 dan 4 menggantinya dengan modul sungguhan.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from studio.modules.artifacts import Artifact, ArtifactKind
from studio.modules.budget import AuthorizationKind, CostEstimate, EstimateLine
from studio.modules.episodes import Episode, EpisodeStatus

WORDS_PER_SECOND_NUM, WORDS_PER_SECOND_DEN = 5, 2  # 2,5 kata/detik (dikalibrasi di Fase 2)
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


def _discover(ctx: StageContext) -> None:
    ctx.spend_llm(
        "discovery",
        tier="fast",
        input_tokens=1500,
        output_tokens=800,
        authorization=AuthorizationKind.OPERATIONAL,
    )
    category = ctx.episode.category.value
    ctx.put(
        ArtifactKind.TOPICS,
        {
            "placeholder": True,
            "notes": ctx.notes,
            "candidates": [
                {
                    "title": f"[PLACEHOLDER] Topik {category} #{i}",
                    "angle": "contoh angle",
                    "risk": "rendah",
                }
                for i in range(1, 4)
            ],
        },
    )


def _research(ctx: StageContext) -> None:
    ctx.spend_llm(
        "research",
        tier="fast",
        input_tokens=4000,
        output_tokens=1500,
        authorization=AuthorizationKind.PREPRODUCTION,
    )
    ctx.put(ArtifactKind.RESEARCH, {"placeholder": True, "notes": ctx.notes, "sources": []})


def _factcheck(ctx: StageContext) -> None:
    ctx.spend_llm(
        "factcheck",
        tier="smart",
        input_tokens=3000,
        output_tokens=1000,
        authorization=AuthorizationKind.PREPRODUCTION,
    )
    ctx.put(ArtifactKind.FACTCHECK, {"placeholder": True, "notes": ctx.notes, "claims": []})


def _script(ctx: StageContext) -> None:
    ctx.spend_llm(
        "script",
        tier="smart",
        input_tokens=2500,
        output_tokens=1200,
        authorization=AuthorizationKind.PREPRODUCTION,
    )
    words = ctx.episode.target_duration_s * WORDS_PER_SECOND_NUM // WORDS_PER_SECOND_DEN
    ctx.put(
        ArtifactKind.SCRIPT,
        {
            "placeholder": True,
            "notes": ctx.notes,
            "word_count": words,
            "text": "[PLACEHOLDER] Naskah narasi akan dibuat di Fase 2.",
        },
    )


def _storyboard(ctx: StageContext) -> None:
    ctx.spend_llm(
        "storyboard",
        tier="fast",
        input_tokens=2000,
        output_tokens=1500,
        authorization=AuthorizationKind.PREPRODUCTION,
    )
    shot_count = max(1, ctx.episode.target_duration_s // SHOT_SECONDS)
    shots = [
        {
            "index": i + 1,
            "duration_s": SHOT_SECONDS,
            "visual": "ai_video" if i < MAX_HERO_SHOTS else "ai_image",
        }
        for i in range(shot_count)
    ]
    ctx.put(ArtifactKind.STORYBOARD, {"placeholder": True, "notes": ctx.notes, "shots": shots})


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
    EpisodeStatus.DISCOVERING: _discover,
    EpisodeStatus.RESEARCHING: _research,
    EpisodeStatus.FACT_CHECKING: _factcheck,
    EpisodeStatus.SCRIPTING: _script,
    EpisodeStatus.STORYBOARDING: _storyboard,
    EpisodeStatus.ESTIMATING_COST: _estimate_cost,
    EpisodeStatus.GENERATING_ASSETS: _generate_assets,
    EpisodeStatus.GENERATING_VOICE: _generate_voice,
    EpisodeStatus.RENDERING: _render,
    EpisodeStatus.EXPORTING: _export,
}
