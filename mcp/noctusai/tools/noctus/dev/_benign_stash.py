"""Shared benign-refresh-artifact stash helper — the N=2 DRY lift of the
``classify dirty files into benign-vs-real → stash the benign ones → rebase →
pop`` idiom.

WHY THIS EXISTS. ``git rebase`` refuses outright when the working tree is dirty
("error: cannot rebase: You have unstaged changes") — it does not care WHICH
files are dirty. Our own pre-commit / cache-refresh hooks dirty a small, known
set of reconstructable files (``project-history/*.ndjson`` ledgers, the
agent-context mirrors, ``.claude/cache/*``) as a side effect of essentially every
commit. So a rebase that would be a clean fast-forward gets refused by artifacts
the tooling itself just wrote.

TWO CALL SITES HAD THE SAME REBASE LEG; ONLY ONE HAD THE FIX.

* ``task_branch.integrate`` (worktree side) — fixed 2026-05-28 after the failure
  was observed N=5+ times ("Bug C"): it classified dirty files and auto-stashed
  the benign ones before rebasing.
* ``_ledger_push.commit_and_ff_push_ledger`` (PRIMARY-checkout side) — same
  ``git rebase <dev_ref>`` leg, no stash. The cost-log pre-commit hook dirties
  ``project-history/vector-costs.ndjson`` on every commit, so this rebase was
  refused essentially every time it mattered. The helper then returned
  ``committed_locally=True, pushed=False`` and left the primary checkout DIVERGED
  from ``origin/dev`` — the recurring "primary/origin divergence" loop with 4+
  ledger entries against it, resolved by hand each session with
  ``git -c rebase.autoStash=true rebase origin/dev``.

The fix was never lifted, so the second site kept paying for it. This module is
that lift: one mechanism, both callers.

WHAT STAYS LOUD. Only the known-benign patterns are stashed. A genuinely dirty
working tree (real in-progress work) still blocks the rebase — but the callers
now surface it as an explicit ``dirty_blocked`` naming the files, instead of a
generic failure that reads as a mystery divergence later.

KB § PATTERNS/common/self-branching-mode.md · KB § PATTERNS/architect/branch-tree-tracking.md
"""
from __future__ import annotations

import fnmatch
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# A ``run_git(*args) -> (rc, stdout, stderr)`` closure. Each caller supplies one
# that already encodes HOW it reaches its repo (``-C <root>`` vs ``cwd=``), so
# this module never has to know.
RunGit = Callable[..., tuple[int, str, str]]

# Known-benign refresh artifacts — files our own pre-commit / cache-refresh hooks
# write as side effects. They appear in ``git status --porcelain``, block a
# rebase, and carry no task work.
#
# All four ``project-history/*.ndjson`` ledgers are ``merge=union`` append-only
# logs churned by the post-checkout/post-merge cache-settle hooks
# (noc-graph / auto-improvement / worktree-salvage / branch-tree). They are
# reconstructable and never contain task work, so they are benign for the purpose
# of the rebase pre-check.
BENIGN_REFRESH_PATTERNS: tuple[str, ...] = (
    "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
    "KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md",
    "project-history/vector-costs.ndjson",
    "project-history/auto-improvement.ndjson",
    "project-history/worktree-salvage.ndjson",
    "project-history/branch-tree.ndjson",
    ".claude/cache/*",
)

STASH_MESSAGE = "task_branch auto-stash: benign refresh artifacts"


def is_benign(path: str, patterns: tuple[str, ...] = BENIGN_REFRESH_PATTERNS) -> bool:
    """True iff ``path`` matches one of the known-benign refresh patterns."""
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def strip_status_code(raw: str) -> str:
    """Strip the porcelain status columns from one ``git status --porcelain``
    line, returning the path.

    Real git always emits EXACTLY two status columns followed by a space
    (``" M path"``, ``"M  path"``, ``"MM path"``), so the fast path is a fixed
    3-char offset. But a fixed offset applied to a line that does NOT have that
    shape silently TRUNCATES the path — ``"M path"`` becomes ``"ath"``-style
    garbage that then misclassifies as real work. A path we cannot parse must
    never be silently corrupted into a different path, so anything not matching
    the canonical shape falls back to splitting on the first whitespace run.

    The rename form ``XY old -> new`` keeps the destination path.
    """
    body = raw[3:] if len(raw) > 3 and raw[2] == " " else (
        raw.lstrip().split(" ", 1)[-1] if " " in raw.lstrip() else raw
    )
    return body.strip().split(" -> ")[-1].strip()


def classify_porcelain(
    out: str, patterns: tuple[str, ...] = BENIGN_REFRESH_PATTERNS
) -> tuple[list[str], list[str]]:
    """Split ``git status --porcelain`` output into ``(benign, real)`` paths."""
    benign: list[str] = []
    real: list[str] = []
    for raw in out.splitlines():
        if not raw.strip():
            continue
        path = strip_status_code(raw)
        (benign if is_benign(path, patterns) else real).append(path)
    return benign, real


def classify_dirty(run_git: RunGit) -> tuple[list[str], list[str]]:
    """``git status --porcelain`` → ``(benign, real)``.

    A git-status failure returns ``([], ["<git-status-failed>"])`` so the caller
    treats it conservatively as real dirt rather than assuming a clean tree.
    """
    rc, out, _err = run_git("status", "--porcelain")
    if rc != 0:
        return [], ["<git-status-failed>"]
    return classify_porcelain(out or "")


def stash_benign(
    run_git: RunGit,
    benign: list[str],
    *,
    log_prefix: str = "benign_stash",
) -> bool:
    """Stash the known-benign artifacts so the tree is clean enough to rebase.

    Returns True if the stash succeeded OR there was nothing to stash; False on
    failure (the caller then proceeds unstashed and lets the rebase surface it,
    rather than pretending the tree is clean).
    """
    if not benign:
        return True
    logger.debug("%s: auto-stashing %d benign artifact(s): %s",
                 log_prefix, len(benign), benign)
    rc, _out, err = run_git(
        "stash", "push", "--include-untracked", "--message", STASH_MESSAGE, "--", *benign
    )
    if rc != 0:
        logger.warning("%s: auto-stash failed (%s); proceeding without stash — "
                       "the rebase may be refused", log_prefix, (err or "").strip())
        return False
    return True


def pop_stash(run_git: RunGit, *, log_prefix: str = "benign_stash") -> None:
    """Pop the auto-stash. Best-effort: a failure is logged, never raised —
    the surrounding operation has already completed one way or the other."""
    rc, _out, err = run_git("stash", "pop")
    if rc != 0:
        logger.warning("%s: stash pop failed (%s); the benign artifacts remain "
                       "stashed — run `git stash pop` to restore them",
                       log_prefix, (err or "").strip())


def dirty_blocked_result(real: list[str], dev_ref: str) -> dict[str, Any]:
    """The explicit, named outcome for 'the tree carries REAL dirt, so the rebase
    cannot run'. Replaces a generic failure that later reads as an unexplained
    primary/origin divergence."""
    files = ", ".join(real[:10]) + (" …" if len(real) > 10 else "")
    return {
        "ok": False,
        "status": "dirty_blocked",
        "retryable": False,
        "committed_locally": True,
        "dirty_files": real,
        "error": (
            f"working tree carries uncommitted non-benign changes ({files}), so the "
            f"rebase onto {dev_ref} cannot run — the ledger row is committed locally "
            f"but NOT pushed. Commit or stash that work, then re-run; local will stay "
            f"diverged from {dev_ref} until you do."
        ),
    }


__all__ = [
    "BENIGN_REFRESH_PATTERNS", "STASH_MESSAGE", "RunGit",
    "is_benign", "strip_status_code", "classify_porcelain", "classify_dirty",
    "stash_benign", "pop_stash", "dirty_blocked_result",
]
