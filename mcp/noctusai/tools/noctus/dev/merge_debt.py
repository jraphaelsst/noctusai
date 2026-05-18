"""`noctus.dev.check_merge_debt` — warn before an unmerged-to-main backlog
becomes a base-mismatch lockout.

Behaviour-preserving native port of ``scripts/merge-debt-monitor.sh``.

Why this exists
    Long-lived feature branches accumulate large unmerged-to-``origin/main``
    backlogs. Engineer Agent-worktrees fork stale ``origin/main``, so the
    bigger the backlog the more often a dispatched engineer's base diverges
    from the branch the work actually targets (the WORKTREE-BASE-DIVERGE
    stop). The fix is a phased-push policy; this monitor is the CUSTODIAL
    enforcement sibling of ``check_disk_usage`` — it makes the backlog
    VISIBLE before it bites. Read-only — never mutates git state.

What it computes (for the current branch vs origin/main)
    * ``commits_ahead`` — ``git rev-list --count <base>..HEAD``.
    * ``closed_projects_unmerged`` — commits in that range whose subject
      matches the repo's project-close convention (the canonical
      ``chore(archive): close <slug> — git mv to archive/...`` shape plus
      generic fallbacks). A closed (shipped) project still sitting unmerged
      on a feature branch is exactly the debt the phased-push policy targets.

Exit codes / severity bands (verbatim from the shell — mirrors the
disk-usage-monitor 0/1/2/3 semantics):
    0  — OK       (≤1 closed-project unmerged AND < CAUTION commits)
    1  — CAUTION  (commits-ahead ≥ COMMITS_CAUTION, still 0 closed-projects)
    2  — WARNING  (≥1 closed-project unmerged)
    3  — CRITICAL (≥ CLOSED_CRITICAL closed-projects OR ≥ COMMITS_CRITICAL commits)
"""
from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from settings import REPO_ROOT
from workspace import resolve_caller_root

logger = logging.getLogger(__name__)

_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

# Thresholds — verbatim from scripts/merge-debt-monitor.sh.
_COMMITS_CAUTION = 25   # CAUTION: backlog growing; plan a phased push soon.
_COMMITS_CRITICAL = 60  # CRITICAL: stale-fork divergence near-certain.
_CLOSED_CRITICAL = 3    # CRITICAL: 3+ shipped projects unmerged.

# Project-close convention (derived from `git log` inspection — verbatim
# from the shell CLOSE_RE). Canonical:
#   `chore(archive): close <slug> — git mv to archive/...`
_CLOSE_RE = re.compile(
    r"chore\(archive\)|close .*— git mv to archive|: close "
)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
    )


def check_merge_debt(
    repo_root: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
) -> dict:
    """Report the current branch's unmerged-to-origin/main backlog.

    Behaviour-preserving native port of ``scripts/merge-debt-monitor.sh``.
    Read-only — best-effort ``git fetch origin main`` (does not touch the
    working tree or local branches), then pure ``git rev-list`` / ``git
    log`` reads. No ``force`` arg — this monitor never mutates state (it is
    custodial, surfaces only).

    Args:
        repo_root: repo-root override (test seam). Wins over
            ``worktree_path``.
        worktree_path: caller-aware path resolution (same contract as the
            sibling dev tools).

    Returns:
        ```
        {
          "timestamp": "<YYYY-MM-DD HH:MM:SS>",
          "branch": "<branch>",
          "base": "origin/main" | "main",
          "commits_ahead": int,
          "closed_projects_unmerged": int,
          "severity": "OK"|"CAUTION"|"WARNING"|"CRITICAL",
          "exit_code": 0|1|2|3,        # verbatim shell exit semantics
          "status": same as severity,  # convenience alias
          "next_action": "<action string>",
        }
        ```
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT

    branch = (
        _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "?"
    )

    # Best-effort refresh (read-only — does not touch working tree).
    _git(root, "fetch", "origin", "main", "--quiet")

    # Resolve comparison base: prefer origin/main, fall back to main.
    base = "origin/main"
    if _git(root, "rev-parse", "--verify", "--quiet", base).returncode != 0:
        base = "main"

    ahead_raw = _git(root, "rev-list", "--count", f"{base}..HEAD").stdout.strip()
    try:
        commits_ahead = int(ahead_raw)
    except ValueError:
        commits_ahead = 0

    log_subjects = _git(
        root, "log", "--format=%s", f"{base}..HEAD"
    ).stdout.splitlines()
    closed_unmerged = sum(
        1 for s in log_subjects if _CLOSE_RE.search(s)
    )

    # Severity classification — verbatim from the shell.
    if closed_unmerged >= _CLOSED_CRITICAL or commits_ahead >= _COMMITS_CRITICAL:
        severity, exit_code = "CRITICAL", 3
        next_action = (
            f"phase-push NOW — {closed_unmerged} closed project(s) + "
            f"{commits_ahead} commits unmerged; merge {branch} → main before "
            f"any further dispatch"
        )
    elif closed_unmerged >= 1:
        severity, exit_code = "WARNING", 2
        next_action = (
            f"phase-push before next dispatch — {closed_unmerged} closed "
            f"(shipped) project(s) sitting unmerged on {branch}"
        )
    elif commits_ahead >= _COMMITS_CAUTION:
        severity, exit_code = "CAUTION", 1
        next_action = (
            f"plan a phased push soon — {commits_ahead} commits ahead of "
            f"{base} (stale-fork divergence risk rising)"
        )
    else:
        severity, exit_code = "OK", 0
        next_action = "ok — nothing to do"

    logger.info(
        "check_merge_debt: branch=%s ahead=%d closed=%d severity=%s",
        branch, commits_ahead, closed_unmerged, severity,
    )
    return {
        "timestamp": datetime.now(tz=_LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "branch": branch,
        "base": base,
        "commits_ahead": commits_ahead,
        "closed_projects_unmerged": closed_unmerged,
        "severity": severity,
        "exit_code": exit_code,
        "status": severity,
        "next_action": next_action,
    }


def register(server) -> None:
    """Register the merge-debt monitor MCP tool."""

    @server.tool(
        name="noctus.dev.check_merge_debt",
        description=(
            "Warn before an unmerged-to-origin/main backlog becomes a "
            "base-mismatch (WORKTREE-BASE-DIVERGE) lockout. Computes "
            "commits-ahead + closed-projects-unmerged for the current branch "
            "vs origin/main; preserves scripts/merge-debt-monitor.sh "
            "thresholds (COMMITS_CAUTION=25 / COMMITS_CRITICAL=60 / "
            "CLOSED_CRITICAL=3) + exit semantics (0/1/2/3) as "
            "status+exit_code+next_action. Read-only (never mutates git). "
            "Pass worktree_path when called from inside a git worktree."
        ),
    )
    def _check_merge_debt(worktree_path: str | None = None) -> dict:
        return check_merge_debt(worktree_path=worktree_path)
