#!/usr/bin/env python3
"""PreToolUse hook (Bash) — refuse a heavy test/build run outside the hardware gate.

Sibling of `claude-guard-test-seams.py`, same contract: payload on stdin, a guard
module's verdict out, fail-CLOSED via `_guard_failclosed.run_guard`
(`[noc-guard:heavy-run]`). KB § PATTERNS/devops/hardware-admission-budget.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "heavy_run_guard.py"


def _load_guard():
    return load_module(GUARD)


def _judge(payload: dict) -> dict | None:
    return _load_guard().decide(payload)


def main() -> int:
    return run_guard("heavy-run", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
