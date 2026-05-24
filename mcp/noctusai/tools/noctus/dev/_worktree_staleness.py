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


__all__ = [
    "GitRunner",
    "PREFERRED_BASE",
    "FALLBACK_BASE",
    "make_subprocess_runner",
    "resolve_merged_base",
    "is_ancestor",
    "all_commits_cherry_picked",
    "is_merged",
]
