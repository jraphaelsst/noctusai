#!/usr/bin/env python3
"""PreToolUse hook (Bash) - refuse an open-ended background launch (run_in_background=true).

Same contract as `claude-guard-heavy-run.py`: payload on stdin, the decision module's verdict out,
fail-CLOSED via `_guard_failclosed.run_guard` (`[noc-guard:background-launch]`).

WARN-FIRST SHADOW (owner, 2026-11-14): until `bg_launch_guard.ENFORCE_FROM` (2026-11-21) a launch that
would be refused is ALLOWED, logged as a `warn` event in `guard-events.ndjson` (read by
`noctus.dev.gate_alignment walls`) and told to the agent on stderr, so the 7 days refine the tool with
real data. From that date it denies. `NOC_BG_LAUNCH_MODE=enforce|shadow` overrides the date.
KB § PATTERNS/common/background-agent-lifecycle.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, log_event, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "bg_launch_guard.py"


def _judge(payload: dict) -> dict | None:
    guard = load_module(GUARD)
    verdict = guard.decide(payload)
    if verdict is None:
        return None
    if guard.mode() != "enforce":
        log_event("background-launch", "warn", verdict["reason"], payload,
                  extra={"kind": "guard", "owner": "tooling-engineer", "source": "shadow"})
        print(f"[noc-guard:background-launch] WARNING (shadow until {guard.ENFORCE_FROM}, then refused): "
              f"{verdict['reason']}", file=sys.stderr)
        return None
    return verdict


def main() -> int:
    return run_guard("background-launch", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
