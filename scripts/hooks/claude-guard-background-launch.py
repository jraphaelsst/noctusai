#!/usr/bin/env python3
"""PreToolUse hook (Bash) - refuse an open-ended background launch (run_in_background=true).

Same contract as `claude-guard-heavy-run.py`: payload on stdin, the decision module's verdict out,
fail-CLOSED via `_guard_failclosed.run_guard` (`[noc-guard:background-launch]`).
KB § PATTERNS/common/background-agent-lifecycle.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "bg_launch_guard.py"


def _judge(payload: dict) -> dict | None:
    return load_module(GUARD).decide(payload)


def main() -> int:
    return run_guard("background-launch", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
