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

🔴 A SECOND, DISTINCT INCIDENT THIS FILE ALSO PINS (2026-08-31, recurring)
---------------------------------------------------------------------
The server died AGAIN on 2026-08-31 — NOT a deploy session this time: 8
concurrent subagents + the orchestrator, one mid-`task_branch
action=integrate` (whose `cache_settle` leg can trigger a noc-graph rebuild —
39,450 nodes / 62,815 edges, ~13-20s pure-Python AST-walk + clustering),
several others independently triggering cache refreshes in the same window.

The classes below prove the gap directly: `offload_blocking` moves a sync
tool off the event-loop THREAD, which fixes an I/O-bound blocker (blocking on
a socket / `time.sleep` releases the GIL) but does nothing for a CPU-bound
one — a pure-Python loop holds the GIL for nearly its whole duration, and
under SUSTAINED CONCURRENT load that starves the loop's own ability to
service stdio (which, per the real `mcp.server.stdio` transport, ALSO hops
through `anyio.to_thread.run_sync` for every read/write/flush — same
worker-thread pool, same GIL). `TestSustainedConcurrentLoadGilContrast`
measures this directly: an I/O-bound blocker stays responsive under load
that leaves a CPU-bound blocker catastrophically stalled.

The actual fix is NOT another change to `offload_blocking` (a blanket
"subprocess every sync tool" would tax ~170 cheap/IO-bound tools for zero
benefit) — it is a TARGETED gate in `noc_graph_cache.refresh()` (the one
identified genuinely-CPU-heavy operation): a module-level `IN_MCP_SERVER`
flag, set only by `server.run()`, that delegates an actually-needed rebuild
to a subprocess instead of running it in-process.
`TestNocGraphRebuildIsolatedFromEventLoop` pins that gate.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import sqlite3
import subprocess as _subprocess_module
import sys
import threading
import time
from io import TextIOWrapper
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anyio
import anyio.to_thread

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


# ═══════════════════════════════════════════════════════════════════════════
# GIL-contrast harness (2026-08-31 recurrence)
# ═══════════════════════════════════════════════════════════════════════════
#
# Reproduces the REAL transport plumbing: `mcp/server/stdio.py`'s
# `stdin_reader`/`stdout_writer` read/write via `anyio.wrap_file`, whose
# `readline`/`write`/`flush` all hop through `anyio.to_thread.run_sync` — the
# SAME default `CapacityLimiter`-backed thread pool `offload_blocking` uses
# for tool calls. So a concurrent CPU-bound tool offload competes for GIL
# time against the transport's own read/write hops, not just against other
# tool calls. This harness measures that directly over a REAL os.pipe(),
# with a writer thread standing in for "the client sending JSON-RPC lines".


def _cpu_bound_work(iterations: int) -> int:
    """Pure-Python busy loop — stands in for an AST walk / dict-heavy graph
    build. Holds the GIL for virtually its entire duration (released only at
    CPython's ~5ms switch-interval boundaries)."""
    total = 0
    for i in range(iterations):
        total += i * i
        s = str(i)
        d = {s: i}
        total += len(d)
    return total


def _calibrate_iterations(target_seconds: float) -> int:
    t0 = time.monotonic()
    _cpu_bound_work(1_000_000)
    cal = time.monotonic() - t0
    return max(1, int(1_000_000 * (target_seconds / cal)))


async def _measure_pipe_latency_under_offloaded_load(
    blocking_fn, n_tasks: int, seconds_each: float, n_msgs: int, interval: float,
) -> list[float]:
    """Runs `n_tasks` concurrent `offload_blocking`-style thread-offloaded
    calls to `blocking_fn(seconds_each)` while a REAL os.pipe (wrapped via
    `anyio.wrap_file`, exactly like `mcp/server/stdio.py`) streams timestamped
    lines from an independent OS thread. Returns the read-latency (seconds)
    of every line, measured wall-clock (write time -> read time)."""
    import os

    r_fd, w_fd = os.pipe()
    r_file = TextIOWrapper(os.fdopen(r_fd, "rb"), encoding="utf-8")
    w_file = TextIOWrapper(os.fdopen(w_fd, "wb"), encoding="utf-8")
    async_r = anyio.wrap_file(r_file)

    latencies: list[float] = []

    async def reader_loop():
        async for line in async_r:
            recv_t = time.monotonic()
            raw = line.strip()
            if raw == "STOP":
                break
            latencies.append(recv_t - float(raw))

    def writer_thread():
        for _ in range(n_msgs):
            w_file.write(f"{time.monotonic():.6f}\n")
            w_file.flush()
            time.sleep(interval)
        w_file.write("STOP\n")
        w_file.flush()

    async with anyio.create_task_group() as tg:
        tg.start_soon(reader_loop)
        wt = threading.Thread(target=writer_thread, daemon=True)
        wt.start()
        async with anyio.create_task_group() as load_tg:
            for _ in range(n_tasks):
                load_tg.start_soon(
                    functools.partial(
                        anyio.to_thread.run_sync,
                        functools.partial(blocking_fn, seconds_each),
                    )
                )
        await anyio.to_thread.run_sync(wt.join)

    return latencies


class TestSustainedConcurrentLoadGilContrast:
    """The direct experiment the 2026-08-31 investigation asked for: hold the
    load SHAPE identical (same offload wrapper, same concurrency, same
    message cadence) and vary only whether the blocking call is I/O-bound
    (releases the GIL) or CPU-bound (holds it). If sleep stays fine and
    CPU-bound stalls, the GIL hypothesis holds specifically — that is what
    both tests below found."""

    N_TASKS = 4
    SECONDS_EACH = 0.6
    N_MSGS = 120
    INTERVAL = 0.02

    def _measure_io_control(self) -> list[float]:
        def io_bound(duration: float) -> None:
            time.sleep(duration)

        return anyio.run(
            _measure_pipe_latency_under_offloaded_load,
            io_bound, self.N_TASKS, self.SECONDS_EACH, self.N_MSGS, self.INTERVAL,
        )

    def _measure_cpu_experiment(self) -> list[float]:
        iterations = _calibrate_iterations(self.SECONDS_EACH)

        def cpu_bound(_duration_unused: float) -> int:
            return _cpu_bound_work(iterations)

        return anyio.run(
            _measure_pipe_latency_under_offloaded_load,
            cpu_bound, self.N_TASKS, self.SECONDS_EACH, self.N_MSGS, self.INTERVAL,
        )

    def test_sustained_io_bound_concurrent_load_stays_responsive(self):
        """CONTROL — `time.sleep` releases the GIL while blocked, so
        `offload_blocking`'s thread-offload is sufficient here (this is
        exactly the 2026-08-27 deploy-session shape the prior fix targeted)."""
        latencies = self._measure_io_control()
        assert len(latencies) >= self.N_MSGS * 0.9
        mx = max(latencies)
        assert mx < 0.1, (
            f"I/O-bound control should stay responsive under concurrent load "
            f"(max latency {mx*1000:.0f}ms) — if this fails, the harness "
            f"itself is broken, not the mechanism under test"
        )

    def test_sustained_cpu_bound_concurrent_load_stalls_the_transport_via_offload_blocking_alone(self):
        """🔴 EXPERIMENT — the 2026-08-31 mechanism, permanently characterized.

        Pure-Python CPU-bound work holds the GIL for virtually its whole
        duration. `offload_blocking` (the 2026-08-27 fix) moves it to a
        worker THREAD, not a separate process — so under sustained
        concurrent load it still starves the event-loop thread's chances to
        service stdio (which itself hops through the SAME thread pool per
        `mcp/server/stdio.py`). This is a permanent characterization test of
        `offload_blocking`'s known limitation — it stays true regardless of
        the `noc_graph_cache` fix below, which sidesteps the limitation for
        the one identified CPU-heavy tool by NOT running that work through
        `offload_blocking`'s thread pool at all (subprocess instead). If a
        FUTURE tool does genuinely CPU-heavy work through plain
        `offload_blocking`, this test documents exactly why that recurs.

        Measures BOTH sides itself (rather than depending on execution order
        against the sibling control test — pytest-randomly reorders tests)
        so the relative assertion below is always exercised.
        """
        cpu_latencies = self._measure_cpu_experiment()
        assert len(cpu_latencies) >= self.N_MSGS * 0.9
        mx = max(cpu_latencies)
        assert mx > 0.15, (
            f"expected the CPU-bound load to visibly stall the transport "
            f"(max latency only {mx*1000:.0f}ms) — either the harness "
            f"changed or CPython's GIL behavior did; re-measure before "
            f"trusting this test either way"
        )
        io_control_max = max(self._measure_io_control())
        assert mx > io_control_max * 5, (
            f"CPU-bound max ({mx*1000:.0f}ms) should be dramatically worse "
            f"than the I/O-bound control ({io_control_max*1000:.0f}ms) under "
            f"the IDENTICAL load shape — that gap IS the GIL hypothesis; a "
            f"small gap would mean something else is at play"
        )


class TestNocGraphRebuildIsolatedFromEventLoop:
    """🔴 THE ACTUAL FIX, PINNED. `noc_graph_cache.refresh()`, when a rebuild
    is genuinely needed AND `IN_MCP_SERVER` is True, must NOT run the
    CPU-heavy `build_graph` pass in-process — it must delegate to a
    subprocess (`_refresh_via_cli_subprocess`).

    MUST FAIL against pre-fix code (no `IN_MCP_SERVER` gate exists, so
    `refresh()` always runs `build_graph` in-process regardless of context)
    and PASS after (verified via git-stash re-run — see the delivery note)."""

    @staticmethod
    def _seed_cache_meta(cache_file: Path) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.noctus.dev import noc_graph_cache as ngc

        conn = sqlite3.connect(str(cache_file))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(ngc._SCHEMA_SQL)
        for k, v in {
            "aggregate_source_sha": "NEW_SHA_AFTER_SUBPROCESS_REBUILD",
            "node_count": "39450",
            "edge_count": "62815",
            "scope": "repo",
            "build_seconds": "14.2",
            "rebuild": "full",
        }.items():
            conn.execute(
                "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
        conn.close()

    def test_rebuild_delegates_to_subprocess_when_in_mcp_server(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.noctus.dev import noc_graph_cache as ngc

        cache_file = tmp_path / "noc-graph.sqlite"

        # Force the "genuinely stale, a rebuild WOULD run" branch.
        monkeypatch.setattr(ngc, "compute_source_sha", lambda root=None: "LIVE_SHA")
        monkeypatch.setattr(ngc, "get_cached_source_sha", lambda root=None: "STALE_SHA")
        monkeypatch.setattr(ngc, "cache_path", lambda repo_root=None: cache_file)
        monkeypatch.setattr(ngc, "IN_MCP_SERVER", True)

        build_graph_calls: list[object] = []

        def _build_graph_stub(*args, **kwargs):
            build_graph_calls.append((args, kwargs))
            raise AssertionError(
                "build_graph ran IN-PROCESS despite IN_MCP_SERVER=True — the "
                "GIL-starvation guard did not engage"
            )

        import noctusai_lib.graph as _real_graph_module
        monkeypatch.setattr(_real_graph_module, "build_graph", _build_graph_stub)

        subprocess_calls: list[dict] = []

        def _fake_subprocess_run(argv, **kwargs):
            subprocess_calls.append({"argv": argv, "kwargs": kwargs})
            self._seed_cache_meta(cache_file)
            return _subprocess_module.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        monkeypatch.setattr(ngc.subprocess, "run", _fake_subprocess_run)

        result = ngc.refresh(force=False, repo_root=tmp_path)

        assert not build_graph_calls, (
            "the CPU-heavy build_graph pass ran on the MCP server's own "
            "worker thread — this is EXACTLY the mechanism that starves the "
            "event loop under concurrent load (see "
            "TestSustainedConcurrentLoadGilContrast)"
        )
        assert subprocess_calls, "expected the rebuild to delegate to a subprocess"
        argv = subprocess_calls[0]["argv"]
        assert "--refresh-noc-graph" in argv
        assert result["ok"] is True
        assert result["source_sha"] == "NEW_SHA_AFTER_SUBPROCESS_REBUILD"
        assert result["nodes"] == 39450
        assert result["edges"] == 62815

    def test_in_process_path_is_UNCHANGED_outside_the_server(self, monkeypatch):
        """Sibling assertion: `IN_MCP_SERVER` defaults False, so CLI / pytest
        / ad-hoc scripts keep the exact pre-fix in-process behavior — the fix
        is additive, not a behavior change for non-server callers."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.noctus.dev import noc_graph_cache as ngc

        assert ngc.IN_MCP_SERVER is False
