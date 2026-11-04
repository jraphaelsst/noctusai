"""Shared classifier for a failed `git push` (verdict-channel integrity).

A rejected push is only a "concurrent-push race" when the rejection is a
non-fast-forward OR the remote ref actually advanced. A pre-push hook that says
no (remote unchanged) must surface its output and NOT be retried or relabelled
as a race. Used by `task_branch` integrate and `_ledger_push._push_leg`.
"""
from __future__ import annotations

import re
from typing import Any, Callable

# The REMOTE answered with an error (GitHub 5xx, transport failure): our hook
# passed and the push reached the server. Checked BEFORE the hook pattern,
# because our pre-push hook prints `[pre-push]` lines on EVERY push. Until
# 2026-11-04 a GitHub "Internal Server Error" was therefore reported as
# `hook_rejected`, which sends the reader to chase a hook that said yes.
_REMOTE_ERROR_RE = re.compile(
    r"\[remote rejected\]|remote: (?:internal server error|.*\b5\d\d\b)"
    r"|the requested url returned error: 5\d\d|\bHTTP 5\d\d\b|RPC failed"
    r"|unexpected disconnect|early EOF|Could not resolve host|Connection (?:timed out|reset)",
    re.I)
# A pre-push hook that said no: git refuses locally, nothing is sent.
_HOOK_REFUSED_RE = re.compile(r"hook declined|pre-push hook|\bUPDATE \S", re.I)

_FF_REJECT_RE = re.compile(
    r"non-fast-forward|fetch first|stale info|tip of your current branch is behind", re.I)


def resolve_ref(git: Callable[..., tuple[int, str, str]], ref: str) -> str | None:
    rc, out, _e = git("rev-parse", ref)
    return out.strip() if rc == 0 and out.strip() else None


def classify_push_failure(git: Callable[..., tuple[int, str, str]], remote: str,
                          dev_branch: str, before: str | None,
                          out: str, err: str) -> dict[str, Any]:
    """kind: race (retry) | remote_error (transient server/transport failure:
    re-run is safe, origin did not move) | hook_rejected | push_failed."""
    text = "\n".join(x for x in (out, err) if x and x.strip())
    lines = [ln for ln in text.splitlines() if ln.strip()]
    tail = "\n".join(lines[-40:])
    git("fetch", remote, "--quiet")
    after = resolve_ref(git, f"{remote}/{dev_branch}")
    advanced = bool(before and after and before != after)
    if advanced or _FF_REJECT_RE.search(text):
        return {"kind": "race", "remote_advanced": advanced, "tail": tail}
    if _REMOTE_ERROR_RE.search(text):
        kind = "remote_error"
    elif _HOOK_REFUSED_RE.search(text):
        kind = "hook_rejected"
    else:
        kind = "push_failed"
    return {"kind": kind, "remote_advanced": False, "tail": tail}
