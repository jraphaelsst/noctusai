#!/usr/bin/env python3
"""PreToolUse hook (matcher `Write|Edit|MultiEdit|NotebookEdit`) — keep a spec-writing advisor's Write inside its
spec/notes paths. Logic: `mcp/noctusai/tools/noctus/dev/advisor_write_guard.py` (owner decision D34, 2026-11-09).

WARN-FIRST SHADOW: while `advisor_write_guard.MODE == "shadow"` a violation is only logged (`warn` event in
`.claude/cache/guard-events.ndjson`, read by `noctus.dev.gate_alignment walls`) and the write proceeds; at `enforce` (the module constant, or env `NOC_ADVISOR_WRITE_MODE=enforce`) it
is denied. Fails CLOSED on a crash / bad stdin like every guard (`[noc-guard:advisor-write]`), via the shared
`_guard_failclosed.run_guard`. The main session carries no `agent_type`, so it is never judged.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, log_event, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "advisor_write_guard.py"
NAME = "advisor-write"


def _roots() -> list[Path]:
    roots = [REPO_ROOT]
    if REPO_ROOT.parent.name == "worktrees" and REPO_ROOT.parent.parent.name == ".claude":
        roots.append(REPO_ROOT.parent.parent.parent)
    return roots


def _judge(payload: dict) -> dict | None:
    guard = load_module(GUARD)
    v = guard.decide(payload.get("tool_name", ""), payload.get("tool_input") or {}, payload.get("agent_type"),
                     REPO_ROOT / ".claude" / "agents", _roots())
    if v is None:
        return None
    if (os.environ.get("NOC_ADVISOR_WRITE_MODE") or guard.MODE) != "enforce":
        log_event(NAME, "warn", v["reason"], payload,
                  extra={"kind": "guard", "owner": "tooling-engineer", "source": "shadow"})
        return None
    return v


def main() -> int:
    return run_guard(NAME, _judge)


if __name__ == "__main__":
    raise SystemExit(main())
