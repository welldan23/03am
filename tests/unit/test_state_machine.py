"""Tabel transisi dibandingkan dengan spesifikasi manual dari ARCHITECTURE §6.1."""

import itertools

import pytest

from studio.modules.episodes import EpisodeStatus as S
from studio.modules.episodes import IllegalTransitionError, state
from studio.modules.episodes import Trigger as T
from studio.shared.gates import Gate

WORKING = [
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
]
TERMINAL = [S.EXPORTED, S.REJECTED, S.CANCELLED]
GATES = [S.AWAITING_TOPIC, S.AWAITING_EDITORIAL, S.AWAITING_COST, S.AWAITING_FINAL]

SPEC: set[tuple[S, T, S]] = {
    (S.DRAFT, T.START, S.DISCOVERING),
    (S.DISCOVERING, T.COMPLETE, S.AWAITING_TOPIC),
    (S.RESEARCHING, T.COMPLETE, S.FACT_CHECKING),
    (S.FACT_CHECKING, T.COMPLETE, S.SCRIPTING),
    (S.SCRIPTING, T.COMPLETE, S.STORYBOARDING),
    (S.STORYBOARDING, T.COMPLETE, S.AWAITING_EDITORIAL),
    (S.ESTIMATING_COST, T.COMPLETE, S.AWAITING_COST),
    (S.GENERATING_ASSETS, T.COMPLETE, S.GENERATING_VOICE),
    (S.GENERATING_VOICE, T.COMPLETE, S.RENDERING),
    (S.RENDERING, T.COMPLETE, S.AWAITING_FINAL),
    (S.EXPORTING, T.COMPLETE, S.EXPORTED),
    (S.AWAITING_TOPIC, T.APPROVE, S.RESEARCHING),
    (S.AWAITING_EDITORIAL, T.APPROVE, S.ESTIMATING_COST),
    (S.AWAITING_COST, T.APPROVE, S.GENERATING_ASSETS),
    (S.AWAITING_FINAL, T.APPROVE, S.EXPORTING),
    (S.AWAITING_TOPIC, T.REVISE, S.DISCOVERING),
    *(
        (S.AWAITING_EDITORIAL, T.REVISE, t)
        for t in (S.RESEARCHING, S.FACT_CHECKING, S.SCRIPTING, S.STORYBOARDING)
    ),
    *(
        (S.AWAITING_COST, T.REVISE, t)
        for t in (S.RESEARCHING, S.FACT_CHECKING, S.SCRIPTING, S.STORYBOARDING, S.ESTIMATING_COST)
    ),
    *(
        (S.AWAITING_FINAL, T.REVISE, t)
        for t in (
            S.RESEARCHING,
            S.FACT_CHECKING,
            S.SCRIPTING,
            S.STORYBOARDING,
            S.ESTIMATING_COST,
            S.GENERATING_ASSETS,
            S.GENERATING_VOICE,
            S.RENDERING,
        )
    ),
    *((g, T.REJECT, S.REJECTED) for g in GATES),
    *((w, T.FAIL, S.FAILED) for w in WORKING),
    *((S.FAILED, T.RETRY, w) for w in WORKING),
    *((s, T.CANCEL, S.CANCELLED) for s in S if s not in TERMINAL),
}


def test_transition_table_matches_spec_for_every_combination() -> None:
    """Semua 19 × 8 × 19 kombinasi (status, trigger, target) dicek terhadap spesifikasi."""
    mismatches = []
    for source, trigger, target in itertools.product(S, T, S):
        legal = (source, trigger, target) in SPEC
        if (target in state.allowed_targets(source, trigger)) is not legal:
            mismatches.append((source.value, trigger.value, target.value, legal))
            continue
        if legal:
            state.check_transition(source, trigger, target)
        else:
            with pytest.raises(IllegalTransitionError):
                state.check_transition(source, trigger, target)
    assert mismatches == []


def test_happy_path_follows_pipeline_order() -> None:
    status = S.DRAFT
    visited = []
    trigger = T.START
    while status is not S.EXPORTED:
        (status,) = state.allowed_targets(status, trigger)
        visited.append(status)
        trigger = T.APPROVE if status in state.STATUS_GATE else T.COMPLETE
    assert tuple(visited) == state.PIPELINE


def test_terminal_states_have_no_exit() -> None:
    for status, trigger in itertools.product(TERMINAL, T):
        assert state.allowed_targets(status, trigger) == frozenset()


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (S.DISCOVERING, (Gate.TOPIC, Gate.EDITORIAL, Gate.COST, Gate.FINAL)),
        (S.RESEARCHING, (Gate.EDITORIAL, Gate.COST, Gate.FINAL)),
        (S.SCRIPTING, (Gate.EDITORIAL, Gate.COST, Gate.FINAL)),
        (S.ESTIMATING_COST, (Gate.COST, Gate.FINAL)),
        (S.RENDERING, (Gate.FINAL,)),
    ],
)
def test_revision_invalidates_later_gates(target: S, expected: tuple[Gate, ...]) -> None:
    assert state.gates_invalidated_by_revision(target) == expected
