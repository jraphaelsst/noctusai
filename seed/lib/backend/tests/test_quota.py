"""Tests for `noctusai_lib.integrations.quota`.

Contract test parametrized over both backends (`InMemoryQuotaTracker`
+ `RedisQuotaTracker` against `fakeredis`) so the Protocol-level
behavior stays in lock-step. Per-backend tests cover specifics
(InMemory determinism, Redis Lua atomicity).

Async surface but no `pytest-asyncio` configured — use `asyncio.run(...)`
matching the existing seed-lib convention (see
`tests/integrations/whatsapp/test_fake_adapter.py`).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, List, Tuple

import pytest

from noctusai_lib.integrations.quota import (
    InMemoryQuotaTracker,
    QuotaCheck,
    QuotaConfig,
    QuotaTracker,
    RedisQuotaTracker,
    make_quota_tracker,
)
from noctusai_lib.integrations.redis import make_fake_redis_client


# ----------------------------------------------------------------------
# Helpers


class FakeClock:
    """Mutable clock for deterministic time-fast-forwarding in tests."""

    def __init__(self, start: datetime) -> None:
        self._t = start

    def __call__(self) -> datetime:
        return self._t

    def advance(self, *, seconds: float) -> None:
        self._t = self._t + timedelta(seconds=seconds)


def _make_in_memory(now: Callable[[], datetime]) -> InMemoryQuotaTracker:
    return InMemoryQuotaTracker(now=now)


def _make_redis(now: Callable[[], datetime]) -> RedisQuotaTracker:
    client = make_fake_redis_client()
    return RedisQuotaTracker(
        client, key_prefix=f"test:{id(client)}", now=now
    )


BACKEND_FACTORIES: List[Tuple[str, Callable[[Callable[[], datetime]], QuotaTracker]]] = [
    ("memory", _make_in_memory),
    ("redis_fake", _make_redis),
]


# ----------------------------------------------------------------------
# Contract tests — parametrized over both backends


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_register_then_consume_within_cap_succeeds(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> List[QuotaCheck]:
        await tracker.register_quota(
            key="k1", config=QuotaConfig(cap=3, window_seconds=60)
        )
        return [
            await tracker.consume(key="k1"),
            await tracker.consume(key="k1"),
            await tracker.consume(key="k1"),
        ]

    checks = asyncio.run(run())
    assert all(c.allowed for c in checks), f"{name}: {checks}"
    assert [c.used for c in checks] == [1, 2, 3]
    assert [c.remaining for c in checks] == [2, 1, 0]
    assert all(c.key == "k1" for c in checks)


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_consume_past_cap_denies_atomically(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> Tuple[List[QuotaCheck], QuotaCheck, QuotaCheck]:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=2, window_seconds=60)
        )
        ok = [await tracker.consume(key="k") for _ in range(2)]
        denied = await tracker.consume(key="k")
        # Confirm the denied call did NOT bump the counter — peek
        # should still report used=2.
        peek = await tracker.peek(key="k")
        return ok, denied, peek

    ok, denied, peek = asyncio.run(run())
    assert all(c.allowed for c in ok), f"{name}: ok={ok}"
    assert denied.allowed is False, f"{name}: denied={denied}"
    assert denied.remaining == 0
    assert denied.used == 2  # pre-call usage; units NOT recorded
    assert peek.used == 2, f"{name}: peek shows units leaked: {peek}"


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_consume_units_greater_than_one(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> Tuple[QuotaCheck, QuotaCheck]:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=10, window_seconds=60)
        )
        first = await tracker.consume(key="k", units=7)
        # 7 + 5 = 12 > cap=10 → denied, NO commit.
        denied = await tracker.consume(key="k", units=5)
        return first, denied

    first, denied = asyncio.run(run())
    assert first.allowed is True
    assert first.used == 7
    assert first.remaining == 3
    assert denied.allowed is False
    assert denied.used == 7  # unchanged from first call
    assert denied.remaining == 3


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_peek_is_non_mutating(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> Tuple[QuotaCheck, QuotaCheck, QuotaCheck]:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=5, window_seconds=60)
        )
        await tracker.consume(key="k", units=2)
        peek1 = await tracker.peek(key="k")
        peek2 = await tracker.peek(key="k")
        # And a third — confirm peeking many times doesn't drift used.
        peek3 = await tracker.peek(key="k")
        return peek1, peek2, peek3

    p1, p2, p3 = asyncio.run(run())
    for p in (p1, p2, p3):
        assert p.used == 2
        assert p.remaining == 3
        assert p.allowed is True  # 2 < cap 5


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_reset_clears_usage_keeps_config(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> Tuple[QuotaCheck, QuotaCheck, QuotaCheck]:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=2, window_seconds=60)
        )
        before = await tracker.consume(key="k", units=2)
        await tracker.reset(key="k")
        after_reset = await tracker.peek(key="k")
        # Config preserved → consume(1) should still be admitted.
        post = await tracker.consume(key="k", units=1)
        return before, after_reset, post

    before, after_reset, post = asyncio.run(run())
    assert before.used == 2 and before.remaining == 0
    assert after_reset.used == 0 and after_reset.remaining == 2
    assert post.allowed is True
    assert post.used == 1


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_window_expiry_releases_capacity(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def fill_to_cap() -> QuotaCheck:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=3, window_seconds=10)
        )
        for _ in range(3):
            await tracker.consume(key="k")
        # Cap reached.
        return await tracker.peek(key="k")

    capped = asyncio.run(fill_to_cap())
    assert capped.used == 3
    assert capped.allowed is False  # 1-unit consume would fail

    # Fast-forward past the 10s window — sliding-window should release
    # all three records.
    clock.advance(seconds=11)

    async def after_expiry() -> Tuple[QuotaCheck, QuotaCheck]:
        peek = await tracker.peek(key="k")
        consumed = await tracker.consume(key="k")
        return peek, consumed

    peek, consumed = asyncio.run(after_expiry())
    assert peek.used == 0
    assert peek.remaining == 3
    assert peek.allowed is True
    assert consumed.allowed is True
    assert consumed.used == 1


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_consume_unregistered_key_raises(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> None:
        await tracker.consume(key="never-registered")

    with pytest.raises(KeyError):
        asyncio.run(run())


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_negative_units_raises(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> None:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=5, window_seconds=60)
        )
        await tracker.consume(key="k", units=-1)

    with pytest.raises(ValueError):
        asyncio.run(run())


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_burst_extends_effective_cap(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    async def run() -> Tuple[QuotaCheck, QuotaCheck, QuotaCheck]:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=3, window_seconds=60, burst=2)
        )
        # Effective cap is 5 (3 + 2). Five consumes succeed, sixth denied.
        results = []
        for _ in range(5):
            results.append(await tracker.consume(key="k"))
        denied = await tracker.consume(key="k")
        peek = await tracker.peek(key="k")
        # Return last admitted + denied + peek.
        return results[-1], denied, peek

    last_ok, denied, peek = asyncio.run(run())
    assert last_ok.allowed is True
    assert last_ok.used == 5
    assert last_ok.remaining == 0
    assert denied.allowed is False
    assert peek.used == 5


# ----------------------------------------------------------------------
# Atomicity — concurrent consume calls must not double-count


@pytest.mark.parametrize("name,factory", BACKEND_FACTORIES)
def test_concurrent_consume_does_not_double_count(name, factory) -> None:
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = factory(clock)

    cap = 10
    parallel = 50  # 5x oversubscribe — denied count == parallel - cap

    async def run() -> Iterable[QuotaCheck]:
        await tracker.register_quota(
            key="race", config=QuotaConfig(cap=cap, window_seconds=60)
        )
        return await asyncio.gather(
            *(tracker.consume(key="race") for _ in range(parallel))
        )

    checks = list(asyncio.run(run()))
    allowed = [c for c in checks if c.allowed]
    denied = [c for c in checks if not c.allowed]
    assert len(allowed) == cap, (
        f"{name}: allowed={len(allowed)} expected={cap}; "
        f"used values={[c.used for c in checks]}"
    )
    assert len(denied) == parallel - cap


# ----------------------------------------------------------------------
# YouTube-quota example — directly verifies the lift's win condition


def test_youtube_quota_example_search_burns_units_fast() -> None:
    """`search.list` costs 100 units; daily cap is 10,000 → 100 calls
    permitted, 101st denied.
    """
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = InMemoryQuotaTracker(now=clock)

    async def run() -> Tuple[List[bool], QuotaCheck]:
        await tracker.register_quota(
            key="yt:tenant-1",
            config=QuotaConfig(cap=10_000, window_seconds=86_400),
        )
        # 99 successful search.list calls (each 100 units) → 9_900 used.
        # 100th call (=10_000) → still allowed (== cap).
        results: List[bool] = []
        for _ in range(100):
            check = await tracker.consume(key="yt:tenant-1", units=100)
            results.append(check.allowed)
        # 101st call → would push to 10_100, denied.
        denied = await tracker.consume(key="yt:tenant-1", units=100)
        return results, denied

    results, denied = asyncio.run(run())
    assert all(results), f"expected 100 allowed; got {sum(results)}"
    assert denied.allowed is False
    assert denied.used == 10_000
    assert denied.remaining == 0


def test_youtube_quota_cheap_path_burns_50x_less() -> None:
    """`list_channel_videos` strategy is ~2 units / page (50 videos);
    one daily quota of 10_000 supports ~5_000 pages = 250_000 videos
    listed, vs. ~100 search calls = 5_000 results. Verifies the seed
    encodes "use the cheap path" via cost arithmetic.
    """
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = InMemoryQuotaTracker(now=clock)

    async def run() -> int:
        await tracker.register_quota(
            key="yt:tenant-2",
            config=QuotaConfig(cap=10_000, window_seconds=86_400),
        )
        admitted = 0
        for _ in range(5_001):
            c = await tracker.consume(key="yt:tenant-2", units=2)
            if c.allowed:
                admitted += 1
            else:
                break
        return admitted

    admitted = asyncio.run(run())
    assert admitted == 5_000


# ----------------------------------------------------------------------
# Per-backend specifics


def test_factory_memory_default() -> None:
    tracker = make_quota_tracker()
    assert isinstance(tracker, InMemoryQuotaTracker)


def test_factory_redis_requires_client() -> None:
    with pytest.raises(ValueError):
        make_quota_tracker(kind="redis")


def test_factory_redis_with_fake_client() -> None:
    tracker = make_quota_tracker(
        kind="redis", redis_client=make_fake_redis_client()
    )
    assert isinstance(tracker, RedisQuotaTracker)


def test_factory_unknown_kind_raises() -> None:
    with pytest.raises(ValueError):
        make_quota_tracker(kind="hypothetical")  # type: ignore[arg-type]


def test_quota_config_validates_inputs() -> None:
    with pytest.raises(ValueError):
        QuotaConfig(cap=-1, window_seconds=60)
    with pytest.raises(ValueError):
        QuotaConfig(cap=10, window_seconds=0)
    with pytest.raises(ValueError):
        QuotaConfig(cap=10, window_seconds=60, burst=-1)


def test_in_memory_runtime_checkable_protocol() -> None:
    tracker = InMemoryQuotaTracker()
    assert isinstance(tracker, QuotaTracker)


def test_redis_runtime_checkable_protocol() -> None:
    tracker = RedisQuotaTracker(make_fake_redis_client())
    assert isinstance(tracker, QuotaTracker)


def test_register_preserves_existing_records_on_cap_change() -> None:
    """Hot-swapping the cap on a running tracker keeps the in-flight
    counter intact (so a 5→10 raise admits new traffic immediately
    without a phantom carry-over reset).
    """
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc))
    tracker = InMemoryQuotaTracker(now=clock)

    async def run() -> Tuple[QuotaCheck, QuotaCheck]:
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=3, window_seconds=60)
        )
        for _ in range(3):
            await tracker.consume(key="k")
        # Hot raise.
        await tracker.register_quota(
            key="k", config=QuotaConfig(cap=10, window_seconds=60)
        )
        peek = await tracker.peek(key="k")
        consumed = await tracker.consume(key="k")
        return peek, consumed

    peek, consumed = asyncio.run(run())
    assert peek.used == 3
    assert peek.remaining == 7  # 10 - 3
    assert consumed.allowed is True
    assert consumed.used == 4
