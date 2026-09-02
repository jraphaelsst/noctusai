#!/usr/bin/env python3
"""PreToolUse hook — refuse a test-file write that patches our own code.

Sibling of `claude-guard-primary-write.py`, same contract and same posture:
read the tool payload on stdin, ask a guard module for a verdict, and emit a
`permissionDecision: deny` when it returns one.

It is a SECOND hook entry rather than a branch inside the existing guard so
that branch-isolation and test-seam enforcement stay independently readable
and independently testable — a failure in one must not disable the other.

Fails OPEN, deliberately: every Edit/Write in the repo passes through here,
so a guard that raises must not become a guard that blocks all work. The
commit-time `check_no_self_monkeypatch` keeper remains the backstop for
anything that leaks past.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    try:
        guard = _load_guard()
        verdict = guard.decide(
            payload.get("tool_name", ""),
            payload.get("tool_input") or {},
            payload.get("cwd"),
        )
    except Exception as exc:  # fail open — see the module docstring
        print(
            f"claude-guard-test-seams: guard unavailable ({exc}) — not blocking",
            file=sys.stderr,
        )
        return 0

    if verdict is None:
        return 0

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": verdict["reason"],
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
