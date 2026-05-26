"""orphan_branch_sweeper — surface branches without matching project artifacts.

Why this exists
    Long-running noc sessions accumulate branches. Many are integrated +
    pushed to dev but the local branch lingers. Some are abandoned mid-
    flight (engineer killed before completion, integration deferred).
    There's currently no curated view of "which branches can I safely
    delete?"

What it does
    For each local branch:
      - Resolve relationship to origin/dev (ahead/behind).
      - Find any `.claude/worktrees/<slug>/` matching the branch.
      - Find any `project-history/roadmaps/<slug>*.md` matching.
      - Classify:
        - **integrated**: 0 commits ahead of origin/dev → safe to delete.
        - **active-worktree**: has a live worktree on disk → DON'T delete.
        - **stale-no-artifacts**: ahead of dev, no worktree, no roadmap →
          probably abandoned; needs review.
        - **stale-with-roadmap**: ahead of dev, no worktree, but a
          matching roadmap exists → resume work or close roadmap.

Status: read-only by default. `--delete-integrated` flag (CLI) actually
deletes branches classified as `integrated`. Never auto-deletes any
other class.

Composition
    Sibling of `check_branch_orphan` (the existing keeper). This module
    is more detailed: classifies + suggests action, where the keeper
    just flags. Future iteration: promote findings into keeper.

KB § CONTEXT/PATTERNS/common/orphan-branch-sweeper.md.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run_git(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a git command. Returns (rc, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, "", str(e)


def _list_local_branches(repo_root: Path) -> list[str]:
    """Return local branch names (excluding HEAD, excluding current)."""
    rc, out, _err = _run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads/"],
        cwd=repo_root,
    )
    if rc != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _ahead_behind(repo_root: Path, branch: str, base: str = "origin/dev") -> tuple[int, int] | None:
    """Return (ahead, behind) count or None on failure."""
    rc, out, _ = _run_git(
        ["rev-list", "--left-right", "--count", f"{branch}...{base}"],
        cwd=repo_root,
    )
    if rc != 0:
        return None
    parts = out.strip().split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _has_worktree(repo_root: Path, branch: str) -> bool:
    """True if a worktree at .claude/worktrees/<branch-leaf>/ exists."""
    leaf = branch.split("/")[-1]
    return (repo_root / ".claude" / "worktrees" / leaf).is_dir()


def _has_roadmap(repo_root: Path, branch: str) -> str | None:
    """Return matching roadmap path or None."""
    leaf = branch.split("/")[-1]
    roadmaps_dir = repo_root / "project-history" / "roadmaps"
    for sub in (roadmaps_dir, roadmaps_dir / "closed"):
        if not sub.is_dir():
            continue
        for f in sub.glob("*.md"):
            if leaf in f.name:
                try:
                    return str(f.relative_to(repo_root))
                except ValueError:
                    return str(f)
    return None


def scan(repo_root: Path | None = None) -> dict[str, Any]:
    """Classify every local branch by integration / activity state.

    Returns:
      {
        ok: bool,
        current_branch: str,
        branches: [
          {
            name: str,
            ahead: int,             # commits ahead of origin/dev
            behind: int,            # commits behind origin/dev
            has_worktree: bool,
            roadmap_path: str|None,
            classification: 'current' | 'integrated' | 'active-worktree' |
                            'stale-no-artifacts' | 'stale-with-roadmap' |
                            'unknown',
            suggestion: str,        # human-readable action
          },
        ],
      }
    """
    if repo_root is None:
        from settings import REPO_ROOT
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)

    rc, current_out, _ = _run_git(["branch", "--show-current"], cwd=repo_root)
    current = current_out.strip() if rc == 0 else ""

    branches: list[dict[str, Any]] = []
    for name in _list_local_branches(repo_root):
        # Skip the special branches we never want to suggest deleting.
        if name in ("main", "dev"):
            continue
        ab = _ahead_behind(repo_root, name)
        if ab is None:
            branches.append({
                "name": name, "ahead": None, "behind": None,
                "has_worktree": _has_worktree(repo_root, name),
                "roadmap_path": _has_roadmap(repo_root, name),
                "classification": "unknown",
                "suggestion": "could not determine relationship to origin/dev",
            })
            continue
        ahead, behind = ab
        has_wt = _has_worktree(repo_root, name)
        roadmap = _has_roadmap(repo_root, name)
        if name == current:
            cls = "current"
            sugg = "checked out — don't delete from this session"
        elif ahead == 0:
            cls = "integrated"
            sugg = f"safe to delete (0 commits ahead of origin/dev; {behind} behind)"
        elif has_wt:
            cls = "active-worktree"
            sugg = "live worktree exists — finish work or use task_branch cleanup"
        elif roadmap:
            cls = "stale-with-roadmap"
            sugg = f"matching roadmap {roadmap} — resume or close it before deleting"
        else:
            cls = "stale-no-artifacts"
            sugg = f"ahead by {ahead}, no worktree, no roadmap — review before delete"
        branches.append({
            "name": name, "ahead": ahead, "behind": behind,
            "has_worktree": has_wt,
            "roadmap_path": roadmap,
            "classification": cls,
            "suggestion": sugg,
        })
    return {
        "ok": True,
        "current_branch": current,
        "branches": branches,
    }


def delete_integrated(repo_root: Path | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Delete branches classified as `integrated` (0 ahead of origin/dev).

    Args:
      dry_run: when True (default) just LIST what would be deleted.

    Returns:
      {ok, deleted: [...names], skipped: [{name, reason}], errors: [...]}
    """
    if repo_root is None:
        from settings import REPO_ROOT
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)
    result = scan(repo_root=repo_root)
    deleted: list[str] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    for b in result.get("branches", []):
        if b["classification"] != "integrated":
            continue
        if dry_run:
            deleted.append(b["name"])
            continue
        rc, _out, err = _run_git(["branch", "-d", b["name"]], cwd=repo_root)
        if rc == 0:
            deleted.append(b["name"])
        else:
            errors.append({"name": b["name"], "error": err.strip()})
    return {
        "ok": not errors,
        "dry_run": dry_run,
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.orphan_branch_sweep",
        description=(
            "Classify every local branch by integration state vs. origin/dev: "
            "integrated (0 ahead — safe to delete), active-worktree, "
            "stale-with-roadmap, stale-no-artifacts. Sibling of "
            "check_branch_orphan with more detailed classification + "
            "actionable suggestions. Read-only. "
            "KB § CONTEXT/PATTERNS/common/orphan-branch-sweeper.md."
        ),
    )
    def _sweep() -> dict:
        return scan()

    @server.tool(
        name="noctus.dev.orphan_branch_delete_integrated",
        description=(
            "Delete branches classified as `integrated` (0 commits ahead "
            "of origin/dev). Defaults to dry-run; pass `dry_run=False` "
            "to actually delete. Never touches active-worktree / "
            "stale-with-roadmap branches."
        ),
    )
    def _delete(dry_run: bool = True) -> dict:
        return delete_integrated(dry_run=dry_run)


__all__ = ["scan", "delete_integrated", "register"]
