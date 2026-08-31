"""Regression guard: no `noctus.dev.*` (or any) MCP tool name is registered twice.

Root cause (2026-08-31): `build_server()` was logging, every single build:

    Tool already exists: noctus.dev.agent_context
    Tool already exists: noctus.dev.dispatch_budget_summary

`FastMCP.tool(name=...)` keeps the FIRST registration and only WARNS on a
collision — the second call's implementation never lands in the tool
registry, so it is dead code that reads as live (a silent fork, exactly the
shape CLAUDE.md §1 forbids). Traced to two genuine same-name collisions:

  - `noctus.dev.agent_context`: `agent_context.py` (per-agent compact
    bundle lookup, wins — registered first in `register_all`) vs
    `context.py` (zero-arg full-platform bootstrap, was dead). NOT
    behaviourally equivalent, so `context.py`'s tool was renamed to
    `noctus.dev.platform_bootstrap_context` rather than deleted — its
    capability survives under an honest, non-colliding name.
  - `noctus.dev.dispatch_budget_summary`: `dispatch_budget.py`
    ((agent, model, window_days) token-sum aggregation, wins) vs
    `dispatch_token_log.py` ((agent, since) outcome/duration aggregation
    over a DIFFERENT entry schema in the SAME ledger file, was dead).
    Renamed to `noctus.dev.dispatch_completion_summary`.

This test builds the REAL server (`server.build_server()`) with a recording
wrapper around `FastMCP.tool` so it observes every `name=` ever passed to
`.tool(...)` — including calls that FastMCP itself would silently accept as
a duplicate — and fails loudly if any name is declared more than once. A
warning nobody reads is not a gate; this is.
"""
from __future__ import annotations

from collections import Counter


def _build_server_recording_tool_names(monkeypatch) -> list[str]:
    """Build the real server while recording every `name=` passed to
    `FastMCP.tool(...)`, INCLUDING calls FastMCP would silently dedupe.

    Patches the FastMCP CLASS method (not the `server` instance) before
    `server.build_server()` runs. `build_server()` itself does
    `_orig_tool = server.tool` (an instance lookup that resolves to a BOUND
    method of whatever the class currently defines) and then wraps THAT —
    so patching the class first means every tool registration, including
    ones already wrapped a second time by `build_server`'s own
    `structured_output` shim, still passes through this recorder.
    """
    from mcp.server.fastmcp import FastMCP

    seen: list[str] = []
    orig_tool = FastMCP.tool

    def _recording_tool(self, *args, **kwargs):
        name = kwargs.get("name")
        if name is None and args:
            name = args[0]
        if name is not None:
            seen.append(name)
        return orig_tool(self, *args, **kwargs)

    monkeypatch.setattr(FastMCP, "tool", _recording_tool)

    from server import build_server
    build_server()
    return seen


def test_no_tool_name_registered_twice(monkeypatch):
    seen = _build_server_recording_tool_names(monkeypatch)
    counts = Counter(seen)
    dupes = {name: n for name, n in counts.items() if n > 1}
    assert not dupes, (
        f"tool name(s) declared more than once (FastMCP silently keeps the "
        f"first and drops the rest as dead code): {dupes}"
    )


def test_agent_context_collision_resolved_by_rename(monkeypatch):
    """Locks in the specific fix: both former colliding names now resolve
    to exactly one registration each, and the previously-dead capability
    (`context.py`'s zero-arg bootstrap) is reachable under its new name —
    proving the rename didn't just hide the collision by deleting it.
    """
    seen = _build_server_recording_tool_names(monkeypatch)
    counts = Counter(seen)

    assert counts["noctus.dev.agent_context"] == 1
    assert counts["noctus.dev.platform_bootstrap_context"] == 1
    assert counts["noctus.dev.dispatch_budget_summary"] == 1
    assert counts["noctus.dev.dispatch_completion_summary"] == 1
