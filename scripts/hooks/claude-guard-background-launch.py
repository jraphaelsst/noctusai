#!/usr/bin/env python3
"""PreToolUse hook (Bash) - refuse an open-ended background launch (run_in_background=true).

Same contract as `claude-guard-heavy-run.py`: payload on stdin, the decision module's verdict out,
fail-CLOSED via `_guard_failclosed.run_guard` (`[noc-guard:background-launch]`).

ENFORCING since 2026-11-14 (owner decision ended the warn-only soak early; `bg_launch_guard.ENFORCE_FROM`).
Shadow remains available via `NOC_BG_LAUNCH_MODE=shadow`: before ENFORCE_FROM a launch that
would be refused is ALLOWED, logged as a `warn` event in `guard-events.ndjson` (read by
`noctus.dev.gate_alignment walls`) and told to the agent on stderr, so the 7 days refine the tool with
real data. From that date it denies. `NOC_BG_LAUNCH_MODE=enforce|shadow` overrides the date.
KB § PATTERNS/common/background-agent-lifecycle.md.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, log_event, run_guard  # noqa: E402

# Cheap prefilter for FOREGROUND calls (the hook matches every Bash call): only a command that could contain a
# never-ending shape reaches the module load, i.e. one with a loop keyword (inline, in a `-c` string, in `$(...)`)
# or one that invokes a script the judge opens (`x.sh`, `x.py`, `./x`). Superset of what `_bg_shell` can report.
_FG_PREFILTER = re.compile(r"\b(?:while|until|tail|watch)\b|--watch|\.(?:sh|bash|zsh|py)\b|(?:^|[\s;&|(])\./")

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "bg_launch_guard.py"


def _judge(payload: dict) -> dict | None:
    guard = load_module(GUARD)
    verdict = guard.decide(payload)
    if verdict is None:
        return None
    if guard.mode() != "enforce":
        why = verdict.get("reason") or f"would rewrite: {verdict.get('context', '')}"
        log_event("background-launch", "warn", why, payload,
                  extra={"kind": "guard", "owner": "tooling-engineer", "source": "shadow"})
        print(f"[noc-guard:background-launch] WARNING (shadow until {guard.ENFORCE_FROM}, then enforced): {why}",
              file=sys.stderr)
        return None
    return verdict


def _shadow_timeout_ok(_payload: dict) -> bool:
    """A TIMEOUT during the warn-only soak must not deny: in shadow the guard only observes."""
    return load_module(GUARD).mode() != "enforce"


def main() -> int:
    raw = sys.stdin.read()
    # Fast path (peer review 2026-11-14, load ~200): this hook matches EVERY Bash call, so a call that is
    # not a background launch returns before any module load, and cannot time out into a deny.
    try:
        quick = json.loads(raw) if raw.strip() else None
    except ValueError:
        quick = None  # malformed: let run_guard refuse it, fail-closed
    if isinstance(quick, dict):
        ti = quick.get("tool_input") or {}
        if quick.get("tool_name") != "Bash":
            return 0
        if not ti.get("run_in_background") and not _FG_PREFILTER.search(str(ti.get("command") or "")):
            return 0
    return run_guard("background-launch", _judge, stdin=io.StringIO(raw), fail_open_when=_shadow_timeout_ok)


if __name__ == "__main__":
    raise SystemExit(main())
