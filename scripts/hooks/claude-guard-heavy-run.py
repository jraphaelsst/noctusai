#!/usr/bin/env python3
"""PreToolUse hook (Bash) — refuse a heavy test/build run outside the hardware gate.

Sibling of `claude-guard-test-seams.py`, same contract: payload on stdin, a guard
module's verdict out, fail-CLOSED via `_guard_failclosed.run_guard`
(`[noc-guard:heavy-run]`). KB § PATTERNS/devops/hardware-admission-budget.md.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "heavy_run_guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("noc_heavy_run_guard", GUARD)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {GUARD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _judge(payload: dict) -> dict | None:
    return _load_guard().decide(payload)


def main() -> int:
    return run_guard("heavy-run", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
