"""Shared classifier for a failed `git push` (verdict-channel integrity).

A rejected push is only a "concurrent-push race" when the rejection is a
non-fast-forward OR the remote ref actually advanced. A pre-push hook that says
no (remote unchanged) must surface its output and NOT be retried or relabelled
as a race. Used by `task_branch` integrate and `_ledger_push._push_leg`.
"""
from __future__ import annotations

import re
from typing import Any, Callable

_FF_REJECT_RE = re.compile(
    r"non-fast-forward|fetch first|stale info|tip of your current branch is behind", re.I)


def resolve_ref(git: Callable[..., tuple[int, str, str]], ref: str) -> str | None:
    rc, out, _e = git("rev-parse", ref)
    return out.strip() if rc == 0 and out.strip() else None


def classify_push_failure(git: Callable[..., tuple[int, str, str]], remote: str,
                          dev_branch: str, before: str | None,
                          out: str, err: str) -> dict[str, Any]:
    """kind: race (retry) | hook_rejected | push_failed (both: do not retry)."""
    text = "\n".join(x for x in (out, err) if x and x.strip())
    lines = [ln for ln in text.splitlines() if ln.strip()]
    tail = "\n".join(lines[-40:])
    git("fetch", remote, "--quiet")
    after = resolve_ref(git, f"{remote}/{dev_branch}")
    advanced = bool(before and after and before != after)
    if advanced or _FF_REJECT_RE.search(text):
        return {"kind": "race", "remote_advanced": advanced, "tail": tail}
    kind = "hook_rejected" if re.search(r"hook|pre-push|UPDATE ", text) else "push_failed"
    return {"kind": kind, "remote_advanced": False, "tail": tail}
