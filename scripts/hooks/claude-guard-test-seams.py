#!/usr/bin/env python3
"""PreToolUse hook — refuse a test-file write that patches our own code.

Sibling of `claude-guard-primary-write.py`, same contract and same posture:
read the tool payload on stdin, ask a guard module for a verdict, and emit a
`permissionDecision: deny` when it returns one.

It is a SECOND hook entry rather than a branch inside the existing guard so
that branch-isolation and test-seam enforcement stay independently readable
and independently testable — a failure in one must not disable the other.

Fails CLOSED (crash / 8 s deadline / bad stdin => deny with the
`[noc-guard:test-seams]` marker) via the shared `_guard_failclosed.run_guard`:
Claude Code lets a crashed hook's tool call run, so failing open silently
stops guarding. Also denies the auth-boundary false-green shape at write time.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "test_seam_guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("noc_test_seam_guard", GUARD)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {GUARD}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so annotations resolve through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _judge(payload: dict) -> dict | None:
    guard = _load_guard()
    return guard.decide(
        payload.get("tool_name", ""),
        payload.get("tool_input") or {},
        payload.get("cwd"),
    )


def main() -> int:
    return run_guard("test-seams", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
