#!/usr/bin/env python3
"""PostToolUse hook — the measurement half of the primary-checkout write guard.

**Why this exists (2026-09-23).** `primary_write_guard.decide()` (the
PreToolUse leg, `claude-guard-primary-write.py`) used to refuse a Bash call
whenever it could not resolve the write target exactly, judging it against
the command's effective cwd instead — a GUESS, not a proof. That guess is
what made the Bash leg a wall: 13 `fix(guard)` commits since 2026-08 chasing
one more shell-quoting shape, and it still refused a `curl … -o
<scratchpad>/x.js` whose actual target was an absolute path OUTSIDE the repo,
purely because `curl -o` is not (and can never exhaustively be) a shape the
parser recognizes. A PreToolUse hook can only ever be a good PARSER of an
arbitrary shell command, never a proof of what it will do.

`decide()` now allows an unresolvable Bash target pre-emptively. This hook is
how the guard still catches it if it actually landed in the primary: it reads
the `git status --porcelain` baseline the PAIRED PreToolUse leg captured
BEFORE the command ran (`capture_pretool_baseline`), diffs it against the
REAL state after, and reports anything genuinely new — minus the append-only
ledgers the toolkit legitimately writes there. This is a SAFETY NET, not a
wall: it never blocks (the command already ran; there is nothing left to
refuse), it only surfaces loudly so the agent cleans up before committing.

All the actual decision logic lives in the SHARED
`mcp/noctusai/tools/noctus/dev/primary_write_guard.py` module —
`measure_posttool_dirt(cwd)`. This file only speaks the harness's hook
protocol (JSON on stdin → stdout/stderr) and loads that module BY PATH via
`_guard_failclosed.load_module`, the shared loader every `claude-guard-*`
hook in this repo uses, for the same reason: this hook runs
after every Bash call in a session, so its import cost is paid hundreds of
times.

ADVISORY BY CONSTRUCTION, same three properties as
`claude-guard-harness-signature.py`:

* **Never blocks.** Always exits 0.
* **Silent when there is nothing to report** — no guarded branch, no
  baseline, no new dirt, or the dirt is entirely ledger ndjson. See
  `measure_posttool_dirt`'s own docstring for why each of those is silent
  rather than a report.
* **Fails OPEN, loudly.** If the module cannot be loaded or throws, the call
  proceeds silently to stdout/exit-0 and the reason goes to stderr.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "primary_write_guard.py"


def _load_guard():
    return load_module(GUARD)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    cwd = payload.get("cwd")
    try:
        guard = _load_guard()
        # Same fallback as the Pre leg: a cwd outside the repo still measures
        # the primary this hook guards (the baseline is per session, so the
        # two legs pair on session_id, not on cwd).
        ctx = (guard.discover_context(cwd) if cwd else None) or guard.discover_context(str(REPO_ROOT))
        warning = guard.measure_posttool_dirt(cwd, ctx=ctx, session_id=payload.get("session_id"))
    except Exception as exc:  # fail open — see the module docstring
        print(
            f"claude-guard-primary-write-post: guard unavailable ({exc}) — not blocking",
            file=sys.stderr,
        )
        return 0

    if warning is None:
        return 0

    print(warning, file=sys.stderr)
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": warning,
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
