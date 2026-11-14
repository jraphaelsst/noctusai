"""Deny an OPEN-ENDED background launch from an agent's Bash call (`run_in_background=true`), BEFORE it runs.

WHY (owner, 2026-11-14): sessions left retry/poll loops and stuck test runs running for hours on an
8 GB machine. Design: background processes END THEMSELVES. Every background launch goes through
`scripts/bg_run.py` (purpose + an end condition the process checks itself, salvage on exit, tree-stop,
orphan check); a launch without it is refused here. No lifetime cap, no idle timer, anywhere.

DENIED (only when run_in_background is true):
  * an open-ended shape (`while`/`until` loop, `sleep N`, `tail -f`, `watch`, `gh run watch`, `--watch`)
    that is not wrapped;
  * a bare long-running command (pytest, vitest, playwright test, vite build, npm test|build,
    hw_admission run) that is not wrapped;
  * a wrapped launch missing `--purpose`, or missing `--done` (or `--long-lived`), or wrapping a loop
    without `--done-when`.
ALLOWED: the wrapper with a declared end condition; known infrastructure (the steward's merge-queue
watch and heartbeat loops, MCP servers, dev servers); anything that is not open-ended or long-running.
No escape hatch: the deny names the wrapper form to use. Warn-only (shadow) until ENFORCE_FROM.

DELIBERATE LIMITS: regex scanning, not a shell interpreter; a script that loops internally
(`./poll.sh`) is not seen. The session-end sweep (`session_end_sweep`) is the safety net.
KB § PATTERNS/common/background-agent-lifecycle.md
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import sys
from pathlib import Path
from typing import Any

_HOOKS = Path(__file__).resolve().parents[5] / "scripts" / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import _bg_process_core as core  # noqa: E402

KB_POINTER = "KB § PATTERNS/common/background-agent-lifecycle.md"

# Warn-first soak (owner, 2026-11-14): shadow for 7 days, used to refine the tool; denies from this date.
ENFORCE_FROM = "2026-11-21"


def mode(today: _dt.date | None = None) -> str:
    """'enforce' or 'shadow'. Env `NOC_BG_LAUNCH_MODE` overrides; otherwise the date decides."""
    forced = (os.environ.get("NOC_BG_LAUNCH_MODE") or "").strip().lower()
    if forced in {"enforce", "shadow"}:
        return forced
    today = today or _dt.date.today()
    return "enforce" if today >= _dt.date.fromisoformat(ENFORCE_FROM) else "shadow"
FORM = ('python3 scripts/bg_run.py --purpose "<what for>" --done "<what counts as done>" '
        '[--done-when "<shell check, exit 0 = done>"] -- <command>   '
        '(infrastructure that lives on purpose: --purpose "..." --long-lived -- <command>)')


def _deny(why: str) -> dict[str, str]:
    return {"reason": f"background launch refused: {why}. Background processes end themselves: launch it as {FORM}. {KB_POINTER}"}


def decide(payload: dict[str, Any]) -> dict[str, Any] | None:
    """None to allow; `{"reason": ...}` to deny. Only `Bash` with run_in_background is judged."""
    if (payload.get("tool_name") or "") != "Bash":
        return None
    ti = payload.get("tool_input") or {}
    if not ti.get("run_in_background"):
        return None
    command = ti.get("command") or ""
    if not command.strip():
        return None
    if core.infra_label(command):
        return None
    if re.search(r"\bbg_run\.py\b", command):
        if not re.search(r"--purpose\b", command):
            return _deny("the wrapper needs --purpose")
        long_lived = re.search(r"--long-lived\b", command) is not None
        if not long_lived and not re.search(r"--done\b(?!-)", command):
            return _deny("the wrapper needs --done (what counts as done) or --long-lived")
        if not long_lived and core.LOOP_RE.search(command) and not re.search(r"--done-when\b", command):
            return _deny("the wrapped command is an open-ended loop/poll with no --done-when check")
        return None
    if core.LOOP_RE.search(command):
        return _deny("open-ended loop/poll/follow with no declared done-condition")
    if core.LONG_RE.search(command):
        return _deny("a bare long-running command (test/build run) without the wrapper")
    return None
