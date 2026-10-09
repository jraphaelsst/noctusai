"""Fast-forward the PRIMARY checkout to ``origin/dev`` — ff-only, never forced.

**The recurrence this closes (3x on 2026-10-09).** Everything that runs the
toolkit "from the primary" — `task_branch`'s fresh-subprocess fallback, the
SessionStart worktree sweep, the merged-tip gates — executes the primary
checkout's ``mcp/noctusai/cli.py``. Nothing moved the primary forward, so code
that had already landed on ``dev`` stayed invisible until someone fast-forwarded
it by hand (the scoped mcp gate and the .env scrub both shipped and then did
not run, because the primary still held the old code).

**When it refuses (and says so — never silently):** the primary is on any
branch other than ``dev``, a detached HEAD, has TRACKED modifications (staged
or not), has local commits ``origin/dev`` lacks (diverged), or the FF would
overwrite an untracked file. Untracked files are otherwise fine: an ff-only
merge leaves them alone. Every refusal is a ``skipped_*`` status with the
reason; the caller surfaces it.

**Why no guard is involved.** ``primary_write_guard`` is a PreToolUse hook over
Claude's own Edit/Write/Bash calls, and ``check_primary_checkout_commit`` fires
on commits. This runs inside the toolkit / a harness hook and creates no commit
— an ff-only merge only moves ``dev`` to a commit that already passed every
gate on its way to ``origin/dev``, exactly what a human ``git pull --ff-only``
does. The guards stay sharp: no carve-out was needed.

Stdlib-only, importable by file path (the SessionStart hook loads it without
importing the toolkit package).
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

GitFn = Callable[..., tuple[int, str, str]]


def _default_git(root: str) -> GitFn:
    def git(*args: str, timeout: float = 120) -> tuple[int, str, str]:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    return git


def ff_primary_to_dev(
    root: str,
    *,
    dev_branch: str = "dev",
    remote: str = "origin",
    fetch: bool = False,
    git: GitFn | None = None,
) -> dict[str, Any]:
    """Fast-forward ``root`` (the primary checkout) to ``<remote>/<dev_branch>``.

    ``fetch=True`` refreshes the remote-tracking ref first (the SessionStart
    child); ``task_branch integrate`` passes False — its push already moved the
    shared ``refs/remotes`` ref. Never raises: every outcome is a status.
    """
    g = git or _default_git(root)
    upstream = f"{remote}/{dev_branch}"
    try:
        if fetch:
            rc, _o, err = g("fetch", "--quiet", remote, dev_branch)
            if rc != 0:
                return {"status": "error", "reason": f"fetch failed: {err[:200]}"}
        rc, branch, err = g("rev-parse", "--abbrev-ref", "HEAD")
        if rc != 0:
            return {"status": "error", "reason": f"rev-parse failed: {err[:200]}"}
        if branch == "HEAD":
            return {"status": "skipped_detached", "reason": "primary is on a detached HEAD"}
        if branch != dev_branch:
            return {"status": "skipped_branch",
                    "reason": f"primary is on {branch!r}, not {dev_branch!r}"}
        rc, dirty, err = g("status", "--porcelain", "--untracked-files=no")
        if rc != 0:
            return {"status": "error", "reason": f"status failed: {err[:200]}"}
        if dirty:
            # split, never slice: callers may have stripped the first line's leading space
            files = [ln.split(maxsplit=1)[-1] for ln in dirty.splitlines() if ln.strip()]
            return {"status": "skipped_dirty",
                    "reason": f"{len(files)} tracked modification(s) in the primary",
                    "files": files[:20]}
        rc, counts, err = g("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if rc != 0:
            return {"status": "error", "reason": f"rev-list failed: {err[:200]}"}
        ahead, behind = (int(x) for x in counts.split())
        rc, before, _e = g("rev-parse", "--short", "HEAD")
        if ahead:
            return {"status": "skipped_diverged",
                    "reason": f"primary {dev_branch} has {ahead} commit(s) {upstream} lacks",
                    "head": before}
        if not behind:
            return {"status": "up_to_date", "head": before}
        rc, _o, err = g("merge", "--ff-only", "--quiet", upstream, timeout=600)
        if rc != 0:
            return {"status": "skipped_ff_failed",
                    "reason": f"git merge --ff-only refused: {err[:300]}", "head": before}
        rc, after, _e = g("rev-parse", "--short", "HEAD")
        return {"status": "fast_forwarded", "from": before, "to": after, "commits": behind}
    except Exception as e:  # noqa: BLE001 — best-effort; the caller reports it
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}


def summary_line(result: dict[str, Any]) -> str:
    """One human line for a result ('' for the boring up-to-date case)."""
    s = result.get("status")
    if s == "fast_forwarded":
        return (f"noc: primary checkout fast-forwarded {result['from']}..{result['to']} "
                f"({result['commits']} commit(s))")
    if s in (None, "up_to_date"):
        return ""
    return f"noc: primary checkout NOT fast-forwarded ({s}): {result.get('reason', '')}"
