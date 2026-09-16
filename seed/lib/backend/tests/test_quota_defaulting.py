"""`DefaultingQuotaTracker` — per-tenant keys get a declared, finite default.

Network-free; `asyncio.run` (no pytest-asyncio), like `test_quota.py`."""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.quota import (
    DefaultingQuotaTracker,
    QuotaConfig,
    QuotaTracker,
    make_quota_tracker,
)
from noctusai_lib.integrations.redis import make_fake_redis_client

_DEFAULT = QuotaConfig(cap=2, window_seconds=3600)


@pytest.fixture(params=["memory", "redis"])
def inner(request) -> QuotaTracker:
    if request.param == "memory":
        return make_quota_tracker(kind="memory")
    return make_quota_tracker(kind="redis", redis_client=make_fake_redis_client())


def test_unseen_key_gets_the_default_cap(inner) -> None:
    tracker = DefaultingQuotaTracker(inner, default=_DEFAULT)
    assert isinstance(tracker, QuotaTracker)

    async def run():
        return [await tracker.consume(key="t:org-a") for _ in range(3)]

    first, second, third = asyncio.run(run())
    assert (first.allowed, second.allowed, third.allowed) == (True, True, False)


def test_keys_are_independent(inner) -> None:
    tracker = DefaultingQuotaTracker(inner, default=_DEFAULT)

    async def run():
        await tracker.consume(key="t:org-a", units=2)
        return await tracker.consume(key="t:org-b")

    assert asyncio.run(run()).allowed is True


def test_pre_registered_override_is_kept(inner) -> None:
    async def run():
        await inner.register_quota(key="t:vip", config=QuotaConfig(cap=5, window_seconds=3600))
        tracker = DefaultingQuotaTracker(inner, default=_DEFAULT)
        return await tracker.consume(key="t:vip", units=4)

    assert asyncio.run(run()).allowed is True


def test_peek_and_reset_register_lazily(inner) -> None:
    tracker = DefaultingQuotaTracker(inner, default=_DEFAULT)

    async def run():
        before = await tracker.peek(key="t:new")
        await tracker.consume(key="t:new", units=2)
        await tracker.reset(key="t:new")
        return before, await tracker.peek(key="t:new")

    before, after = asyncio.run(run())
    assert before.allowed is True and after.allowed is True


def test_negative_units_still_refused(inner) -> None:
    tracker = DefaultingQuotaTracker(inner, default=_DEFAULT)
    with pytest.raises(ValueError):
        asyncio.run(tracker.consume(key="t:x", units=-1))
