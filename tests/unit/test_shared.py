import socket
from datetime import UTC, datetime, timedelta

import pytest
from pytest_socket import SocketBlockedError

from studio.shared.actors import Actor, ActorKind, OwnerPolicy
from studio.shared.clock import FakeClock, from_iso, to_iso
from studio.shared.errors import NotAuthorizedError
from studio.shared.hashing import canonical_json, content_hash
from studio.shared.ids import is_valid_id, new_id


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_network_is_blocked_in_tests() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_ulid_format_and_time_order() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    first = new_id(clock)
    clock.advance(timedelta(milliseconds=5))
    second = new_id(clock)
    assert is_valid_id(first) and is_valid_id(second)
    assert first < second


def test_ulid_is_monotonic_within_same_millisecond() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    ids = [new_id(clock) for _ in range(500)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_iso_roundtrip_is_utc() -> None:
    moment = datetime(2026, 11, 3, 2, 0, 0, 123456, tzinfo=UTC)
    assert to_iso(moment) == "2026-11-03T02:00:00.123456Z"
    assert from_iso(to_iso(moment)) == moment
    with pytest.raises(ValueError):
        to_iso(datetime(2026, 1, 1))


def test_fake_clock_requires_timezone() -> None:
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 1, 1))


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert content_hash({"x": [1, 2]}) != content_hash({"x": [2, 1]})


def test_owner_policy_only_allows_allowlisted_owner() -> None:
    policy = OwnerPolicy(frozenset({"cli:owner"}))
    assert policy.is_owner(Actor.owner("cli:owner"))
    assert not policy.is_owner(Actor.owner("telegram:999"))
    assert not policy.is_owner(Actor(ActorKind.DIRECTOR, "cli:owner"))
    assert not policy.is_owner(Actor.system("cli:owner"))
    with pytest.raises(NotAuthorizedError):
        policy.require_owner(Actor.director(), "approve")


def test_empty_allowlist_denies_everyone() -> None:
    assert not OwnerPolicy(frozenset()).is_owner(Actor.owner("cli:owner"))
