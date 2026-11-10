#!/usr/bin/env python3
"""PreToolUse hook (matcher `Read|Grep|Glob|Bash`) — blind-recorder read guard for open council sessions.
Logic: `mcp/noctusai/tools/noctus/dev/council_read_guard.py` (council must-fix J, 2026-11-09).

While a council session has no verdict row, direct reads of its `project-history/council/**` file are denied for every
caller once enforcing; the ledger tool itself is untouched. WARN-FIRST SHADOW by default (new-gate rule, >=7 days); env
`NOC_COUNCIL_READ_MODE=enforce` (or `council_read_guard.MODE = "enforce"`) denies. Fails CLOSED on a crash /
bad stdin like every guard (`[noc-guard:council-read]`) via the shared `_guard_failclosed.run_guard`; every deny is a
row in `.claude/cache/guard-events.ndjson` (read by `noctus.dev.gate_alignment walls`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, log_event, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "council_read_guard.py"
NAME = "council-read"


def _roots() -> list[Path]:
    roots = [REPO_ROOT]
    if REPO_ROOT.parent.name == "worktrees" and REPO_ROOT.parent.parent.name == ".claude":
        roots.append(REPO_ROOT.parent.parent.parent)
    return roots


def _judge(payload: dict) -> dict | None:
    guard = load_module(GUARD)
    v = guard.decide(payload.get("tool_name", ""), payload.get("tool_input") or {}, _roots())
    if v is None:
        return None
    if (os.environ.get("NOC_COUNCIL_READ_MODE") or guard.MODE) != "enforce":
        log_event(NAME, "warn", v["reason"], payload,
                  extra={"kind": "guard", "owner": "tooling-engineer", "source": "shadow"})
        return None
    return v


def main() -> int:
    return run_guard(NAME, _judge)


if __name__ == "__main__":
    raise SystemExit(main())
