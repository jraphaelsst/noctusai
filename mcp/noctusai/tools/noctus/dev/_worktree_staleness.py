"""Shared worktree-staleness predicate — the merged-base + is-merged core.

NOT an MCP tool (no ``@server.tool``; never added to ``register_all``). It is
the single source of truth for the "is this engineer worktree's branch merged
into the integration branch?" question, consumed by BOTH
``cleanup_worktrees.py`` (``noctus.dev.cleanup_stale_worktrees``) AND
``mole.py`` (``noctus.dev.mole``, worktree scope). It was extracted to kill the
documented N=2 DRY duplication where both tools hand-rolled the same
``merge-base --is-ancestor`` OR ``git cherry`` / ``git log`` predicate and
literally claimed to "exactly parity" each other — changing one drifted from
the other (a cleanup-only base-ref edit broke parity and had to be reverted).

What "merged" means (the orchestrator FFs an engineer branch into the
integration branch via cherry-pick → NEW sha, SAME patch):
  (a) the branch is reachable from the base by SHA ancestry (a true merge), OR
  (b) every commit on the branch is already on the base by PATCH-ID
      (``git cherry base branch`` reports ZERO ``+`` lines and the branch has
      ≥1 commit).
Unmerged work-in-progress branches are NOT merged (so worktrees holding them
are kept by both callers).

Base ref (the dev-integration model — KB § PATTERNS/branching-and-merging.md
§ 0): engineer worktrees fork from and integrate to ``dev``, NOT ``main`` (a
worktree merged-to-dev-but-not-yet-blessed-to-main was never swept under the
old ``origin/main`` keying → disk bloat). The base prefers ``origin/dev`` and
falls back to ``dev`` (mirrors the existing fallback shape).

Injectable runner: every git call goes through a ``run`` callable returning
``(returncode, stdout, stderr)`` — mirroring how ``release.py`` injects ``run``
— so the colocated unit test exercises every path with ZERO real git. The
default runner wraps ``subprocess.run`` at a given root.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

# (rc, stdout, stderr)
GitRunner = Callable[..., tuple[int, str, str]]

# The base the engineer-integration model keys staleness off: prefer the
# integration tip, fall back to the local branch (mirrors the existing shape).
PREFERRED_BASE = "origin/dev"
FALLBACK_BASE = "dev"


def make_subprocess_runner(root: Path, *, timeout: int | None = None) -> GitRunner:
    """A ``run`` that executes ``git <args>`` at ``root`` and returns
    ``(rc, stdout, stderr)``. The default each consumer wires when it isn't
    injecting its own runner. ``timeout`` is forwarded to ``subprocess.run``
    when set (mole's git calls carry a per-call timeout)."""

    def _run(args: list[str]) -> tuple[int, str, str]:
        kwargs: dict = dict(cwd=str(root), capture_output=True, text=True)
        if timeout is not None:
            kwargs["timeout"] = timeout
        r = subprocess.run(args, **kwargs)
        return r.returncode, (r.stdout or ""), (r.stderr or "")

    return _run


def resolve_merged_base(run: GitRunner) -> str:
    """Resolve the comparison base: prefer ``origin/dev``, fall back to ``dev``.

    Mirrors the existing fallback shape (verify the preferred ref resolves;
    otherwise use the local branch name)."""
    rc, _out, _err = run(
        ["git", "rev-parse", "--verify", "--quiet", PREFERRED_BASE]
    )
    return PREFERRED_BASE if rc == 0 else FALLBACK_BASE


def is_ancestor(run: GitRunner, branch: str, base: str) -> bool:
    """``git merge-base --is-ancestor branch base`` — SHA ancestry (true merge)."""
    rc, _o, _e = run(["git", "merge-base", "--is-ancestor", branch, base])
    return rc == 0


def all_commits_cherry_picked(run: GitRunner, branch: str, base: str) -> bool:
    """Patch-id equivalence: every commit on ``branch`` is already on ``base``.

    The branch must have ≥1 commit and ZERO ``+`` lines in
    ``git cherry base branch`` (``+`` = genuinely unmerged; ``-`` = on base by
    patch-id). The orchestrator FFs via cherry-pick (new sha, same patch), so
    this catches branches whose work landed without a SHA-ancestry merge."""
    rc, out, _e = run(["git", "cherry", base, branch])
    if rc != 0:
        return False
    plus_lines = sum(1 for ln in out.splitlines() if ln.startswith("+"))
    _rc2, log_out, _e2 = run(
        ["git", "log", "--oneline", f"{base}..{branch}"]
    )
    total = len([ln for ln in log_out.splitlines() if ln.strip()])
    return total > 0 and plus_lines == 0


def is_merged(run: GitRunner, branch: str, base: str) -> bool:
    """The merged predicate both tools share: SHA-ancestry OR patch-id/cherry."""
    return is_ancestor(run, branch, base) or all_commits_cherry_picked(
        run, branch, base
    )


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 2026-09-16 incident — the merged predicate is a FALSE POSITIVE for a
# freshly-created, actively-worked-in worktree.
#
# ``is_ancestor(run, branch, base)`` is ``git merge-base --is-ancestor branch
# base``, and a commit is trivially its OWN ancestor. A worktree created via
# ``git worktree add -b <branch> <path>`` off the current ``origin/dev`` tip
# starts with ZERO commits ahead — ``branch`` and ``base`` are the SAME sha.
# That makes ``is_ancestor`` return True on the very first call, before the
# engineer has committed anything, classifying the worktree as "merged" —
# and therefore "safe to remove" — while two engineers were actively working
# in it (``community-m1-backend`` / ``community-m1-frontend``, ~6 minutes
# old, 0 commits ahead, swept by ``cleanup_stale_worktrees force=True``,
# uncommitted work lost).
#
# ``is_merged`` itself is not wrong — "reachable from base by SHA ancestry"
# IS what a true merge looks like, and a 0-commit worktree genuinely has no
# unmerged patch to protect via ``git cherry``. The gap is that "merged" and
# "safe to remove right now" are two different questions; a worktree can be
# merged (in the trivial 0-commit sense) and still be somebody's live desk.
# Two independent guards close that gap — neither re-defines "merged":
#
#   1. pointer_blocks_removal — a LIVE branch-tree pointer (the global
#      git-tree × claude-tree map, ``project-history/branch-tree.ndjson``)
#      is a first-class claim: an engineer publishes ``status=on_going``
#      before touching a file (KB § PATTERNS/architect/branch-tree-tracking.md).
#      A non-terminal pointer means someone is claiming this branch RIGHT
#      NOW, independent of what git ancestry says. This is the STRONGER
#      signal and is NEVER bypassed, not even by ``force=True`` — force
#      only ever meant "skip the confirmation ritual", never "override an
#      explicit peer claim".
#   2. is_too_young — even absent a pointer (a raw ``git worktree add``, or
#      a stale/never-updated pointer), a worktree younger than
#      ``min_age_minutes`` is refused. This is what actually would have
#      caught the 2026-09-16 incident: a worktree ~6 minutes old is nowhere
#      near ``DEFAULT_MIN_AGE_MINUTES``. ``force=True`` MAY override this
#      one — an operator who explicitly asks to force-sweep a young-but-
#      merged worktree has made a deliberate call the pointer guard cannot
#      make for them.
#
# Both guards report WHY a candidate was skipped (the reason string / dict)
# rather than silently keeping it — a silent skip reads as "nothing to
# clean up here" and hides the exact signal an operator needs to decide
# whether to force past it.
# ═══════════════════════════════════════════════════════════════════════════

#: Reasoning: the incident worktrees were ~6 minutes old. A default in the
#: 30-120 minute range gives an engineer a full working session's worth of
#: "invisible to staleness heuristics" grace without meaningfully delaying
#: cleanup of worktrees that are genuinely abandoned (those are typically
#: hours-to-days old, not tens of minutes). 60 minutes is the midpoint of
#: that range and is overridable per-call via ``min_age_minutes``.
DEFAULT_MIN_AGE_MINUTES: float = 60.0


def _dir_creation_epoch(path: Path) -> float | None:
    """Best-effort worktree-directory creation time (epoch seconds).

    Prefers ``st_birthtime`` (macOS/BSD — genuine creation time) and falls
    back to ``st_ctime`` (inode change time — the closest POSIX-portable
    proxy on platforms without a birth time, e.g. most Linux filesystems).
    ``None`` when the path cannot be stat'd (already removed, permission
    error) — the caller treats an unresolvable age as "cannot prove this is
    old enough", never as "assume it's old".
    """
    try:
        st = path.stat()
    except OSError:
        return None
    birth = getattr(st, "st_birthtime", None)
    return float(birth) if birth is not None else float(st.st_ctime)


def _last_commit_epoch(run: GitRunner, branch: str) -> float | None:
    """Epoch seconds of the branch tip's commit time (``%ct``), or ``None``
    when the branch cannot be resolved (never treated as "old")."""
    rc, out, _err = run(["git", "log", "-1", "--format=%ct", branch])
    if rc != 0:
        return None
    lines = (out or "").strip().splitlines()
    if not lines:
        return None
    try:
        return float(lines[0].strip())
    except ValueError:
        return None


def worktree_age_seconds(
    run: GitRunner, wt_path: Path, branch: str, *, now: float | None = None
) -> float | None:
    """Age = ``now - max(worktree dir creation time, last commit time on
    branch)`` — the YOUNGEST of "when the directory appeared" and "when the
    branch last moved" is what actually measures how long ago someone could
    have started working here. ``None`` only when NEITHER source resolves —
    the caller must treat that as "cannot prove this is old enough" (see
    :func:`is_too_young`), never as a silent pass-through.
    """
    candidates: list[float] = []
    c1 = _dir_creation_epoch(wt_path)
    if c1 is not None:
        candidates.append(c1)
    c2 = _last_commit_epoch(run, branch)
    if c2 is not None:
        candidates.append(c2)
    if not candidates:
        return None
    ref_now = now if now is not None else time.time()
    return ref_now - max(candidates)


def is_too_young(
    run: GitRunner,
    wt_path: Path,
    branch: str,
    *,
    min_age_minutes: float = DEFAULT_MIN_AGE_MINUTES,
    now: float | None = None,
) -> tuple[bool, float | None, float]:
    """``(too_young, age_seconds, min_age_seconds)``.

    ``age_seconds`` unresolvable (``None``) is conservatively treated as
    too-young — "cannot prove old enough" refuses removal rather than
    silently assuming a safe age (no-silent-errors, CLAUDE.md §1).
    """
    min_age_seconds = min_age_minutes * 60.0
    age = worktree_age_seconds(run, wt_path, branch, now=now)
    if age is None:
        return True, None, min_age_seconds
    return age < min_age_seconds, age, min_age_seconds


def pointer_status_for_branch(branch: str, run: GitRunner) -> str | None:
    """The latest branch-tree pointer status for ``branch``, or ``None`` when
    no pointer row exists for it.

    Reuses ``branch_pointer.query``'s own latest-per-branch resolution
    (reads ``origin/dev``'s copy of ``project-history/branch-tree.ndjson``)
    rather than re-parsing the ndjson by hand here — one resolver, shared.
    ``run`` is passed straight through as ``branch_pointer.query``'s
    ``runner`` seam (same ``run(["git", ...]) -> (rc, out, err)`` shape
    :func:`make_subprocess_runner` already produces), so callers get the SAME
    repo-root binding they already use for the merge predicate — no second
    git-root resolution, no risk of asking about the wrong tree.
    """
    from tools.noctus.dev import branch_pointer as _bp

    rows = _bp.query(from_dev=True, branch=branch, runner=run)
    return rows[0].get("status") if rows else None


def pointer_blocks_removal(branch: str, run: GitRunner) -> tuple[bool, str | None]:
    """``(blocks, status)`` — ``blocks`` is True iff ``branch`` carries a live
    (non-terminal) branch-tree pointer. This is the STRONGER guard: an
    explicit claim from a peer, never overridden by ``force=True``."""
    from tools.noctus.dev.branch_pointer import TERMINAL_STATUSES

    status = pointer_status_for_branch(branch, run)
    if status is None:
        return False, None
    return status not in TERMINAL_STATUSES, status


__all__ = [
    "GitRunner",
    "PREFERRED_BASE",
    "FALLBACK_BASE",
    "DEFAULT_MIN_AGE_MINUTES",
    "make_subprocess_runner",
    "resolve_merged_base",
    "is_ancestor",
    "all_commits_cherry_picked",
    "is_merged",
    "worktree_age_seconds",
    "is_too_young",
    "pointer_status_for_branch",
    "pointer_blocks_removal",
]
