#!/usr/bin/env python3
"""PreToolUse hook -- refuse a NEW route / table that declares no access tier (default deny).

Sibling of `claude-guard-test-seams.py`, same contract: stdin payload -> guard module verdict -> `permissionDecision: deny`.
Fails CLOSED via `_guard_failclosed.run_guard` (`[noc-guard:access-tier]`). Backstop: the keepers
`check_access_tier_routes` / `check_access_tier_tables` at commit. KB § PATTERNS/security/access-tiers.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "access_tier_guard.py"


def _judge(payload: dict) -> dict | None:
    return load_module(GUARD).decide(payload.get("tool_name", ""), payload.get("tool_input") or {}, payload.get("cwd"))


def main() -> int:
    return run_guard("access-tier", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
