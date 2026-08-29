"""A synchronous tool must NOT block the MCP server's event loop.

🔴 THE INCIDENT THIS PINS (2026-08-27, recurring)
------------------------------------------------
The `noctusai` MCP server kept dying mid-session, always on deploy-shaped
sessions. Root cause: FastMCP dispatches a sync tool INLINE on the asyncio loop
(`func_metadata.call_fn_with_arg_validation`: `if fn_is_async: await fn() else:
fn()`), and this server speaks JSON-RPC over **stdio** on that same loop.

173 of 185 tool modules are synchronous, and the slowest are the ones a deploy
calls: `_vps_ssh.run_remote` throttles ≥3s between SSH attempts (fail2ban
avoidance) and `deploy_image` polls health for up to 120s. One call held the
loop for minutes; every call queued behind it died with "Connection closed"
(observed: `vps_ps`, `deploy_verify` ×2, `spa_smoke`, all behind a running
`deploy_image`).

`server.offload_blocking` moves sync tools to a worker thread at the single
`server.tool` seam. These tests pin the three properties that fix depends on.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import offload_blocking  # noqa: E402


def test_sync_tool_becomes_a_coroutine_function():
    """FastMCP decides inline-vs-await by `iscoroutinefunction`, so the wrapper
    only takes effect if it actually reports as one."""

    def tool(a: int) -> int:
        return a + 1

    wrapped = offload_blocking(tool)
    assert inspect.iscoroutinefunction(wrapped)


def test_an_already_async_tool_is_passed_through_untouched():
    """The 12 async tools keep their own concurrency — no double-wrapping."""

    async def tool(a: int) -> int:
        return a + 1

    assert offload_blocking(tool) is tool


def test_the_argument_signature_SURVIVES_the_wrap():
    """🔴 Load-bearing, not cosmetic. FastMCP builds each tool's JSON schema
    with `inspect.signature`, which follows `__wrapped__`. Without
    `functools.wraps` every tool would register as `(*args, **kwargs)` and lose
    its parameters — the server would come up with 185 argument-less tools."""

    def tool(product: str, confirm: bool = False) -> dict:
        return {"product": product, "confirm": confirm}

    wrapped = offload_blocking(tool)
    params = inspect.signature(wrapped).parameters
    assert list(params) == ["product", "confirm"]
    assert params["confirm"].default is False
    assert wrapped.__name__ == "tool"


def test_it_runs_OFF_the_event_loop_thread():
    """The property the whole fix exists for."""

    loop_thread: list[int] = []
    tool_thread: list[int] = []

    def tool() -> str:
        tool_thread.append(threading.get_ident())
        return "ok"

    wrapped = offload_blocking(tool)

    async def main():
        loop_thread.append(threading.get_ident())
        return await wrapped()

    assert asyncio.run(main()) == "ok"
    assert tool_thread and loop_thread
    assert tool_thread[0] != loop_thread[0], (
        "the sync tool ran on the event-loop thread — it would block stdio"
    )


def test_a_SLOW_sync_tool_does_not_stall_a_concurrent_task():
    """The regression in its observed form: work queued behind a slow tool must
    still be serviced. Pre-fix this asserted false — the concurrent task could
    not run until the blocking call returned.

    Uses a deliberately small sleep: the property is 'progress happens during',
    not 'how long it takes'.
    """
    BLOCK = 0.40

    def slow_tool() -> str:
        time.sleep(BLOCK)  # stands in for a throttled SSH round-trip
        return "slow-done"

    wrapped = offload_blocking(slow_tool)
    ticks = 0

    async def heartbeat():
        """Stands in for the stdio reader answering other JSON-RPC traffic."""
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    async def main():
        beat = asyncio.create_task(heartbeat())
        result = await wrapped()
        beat.cancel()
        return result

    assert asyncio.run(main()) == "slow-done"
    assert ticks >= 5, (
        f"only {ticks} heartbeats during a {BLOCK}s tool — the loop was blocked, "
        "which is exactly the 'Connection closed' failure this fixes"
    )


def test_exceptions_propagate_rather_than_being_swallowed():
    """No silent errors: a failing tool must still fail, not resolve to None."""

    def tool() -> None:
        raise ValueError("boom")

    wrapped = offload_blocking(tool)

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(wrapped())
