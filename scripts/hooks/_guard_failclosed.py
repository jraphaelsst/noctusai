"""Shared fail-CLOSED runner for every Claude Code PreToolUse guard script.

Claude Code treats a command hook that crashes (non-zero exit other than 2) or
exceeds its `timeout` as a NON-blocking error and lets the tool call run — so a
guard that merely "fails open, loudly" silently stops guarding (CLAUDE.md §1
"No silent errors", "Gate<->methodology sync"). This module makes the guard
scripts refuse instead of waving through:

* any unexpected exception          -> deny, naming guard + exception class
* internal deadline (8 s < the 10 s settings timeout) -> deny, "timed out"
* empty / malformed / non-object stdin -> deny (cannot judge => refuse)

Every deny reason starts with the stable marker `[noc-guard:<name>]` so a UI
layer can attribute it. The guards' own escape hatches
(`NOCTUS_ALLOW_PRIMARY_WRITE`, `NOCTUS_ALLOW_SELF_PATCH`) live INSIDE the
judge functions and are untouched.

Stdlib-only (runs under the hook's bare `python3`). The deadline uses SIGALRM
(main thread, POSIX); where unavailable the settings timeout is the only net.
KB § PATTERNS/common/self-branching-mode.md §11.
"""
from __future__ import annotations

import json
import signal
import sys
from collections.abc import Callable
from typing import Any, TextIO

DEFAULT_DEADLINE_S = 8.0  # must stay below the `timeout` in .claude/settings.json (10)


class GuardTimeout(BaseException):
    """BaseException on purpose: a guard's inner `except Exception` must not swallow it."""


def marker(name: str) -> str:
    return f"[noc-guard:{name}]"


def deny_json(name: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{marker(name)} {reason}",
        }
    }


def run_guard(
    name: str,
    judge: Callable[[dict[str, Any]], dict[str, Any] | None],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> int:
    """Read the hook payload, call `judge(payload)`, emit a deny on a verdict OR on any failure.

    `judge` returns None to allow, or a dict with `reason` to deny. Always returns 0:
    a deny is a JSON decision on stdout, never a non-zero exit (which would fail open).
    """
    stdin = stdin if stdin is not None else sys.stdin
    out = stdout if stdout is not None else sys.stdout

    def _emit(reason: str) -> int:
        json.dump(deny_json(name, reason), out)
        return 0

    try:
        raw = stdin.read()
        payload = json.loads(raw) if raw.strip() else None
    except Exception as exc:  # noqa: BLE001 — unreadable stdin => refuse
        return _emit(
            f"could not read the hook payload ({type(exc).__name__}) — guard failed closed; "
            "fix the guard, do not bypass."
        )
    if not isinstance(payload, dict):
        return _emit(
            "empty or malformed hook payload — cannot judge, so refusing (guard failed closed); "
            "fix the caller/guard, do not bypass."
        )

    def _on_alarm(_signum, _frame):
        raise GuardTimeout()

    armed = hasattr(signal, "setitimer")
    previous = None
    try:
        if armed:
            previous = signal.signal(signal.SIGALRM, _on_alarm)
            signal.setitimer(signal.ITIMER_REAL, deadline_s)
        verdict = judge(payload)
    except GuardTimeout:
        return _emit(
            f"guard timed out (failed closed) after {deadline_s:g}s; fix the guard, do not bypass."
        )
    except Exception as exc:  # noqa: BLE001 — the whole point: crash => deny, never allow
        print(f"claude-guard-{name}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return _emit(
            f"guard crashed ({type(exc).__name__}) — guard failed closed; "
            "fix the guard, do not bypass."
        )
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if previous is not None:
                signal.signal(signal.SIGALRM, previous)

    if verdict is None:
        return 0
    return _emit(str(verdict["reason"]))
