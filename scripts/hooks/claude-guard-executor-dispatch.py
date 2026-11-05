#!/usr/bin/env python3
"""PreToolUse hook (matcher `Agent|Task`) — refuse an EXECUTOR subagent dispatch
that has no worktree. Logic: `mcp/noctusai/tools/noctus/dev/executor_dispatch_guard.py`.
Fails CLOSED through the shared `_guard_failclosed.run_guard`
(`[noc-guard:executor-dispatch]`). KB § PATTERNS/common/self-branching-mode.md §11.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "executor_dispatch_guard.py"


def _load_guard():
    return load_module(GUARD)


def _roots() -> list[Path]:
    """This tree, plus the primary checkout when running from `.claude/worktrees/<slug>`
    (worktrees are siblings under the PRIMARY's `.claude/worktrees/`)."""
    roots = [REPO_ROOT]
    if REPO_ROOT.parent.name == "worktrees" and REPO_ROOT.parent.parent.name == ".claude":
        roots.append(REPO_ROOT.parent.parent.parent)
    return roots


def _judge(payload: dict) -> dict | None:
    guard = _load_guard()
    return guard.decide(
        payload.get("tool_name", ""),
        payload.get("tool_input") or {},
        REPO_ROOT / ".claude" / "agents",
        _roots(),
    )


def main() -> int:
    return run_guard("executor-dispatch", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
