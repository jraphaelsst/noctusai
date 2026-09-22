"""Startup maintenance steps are independent (2026-09-21, live run): a
transient PostgREST error in one step used to skip every step after it —
including the slot sweep the isolation guarantee depends on."""
from __future__ import annotations

import asyncio

from app.main import _startup_step


def _run(coro):
    return asyncio.run(coro)


def test_a_transient_failure_is_retried_and_succeeds():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("PostgREST hiccup")

    failures: list[str] = []
    _run(_startup_step("flaky", flaky, failures, delays=(0.0, 0.0, 0.0)))
    assert calls["n"] == 3 and failures == []


def test_a_persistent_failure_is_recorded_and_does_not_block_later_steps():
    ran: list[str] = []

    async def broken():
        ran.append("broken")
        raise RuntimeError("down")

    async def later():
        ran.append("later")

    async def both():
        failures: list[str] = []
        await _startup_step("broken", broken, failures, delays=(0.0,))
        await _startup_step("later", later, failures, delays=(0.0,))
        return failures

    failures = _run(both())
    assert failures == ["broken"]
    assert ran == ["broken", "broken", "later"]  # 1 try + 1 retry, then the next step still ran
