#!/usr/bin/env python3
"""PreToolUse hook — refuse a write aimed at the primary checkout on a shared
branch, refuse a git invocation that disables its own hooks, AND refuse
tampering with the hook FILES themselves (`.git/hooks/*`, `.git/config`).

Thin adapter. Every decision lives in
`mcp/noctusai/tools/noctus/dev/primary_write_guard.py` — `decide()` for the
primary-checkout-write concern, `decide_git_bypass()` for the git-invocation
hooks-bypass concern, `decide_hook_integrity()` for the file-tampering
variant of the same concern (three independent functions in the SAME module;
see each function's own docstring for why they are separate). This file only
speaks the harness's hook protocol (JSON on stdin → a permission decision on
stdout), and loads that ONE module ONCE per call — checking all three
concerns costs no additional `importlib` round-trip, only extra function
calls on an already-loaded module.

**Also the measurement net's OTHER half.** When every decision above allows
an in-flight `Bash` call and the primary checkout is on a shared branch, this
leg stashes a `git status --porcelain` snapshot (`capture_pretool_baseline`)
for the PAIRED `PostToolUse` hook (`claude-guard-primary-write-post.py`) to
diff against. `decide()` no longer refuses a Bash write whose exact target it
could not parse (see that function's own "MEASURE, DON'T PREDICT" note) — the
snapshot here is how the guard still catches it if it actually landed in the
primary, just AFTER the fact instead of guessing beforehand.

Two deliberate properties:

* **It loads the guard BY PATH, not as a package.** Importing
  `tools.noctus.dev.…` normally would drag in `settings` and the rest of the
  toolkit; this hook runs before EVERY Bash/Edit/Write call, so its import cost
  is paid hundreds of times per session. By-path import of a stdlib-only module
  keeps that in the low milliseconds.
* **It fails CLOSED.** If the guard cannot be loaded, throws, or exceeds its
  internal 8 s deadline, the call is DENIED (`[noc-guard:primary-write] ...`) —
  Claude Code treats a crashed/timed-out hook as non-blocking, so failing open
  silently stops guarding. Shared runner: `_guard_failclosed.run_guard`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import DEFAULT_DEADLINE_S, load_module, log_event, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "primary_write_guard.py"


def _load_guard():
    return load_module(GUARD)


#: margin kept between the guard's own deadline and run_guard's alarm, so a slow probe refuses with ITS reason
DEADLINE_MARGIN_S = 1.5
#: a call slower than this logs its per-stage timings (the next timeout names its stage instead of being a guess)
SLOW_CALL_S = 2.0


def _judge(payload: dict) -> dict | None:
    import time
    t0 = time.monotonic()
    stages: dict[str, float] = {}
    try:
        return _judge_timed(payload, stages)
    finally:
        total = time.monotonic() - t0
        if total > SLOW_CALL_S:
            try:
                log_event("primary-write", "slow", f"{total:.2f}s", {"session_id": payload.get("session_id")},
                          extra={"kind": "hook", "stages": {k: round(v, 3) for k, v in stages.items()},
                                 "tool_name": payload.get("tool_name")})
            except Exception:  # noqa: BLE001 - telemetry never changes a verdict
                pass


_WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})


def _is_read_only_call(payload: dict) -> bool:
    """True when the call provably cannot write (no git, no repo walk needed to say so)."""
    tool = payload.get("tool_name", "")
    if tool in _WRITE_TOOLS:
        return False
    if tool != "Bash":
        return True  # Grep/Glob/Read/...: no write intent at all
    command = str((payload.get("tool_input") or {}).get("command") or "")
    return _load_guard().bash_is_read_only(command)


def _judge_timed(payload: dict, stages: dict[str, float]) -> dict | None:
    import time
    mark = [time.monotonic()]

    def lap(name: str) -> None:
        now = time.monotonic()
        stages[name] = stages.get(name, 0.0) + now - mark[0]
        mark[0] = now

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    guard = _load_guard()
    guard.set_deadline(DEFAULT_DEADLINE_S - DEADLINE_MARGIN_S)
    lap("load")
    if _is_read_only_call(payload):
        # READ-ONLY FAST PATH (2026-11-12): only the pure-string git-bypass check runs. No `git`
        # subprocess, no worktree discovery, no baseline -- those cost seconds under load and a
        # read has nothing to guard. A stale baseline from an earlier write is dropped by a plain
        # file remove (no git) so the Post leg never diffs against it.
        verdict = guard.decide_git_bypass(tool_name, tool_input)
        if verdict is None and tool_name == "Bash":
            from _guard_failclosed import _primary_root
            guard.discard_pretool_baseline(guard.GuardContext(str(_primary_root()), "", ()),
                                           payload.get("session_id"))
        lap("readonly-fastpath")
        return verdict
    # Hooks-bypass and hook-integrity are checked FIRST: both are universal,
    # branch- and location-independent concerns (see each function's own
    # docstring), so a command that is also a primary-checkout write gets the
    # more specific reason.
    cwd = payload.get("cwd") or os.getcwd()
    verdict = guard.decide_git_bypass(tool_name, tool_input)
    if verdict is None:
        verdict = guard.decide_hook_integrity(tool_name, tool_input, cwd)
    if verdict is None:
        verdict = guard.decide_wired_worktree_npm(tool_name, tool_input, cwd)
    lap("bypass+integrity")
    ctx = None
    if verdict is None:
        ctx = guard.discover_context(cwd)
        if ctx is not None:
            # AUTO-CLAIM (2026-11-05): working in a worktree makes it this
            # session's claim, so a later stray primary write can be redirected.
            guard.auto_claim(tool_name, tool_input, payload.get("session_id"), cwd, ctx)
        lap("context+claim")
        verdict = guard.decide(tool_name, tool_input, cwd, ctx=ctx)
        lap("decide")
        if verdict is not None and ctx is not None:
            # A refused Edit/Write (file path) or relative-path Bash command whose
            # session claimed a worktree is rewritten into it instead (visible:
            # the allow carries the REDIRECTED note).
            sid = payload.get("session_id")
            verdict = (guard.redirect_for(tool_name, tool_input, sid, ctx, verdict)
                       or guard.redirect_bash_for(tool_input, sid, cwd, ctx, verdict)
                       or verdict)
    if verdict is None and tool_name == "Bash":
        # The measurement net's baseline — see the module docstring. Best-effort
        # by construction; nothing here can turn an ALLOW into a refusal.
        # A call that STARTS outside the repo (`cd <repo> && …` from the
        # scratchpad) has no ctx from its cwd, yet its Post leg runs inside the
        # repo — so fall back to the primary this hook guards, and per session:
        # capture when guarded, otherwise discard, so the Post leg never diffs
        # against an older call's snapshot (2026-11-04 false "NEW DIRT").
        base_ctx = ctx if ctx is not None else guard.discover_context(str(REPO_ROOT))
        if base_ctx is not None:
            sid = payload.get("session_id")
            if (base_ctx.guarded and guard.time_left() >= guard.BEST_EFFORT_MIN_LEFT_S
                    and not guard.bash_is_read_only(str(tool_input.get("command") or ""))):
                guard.capture_pretool_baseline(base_ctx, sid)
            else:
                # no budget for the snapshot: discard, so the Post leg never diffs against a STALE one
                guard.discard_pretool_baseline(base_ctx, sid)
        lap("baseline")
    return verdict


def main() -> int:
    return run_guard("primary-write", _judge, fail_open_when=_is_read_only_call)


if __name__ == "__main__":
    raise SystemExit(main())
