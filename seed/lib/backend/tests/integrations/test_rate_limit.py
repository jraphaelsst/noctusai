"""Unit tests for the outbound rate-limit primitive.

Uses an explicit VirtualClock so pacing/backoff logic is exercised
deterministically without any real waiting. (The autouse conftest fixture
also installs a virtual default clock; these tests inject their own for
precise control.)
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.rate_limit import (
    BucketConfig,
    TokenBucket,
    VirtualClock,
    parse_retry_after,
    retry_with_backoff,
)


class _RateLimited(Exception):
    def __init__(self, retry_after: float | None = None):
        super().__init__("429")
        self.retry_after = retry_after


# ─── TokenBucket pacing ─────────────────────────────────────────────────────


def test_burst_is_immediate_then_paced():
    clk = VirtualClock()
    b = TokenBucket(BucketConfig(rate_per_sec=2.0, burst=3.0), clock=clk)
    # First `burst` acquires are free (no wait).
    assert b.acquire() == 0.0
    assert b.acquire() == 0.0
    assert b.acquire() == 0.0
    # 4th must wait ~1 token / 2 per sec = 0.5s of virtual time.
    waited = b.acquire()
    assert waited == pytest.approx(0.5, abs=1e-6)


def test_refill_over_time_allows_more():
    clk = VirtualClock()
    b = TokenBucket(BucketConfig(rate_per_sec=10.0, burst=1.0), clock=clk)
    assert b.acquire() == 0.0
    # advance 1s of virtual time -> 10 tokens refilled (capped at burst=1)
    clk.sleep(1.0)
    assert b.acquire() == 0.0  # refilled, immediate


def test_sustained_rate_paces_to_configured_rps():
    clk = VirtualClock()
    b = TokenBucket(BucketConfig(rate_per_sec=4.0, burst=1.0), clock=clk)
    b.acquire()  # consume the initial token
    total = 0.0
    for _ in range(4):
        total += b.acquire()
    # 4 more acquires at 4/s with burst 1 => ~0.25s each = ~1.0s
    assert total == pytest.approx(1.0, abs=1e-6)


# ─── retry_with_backoff ─────────────────────────────────────────────────────


def test_retries_then_succeeds():
    clk = VirtualClock()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimited()
        return "ok"

    out = retry_with_backoff(
        fn, bucket="meta", is_retryable=lambda e: isinstance(e, _RateLimited), clock=clk
    )
    assert out == "ok"
    assert calls["n"] == 3


def test_non_retryable_propagates_immediately():
    clk = VirtualClock()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("boom")

    with pytest.raises(ValueError):
        retry_with_backoff(
            fn, bucket="meta",
            is_retryable=lambda e: isinstance(e, _RateLimited), clock=clk,
        )
    assert calls["n"] == 1  # no retry on a non-rate-limit error


def test_gives_up_after_max_retries_and_reraises():
    clk = VirtualClock()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _RateLimited()

    # meta bucket max_retries default is 6 -> 1 initial + 6 retries = 7 calls
    with pytest.raises(_RateLimited):
        retry_with_backoff(
            fn, bucket="meta",
            is_retryable=lambda e: isinstance(e, _RateLimited), clock=clk,
        )
    assert calls["n"] == rate_limit._config_for("meta").max_retries + 1


def test_honors_retry_after_hint():
    clk = VirtualClock()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _RateLimited(retry_after=12.0)
        return "ok"

    retry_with_backoff(
        fn, bucket="meta",
        is_retryable=lambda e: isinstance(e, _RateLimited),
        retry_after=lambda e: getattr(e, "retry_after", None),
        clock=clk,
    )
    # Virtual time advanced by exactly the hinted 12s (not exp backoff).
    assert clk.monotonic() == pytest.approx(12.0, abs=1e-6)


# ─── parse_retry_after ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [("120", 120.0), ("0", 0.0), (None, None), ("-5", None), ("abc", None), (30, 30.0)],
)
def test_parse_retry_after(value, expected):
    assert parse_retry_after(value) == expected


# ─── async path ─────────────────────────────────────────────────────────────


def test_acquire_async_paces_without_blocking():
    import asyncio

    rate_limit.set_default_clock(VirtualClock())
    rate_limit._reset_all_buckets()
    try:
        async def run():
            # meta burst=5 -> first 5 immediate, 6th paced (3/s => ~0.333s)
            waits = [await rate_limit.acquire_async("meta") for _ in range(6)]
            return waits

        waits = asyncio.run(run())
        assert waits[:5] == [0.0, 0.0, 0.0, 0.0, 0.0]
        assert waits[5] == pytest.approx(1 / 3, abs=1e-6)
    finally:
        rate_limit.reset_default_clock()
        rate_limit._reset_all_buckets()


def test_retry_with_backoff_async_retries_then_succeeds():
    import asyncio

    rate_limit.set_default_clock(VirtualClock())
    rate_limit._reset_all_buckets()
    try:
        calls = {"n": 0}

        async def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _RateLimited()
            return "ok"

        async def run():
            return await rate_limit.retry_with_backoff_async(
                fn, bucket="meta",
                is_retryable=lambda e: isinstance(e, _RateLimited),
            )

        assert asyncio.run(run()) == "ok"
        assert calls["n"] == 3
    finally:
        rate_limit.reset_default_clock()
        rate_limit._reset_all_buckets()
