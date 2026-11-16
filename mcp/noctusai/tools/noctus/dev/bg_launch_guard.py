"""Make EVERY background launch end at RUNTIME, decided BEFORE it runs (PreToolUse on Bash).

WHY (owner, 2026-11-14): leftovers lived hours or days; a sweep someone must remember to call is not a
mechanism. "They live no longer than they were meant to." So the process itself ends the moment its job is done
or can no longer finish, and this guard makes that true for every launch:

  * run_in_background, not declared infrastructure, not already wrapped -> REWRITTEN (updatedInput) into
    `scripts/bg_run.py --purpose <derived> --done "command exits" --command=<cmd>`: the wrapper ends when the
    child exits, when its `--done-when` holds, when a wait's producer is dead (ProducerWatch), and when its
    owning Claude session dies (parent-death). Nothing is refused that can simply be wrapped.
  * a POLL (a `while`/`until` whose body is only `sleep` + a readiness test: file exists/non-empty, grep a
    pattern, pgrep) is never acceptable - bounded by `timeout N` or not, foreground or background (owner
    2026-11-14: "launch the command itself with run_in_background; the completion notification resumes you;
    read a task output once, never in a loop"). Bounded non-poll loops (`for f in ...; do ...; done`) pass;
  * what cannot be made to end is DENIED, with the shape to use: a loop/poll/follow/watch with no end condition
    (`while true; do sleep`, `tail -f`, `watch`, `--watch`), also when it hides inside a script the command
    invokes (`./poll.sh`, `bash x.sh`, `python poll.py`; the first path token is opened and scanned, bounded);
  * a wrapped launch missing `--purpose`, or `--done` (or `--long-lived`), or wrapping an open-ended command with
    no `--done-when`, is denied.
  * FOREGROUND calls are judged the same way (the harness moves a call that hits the 600 s tool timeout to the
    background by itself): an unbounded loop/follow/watch, inline or inside an invoked script, is denied.
ALLOWED untouched: known infrastructure (steward merge-queue watch / heartbeat, MCP servers, dev servers).
Bounded forms pass for non-poll loops: a `timeout N` before the loop (also inside `bash -c '...'`), or the wrapper with `--done-when`.

JUDGED BY STRUCTURE, NOT TEXT: `scripts/hooks/_bg_shell.py` lexes the command like a shell (quotes, `$(...)`,
heredocs, redirections; no new dependency), so prose in `-m '...'` or a heredoc written to a file is data and
never judged, while a quoted loop that EXECUTES (`bash -c`, `eval`, `$(...)`, a heredoc fed to a shell) is.

DELIBERATE LIMITS: a loop built at runtime (`eval "$VAR"`), a script that sources another script more than
4 levels deep or one larger than 128 KB / outside the repo and the session scratchpad is not seen; a Python
script is judged only for an infinite `while True` with no break/return. Anything that still escapes is caught
by the session-end sweep, which logs it as `escaped-runtime-end` (an escape is a bug in the runtime-end legs).
Enforcing since ENFORCE_FROM (owner decision 2026-11-14, ended the warn-only soak early).
KB § PATTERNS/common/background-agent-lifecycle.md
"""
from __future__ import annotations

import datetime as _dt
import os
import shlex
import sys
from pathlib import Path
from typing import Any

_HOOKS = Path(__file__).resolve().parents[5] / "scripts" / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import _bg_process_core as core  # noqa: E402

KB_POINTER = "KB § PATTERNS/common/background-agent-lifecycle.md"

# Owner decision 2026-11-14 ("im tired of leftovers being held for hours or even days"): the planned 7-day
# warn-only soak (to 2026-11-21) is ended early; the guard denies from today. NOC_BG_LAUNCH_MODE still overrides.
ENFORCE_FROM = "2026-11-14"


def mode(today: _dt.date | None = None) -> str:
    """'enforce' or 'shadow'. Env `NOC_BG_LAUNCH_MODE` overrides; otherwise the date decides."""
    forced = (os.environ.get("NOC_BG_LAUNCH_MODE") or "").strip().lower()
    if forced in {"enforce", "shadow"}:
        return forced
    today = today or _dt.date.today()
    return "enforce" if today >= _dt.date.fromisoformat(ENFORCE_FROM) else "shadow"


POLL_RULE = "launch the command itself with run_in_background; the completion notification resumes you; read a task output once, never in a loop"
WAIT_FORM = POLL_RULE
FORM = ('python3 scripts/bg_run.py --purpose "<what for>" --done "<what counts as done>" '
        '[--done-when "<shell check, exit 0 = done>"] -- <command>   '
        '(infrastructure that lives on purpose: --purpose "..." --long-lived -- <command>)')
_BG_RUN = Path(core.__file__).resolve().parent.parent / "bg_run.py"


def _deny(why: str) -> dict[str, str]:
    return {"reason": f"background launch refused: {why}. Background processes end themselves: launch it as {FORM}. {KB_POINTER}"}


def _purpose(ti: dict[str, Any], command: str, fallback: str) -> str:
    desc = " ".join(str(ti.get("description") or "").split())
    if len(desc) >= 5:
        return desc[:120]
    return f"{fallback}: {' '.join(command.split())[:70]}"


def rewrite_finite(ti: dict[str, Any], command: str, wrapped: str | None = None) -> dict[str, Any]:
    """The REWRITE verdict. `command` is what the agent wrote (it names the purpose); `wrapped` is what actually runs
    inside the wrapper when an inner rewrite already changed it (the heavy-run gate, via `bash_rewrite_chain`)."""
    q = shlex.quote
    cmd = (f"python3 {q(str(_BG_RUN))} --purpose {q(_purpose(ti, command, 'background'))} "
           f"--done 'the command exits' --command={q(wrapped if wrapped is not None else command)}")
    return {"decision": "allow", "updated_input": {**ti, "command": cmd},
            "context": "this background launch was wrapped in scripts/bg_run.py: it ends the moment the command exits, "
                       f"or its owning session ends; you are notified as before. {KB_POINTER}"}


def _teach(found: list[Any]) -> str:
    kinds = {f.kind for f in found}
    if "poll" in kinds:
        return (f"a poll (a loop that only sleeps and tests readiness: {found[0].detail}) is never acceptable, with or without "
                f"`timeout`: {POLL_RULE}")
    where = "; ".join(f"{f.kind}: {f.detail}" for f in found[:3])
    if "script-loop" in kinds:
        return (f"the script it runs contains an open-ended loop ({where}); a script's loop has no end the wrapper can see. "
                "Launch the producer itself in the background, or bound it: `bg_run.py --done-when '<check>' -- <script>`")
    if "loop" in kinds:
        return (f"open-ended loop with no declared done-condition ({where}); launch the producer itself in the "
                "background (you are notified when it exits), or give it an end with `--done-when`")
    return (f"open-ended follow/watch with no declared done-condition ({where}); "
            "give it an end: `bg_run.py --done-when '<check>' -- <command>`, or launch the producer itself")


def _wrapper_in(command: str, ctx: Any) -> dict | None:
    for c in core.shell.parse(command).cmds:
        ws, _ = core.shell.core_words(c.words)
        w = core.shell.wrapper_of(ws) if ws else None
        if w is not None:
            return w
    return None


def decide(payload: dict[str, Any]) -> dict[str, Any] | None:
    """None to allow; `{"reason": ...}` to deny; `{"decision": "allow", "updated_input": ..}` to allow a REWRITTEN
    launch. Only `Bash` is judged."""
    if (payload.get("tool_name") or "") != "Bash":
        return None
    ti = payload.get("tool_input") or {}
    command = ti.get("command") or ""
    if not command.strip() or core.infra_label(command):
        return None
    ctx = core.shell.make_ctx(payload.get("cwd"))
    found = core.shell.open_ended(command, ctx=ctx)
    if not ti.get("run_in_background"):
        if not found:
            return None
        return {"reason": "foreground loop refused: an unbounded wait/poll/follow outlives its purpose (the harness "
                          f"moves a call that hits the tool timeout to the background, where it waits forever): "
                          f"{_teach(found)}. {WAIT_FORM}. {KB_POINTER}"}
    wrap = _wrapper_in(command, ctx)
    if wrap is not None:
        long_lived = "long-lived" in wrap["flags"]
        if not wrap.get("purpose"):
            return _deny("the wrapper needs --purpose")
        if not long_lived and not wrap.get("done"):
            return _deny("the wrapper needs --done (what counts as done) or --long-lived")
        if not long_lived and found:
            return _deny("the wrapped command is an open-ended loop/poll/follow with no --done-when check")
        return None
    if not found:
        return rewrite_finite(ti, command)
    return _deny(_teach(found))
