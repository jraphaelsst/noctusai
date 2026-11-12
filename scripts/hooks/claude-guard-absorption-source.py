#!/usr/bin/env python3
"""PreToolUse hook (matcher `Edit|Write|MultiEdit|NotebookEdit|Bash`) — refuse a WRITE under `products/<source>/` when
`<source>` is an ABSORPTION SOURCE and the worktree branch is not `absorb-<source>-*` (Phase 5a, owner rule 2026-11-12:
"erp-imob is to be absorbed, so no changes or refinements to it"). Logic + registry derivation:
`mcp/noctusai/tools/noctus/dev/absorption_sources.py` (stdlib-only; the source list is DERIVED from the absorptions
ledger, never hand-kept here). The refusal names the canon to work in.

Fails CLOSED like every guard (`[noc-guard:absorption-source]`) via the shared `_guard_failclosed.run_guard`; a ledger that
cannot be read at all is a refusal only when the call targets a `products/` path (a registry we could not read must not
read as "no sources"). Every deny is a gate-fire row in `.claude/cache/guard-events.ndjson` (F6, read by
`noctus.dev.gate_alignment walls`). The F3 commit keeper `check_absorption_source_frozen` is the backstop for a Bash write
whose target the shell parser could not resolve (measure, don't predict).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev"
NAME = "absorption-source"
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _judge(payload: dict) -> dict | None:
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool not in _WRITE_TOOLS and tool != "Bash":
        return None
    cwd = payload.get("cwd") or os.getcwd()
    mod = load_module(DEV / "absorption_sources.py")
    guard = None
    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        if "products/" not in command:
            return None  # cheap pre-filter: nothing under products/ is named, nothing to judge
        guard = load_module(DEV / "primary_write_guard.py")
        command = guard.expand_literal_assignments(command)
        tool_input = {**tool_input, "command": command}
    elif "products/" not in str(tool_input.get("file_path") or tool_input.get("notebook_path") or ""):
        return None
    sources, err = mod.load_sources(REPO_ROOT)
    if err:
        return {"reason": f"cannot derive the absorption-source list ({err}); refusing a write that names products/ "
                          "(fail closed). Fetch origin/ledgers or restore project-history/absorptions.ndjson - do not bypass."}
    verdict = mod.decide(
        tool, tool_input, cwd, sources,
        bash_targets=(guard.bash_write_targets if guard else None),
        resolve=(guard._resolve if guard else None),
    )
    return verdict  # run_guard writes the deny row (the F6 gate-fire telemetry) - logging here would double it


def main() -> int:
    return run_guard(NAME, _judge)


if __name__ == "__main__":
    raise SystemExit(main())
