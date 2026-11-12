"""Shared fail-CLOSED runner for every Claude Code PreToolUse guard script.

Claude Code treats a command hook that crashes (non-zero exit other than 2) or
exceeds its `timeout` as a NON-blocking error and lets the tool call run — so a
guard that merely "fails open, loudly" silently stops guarding (CLAUDE.md §1
"No silent errors", "Gate<->methodology sync"). This module makes the guard
scripts refuse instead of waving through:

* any unexpected exception          -> deny, naming guard + exception class
* internal deadline (8 s < the 10 s settings timeout) -> deny, "timed out" --
  EXCEPT a provably READ-ONLY call (`fail_open_when`), which is allowed with a
  logged `allow-timeout` warning: a read cannot cause the harm the guard exists
  to stop, so blocking it on a slow probe is pure cost. Writes stay fail-closed.
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

import importlib.util
import json
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO

DEFAULT_DEADLINE_S = 8.0  # must stay below the `timeout` in .claude/settings.json (10)

# Guard-event log (2026-11-05, gates audit): every deny and every rewrite is
# appended here, one JSON line each. Before this, guard friction was only
# countable by grepping session transcripts. Read it with e.g.
#   jq -r .guard .claude/cache/guard-events.ndjson | sort | uniq -c
# Gitignored (.claude/cache/), machine-local, append-only. A failed write is
# reported on stderr and never changes the verdict.
def _primary_root() -> Path:
    """The PRIMARY checkout root, also when running inside a linked worktree.

    A worktree's `.git` is a FILE (`gitdir: <primary>/.git/worktrees/<n>`); a
    per-worktree log would scatter the firing history across trees and vanish
    with each worktree's cleanup, defeating the alignment report (2026-11-05).
    """
    here = Path(__file__).resolve().parents[2]
    dot_git = here / ".git"
    try:
        if dot_git.is_file():
            gitdir = dot_git.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip()
            parts = Path(gitdir).parts
            if "worktrees" in parts:
                return Path(*parts[: parts.index(".git")])
    except (OSError, IndexError, ValueError):
        pass
    return here


EVENT_LOG = _primary_root() / ".claude" / "cache" / "guard-events.ndjson"


def log_event(name: str, outcome: str, reason: str, payload: dict[str, Any] | None,
              log_path: Path | None = None, extra: dict[str, Any] | None = None) -> None:
    import datetime
    import os
    tool_input = (payload or {}).get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {"command": str(tool_input or "")}
    target = tool_input.get("file_path") or tool_input.get("command") or ""
    row = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "guard": name,
        "outcome": outcome,
        "tool": (payload or {}).get("tool_name"),
        "target": str(target)[:200],
        "reason": reason[:300],
        "session": (payload or {}).get("session_id"),
        "cwd": (payload or {}).get("cwd") or os.getcwd(),
    }
    if extra:  # kind / owner / source: the unified gate-event shape (gate_alignment)
        row.update({k: v for k, v in extra.items() if k not in row})
    path = log_path or Path(os.environ.get("NOCTUS_GUARD_EVENT_LOG") or EVENT_LOG)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        print(f"claude-guard-{name}: guard-event log write failed ({exc}); verdict unchanged",
              file=sys.stderr)


class GuardTimeout(BaseException):
    """BaseException on purpose: a guard's inner `except Exception` must not swallow it."""


def load_module(path: str | Path, name: str | None = None) -> ModuleType:
    """Load a guard's decision module BY PATH (the one shared importlib idiom).

    Fail-CLOSED: any failure raises `ImportError` (or whatever the module's own
    import raises) — never returns None. Called from inside a `judge`, `run_guard`
    turns the raise into a `[noc-guard:<name>]` deny; the advisory hooks catch it
    and stay silent-but-logged. `name` defaults to `noc_<file stem>`.
    """
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name or f"noc_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: @dataclass resolves annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    event_log: Path | None = None,
    fail_open_when: Callable[[dict[str, Any]], bool] | None = None,
) -> int:
    """Read the hook payload, call `judge(payload)`, emit a deny on a verdict OR on any failure.

    `judge` returns None to allow, a dict with `reason` to deny, or a dict with
    `decision: "allow"` + `updated_input` (+ `context`) to allow a REWRITTEN call
    (the primary-write redirect). Always returns 0: a deny is a JSON decision on
    stdout, never a non-zero exit (which would fail open).
    """
    stdin = stdin if stdin is not None else sys.stdin
    out = stdout if stdout is not None else sys.stdout

    payload: Any = None

    def _emit(reason: str) -> int:
        json.dump(deny_json(name, reason), out)
        log_event(name, "deny", reason, payload if isinstance(payload, dict) else None, event_log)
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

    def _read_only_timeout() -> bool:
        """ASYMMETRY: a READ-ONLY call that merely ran out of time is allowed (logged), never blocked."""
        try:
            return bool(fail_open_when and isinstance(payload, dict) and fail_open_when(payload))
        except Exception:  # noqa: BLE001 - an unprovable read-only call stays fail-closed
            return False

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
        if _read_only_timeout():
            msg = f"[noc-guard:{name}] WARNING: guard timed out after {deadline_s:g}s on a read-only call -- allowed"
            print(msg, file=sys.stderr)
            log_event(name, "allow-timeout", msg, payload, event_log)
            return 0
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
    if verdict.get("decision") == "allow":
        if not isinstance(verdict.get("updated_input"), dict):
            return _emit("allow verdict without an updated_input object — guard failed closed; fix the guard.")
        json.dump(allow_rewritten_json(verdict["updated_input"], str(verdict.get("context") or "")), out)
        log_event(name, "rewrite", str(verdict.get("context") or ""), payload, event_log)
        return 0
    return _emit(str(verdict["reason"]))


def allow_rewritten_json(updated_input: dict[str, Any], context: str) -> dict[str, Any]:
    output: dict[str, Any] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": updated_input,
    }
    if context:
        output["additionalContext"] = context
    return {"hookSpecificOutput": output}
