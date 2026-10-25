"""Tabel transisi state machine episode — satu-satunya sumber aturan transisi.

Lihat diagram di docs/ARCHITECTURE.md §6.1. Mengubah tabel ini = update test + diagram.
"""

from __future__ import annotations

from collections.abc import Mapping

from studio.modules.episodes.models import EpisodeStatus as S
from studio.modules.episodes.models import IllegalTransitionError
from studio.modules.episodes.models import Trigger as T
from studio.shared.gates import Gate

# Urutan produksi. Posisi dipakai untuk menentukan target revisi dan gate yang digantikan.
PIPELINE: tuple[S, ...] = (
    S.DISCOVERING,
    S.AWAITING_TOPIC,
    S.RESEARCHING,
    S.FACT_CHECKING,
    S.SCRIPTING,
    S.STORYBOARDING,
    S.AWAITING_EDITORIAL,
    S.ESTIMATING_COST,
    S.AWAITING_COST,
    S.GENERATING_ASSETS,
    S.GENERATING_VOICE,
    S.RENDERING,
    S.AWAITING_FINAL,
    S.EXPORTING,
    S.EXPORTED,
)

GATE_STATUS: Mapping[Gate, S] = {
    Gate.TOPIC: S.AWAITING_TOPIC,
    Gate.EDITORIAL: S.AWAITING_EDITORIAL,
    Gate.COST: S.AWAITING_COST,
    Gate.FINAL: S.AWAITING_FINAL,
}
STATUS_GATE: Mapping[S, Gate] = {status: gate for gate, status in GATE_STATUS.items()}

# Status kerja = ada job yang mengerjakannya.
WORKING: frozenset[S] = frozenset(
    {
        S.DISCOVERING,
        S.RESEARCHING,
        S.FACT_CHECKING,
        S.SCRIPTING,
        S.STORYBOARDING,
        S.ESTIMATING_COST,
        S.GENERATING_ASSETS,
        S.GENERATING_VOICE,
        S.RENDERING,
        S.EXPORTING,
    }
)
TERMINAL: frozenset[S] = frozenset({S.EXPORTED, S.REJECTED, S.CANCELLED})

NEXT_ON_COMPLETE: Mapping[S, S] = {
    S.DISCOVERING: S.AWAITING_TOPIC,
    S.RESEARCHING: S.FACT_CHECKING,
    S.FACT_CHECKING: S.SCRIPTING,
    S.SCRIPTING: S.STORYBOARDING,
    S.STORYBOARDING: S.AWAITING_EDITORIAL,
    S.ESTIMATING_COST: S.AWAITING_COST,
    S.GENERATING_ASSETS: S.GENERATING_VOICE,
    S.GENERATING_VOICE: S.RENDERING,
    S.RENDERING: S.AWAITING_FINAL,
    S.EXPORTING: S.EXPORTED,
}

NEXT_ON_APPROVE: Mapping[S, S] = {
    S.AWAITING_TOPIC: S.RESEARCHING,
    S.AWAITING_EDITORIAL: S.ESTIMATING_COST,
    S.AWAITING_COST: S.GENERATING_ASSETS,
    S.AWAITING_FINAL: S.EXPORTING,
}


def position(status: S) -> int:
    return PIPELINE.index(status)


def _revision_targets(gate_status: S) -> frozenset[S]:
    if gate_status is S.AWAITING_TOPIC:
        return frozenset({S.DISCOVERING})
    start, end = position(S.RESEARCHING), position(gate_status)
    return frozenset(s for s in PIPELINE[start:end] if s in WORKING)


REVISION_TARGETS: Mapping[S, frozenset[S]] = {
    gate_status: _revision_targets(gate_status) for gate_status in GATE_STATUS.values()
}


def _build_table() -> dict[tuple[S, T], frozenset[S]]:
    table: dict[tuple[S, T], frozenset[S]] = {(S.DRAFT, T.START): frozenset({S.DISCOVERING})}
    for source, target in NEXT_ON_COMPLETE.items():
        table[(source, T.COMPLETE)] = frozenset({target})
    for source, target in NEXT_ON_APPROVE.items():
        table[(source, T.APPROVE)] = frozenset({target})
        table[(source, T.REJECT)] = frozenset({S.REJECTED})
        table[(source, T.REVISE)] = REVISION_TARGETS[source]
    for source in WORKING:
        table[(source, T.FAIL)] = frozenset({S.FAILED})
    table[(S.FAILED, T.RETRY)] = WORKING
    for source in S:
        if source not in TERMINAL:
            table[(source, T.CANCEL)] = frozenset({S.CANCELLED})
    return table


TRANSITIONS: Mapping[tuple[S, T], frozenset[S]] = _build_table()


def allowed_targets(source: S, trigger: T) -> frozenset[S]:
    return TRANSITIONS.get((source, trigger), frozenset())


def check_transition(source: S, trigger: T, target: S) -> None:
    if target not in allowed_targets(source, trigger):
        raise IllegalTransitionError(
            f"transisi {source.value} --{trigger.value}--> {target.value} tidak diizinkan"
        )


def gates_invalidated_by_revision(target: S) -> tuple[Gate, ...]:
    """Gate yang posisinya setelah `target` harus disetujui ulang."""
    target_pos = position(target)
    return tuple(gate for gate, status in GATE_STATUS.items() if position(status) > target_pos)
