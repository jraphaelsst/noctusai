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
        - **protected**: `main` / `dev` / `prod` / `prod-backup` — NEVER
          deletable. A release branch is 0-ahead of dev by definition, so
          the `integrated` rule below would otherwise mark production as
          the most disposable branch in the repo.
        - **active-worktree**: has a live worktree on disk → DON'T delete.
          Checked BEFORE `integrated`, and deliberately: the ordinary end
          state of a dispatch is "integrated to dev, worktree still on
          disk", so the integrated rule would otherwise claim every live
          worktree's branch was safe to delete.
        - **integrated**: 0 commits ahead of origin/dev, no worktree →
          safe to delete.
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


#: Branches that must NEVER be suggested for deletion, whatever their
#: relationship to `origin/dev`.
#:
#: 🔴 `prod` is the entry this exists for. The classifier's rule is
#: "0 commits ahead of origin/dev ⇒ integrated ⇒ safe to delete", and a
#: release branch is 0-ahead **by definition** — it trails dev, it never
#: leads it. So the production branch scored as the most disposable thing
#: in the repo, and `git branch -d prod` would have SUCCEEDED: `-d`
#: refuses only unmerged branches, and prod is fully merged into dev.
#: Observed on 2026-08-21, when a sweep reported
#: "prod — safe to delete (0 commits ahead of origin/dev; 569 behind)".
#:
#: `main` and `dev` were already skipped, which is precisely why nobody
#: noticed `prod` was missing: they were dropped SILENTLY, so the output
#: never showed which branches the guard covered. They are now classified
#: and RETURNED as `protected` instead — a visible row is auditable, a
#: silent `continue` is not.
PROTECTED_BRANCHES: frozenset[str] = frozenset(
    {"main", "dev", "prod", "prod-backup"}
)


def is_protected(branch: str) -> bool:
    """True if `branch` must never be auto-deleted.

    Exposed so callers guard on the same predicate the classifier uses,
    rather than re-deriving a list that drifts out of sync with this one.
    """
    return branch in PROTECTED_BRANCHES


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
            classification: 'protected' | 'current' | 'integrated' |
                            'active-worktree' | 'stale-no-artifacts' |
                            'stale-with-roadmap' | 'unknown',
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
        # Protected branches are CLASSIFIED, not skipped. The previous
        # `continue` hid them from the output entirely, which is how the
        # missing `prod` entry went unnoticed — you cannot audit a list
        # for a gap it never shows you.
        if is_protected(name):
            ab_p = _ahead_behind(repo_root, name)
            branches.append({
                "name": name,
                "ahead": ab_p[0] if ab_p else None,
                "behind": ab_p[1] if ab_p else None,
                "has_worktree": _has_worktree(repo_root, name),
                "roadmap_path": _has_roadmap(repo_root, name),
                "classification": "protected",
                "suggestion": (
                    "NEVER delete — protected branch. A release branch is "
                    "0-ahead of dev by definition, so the integrated "
                    "heuristic does not apply to it."
                ),
            })
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
        elif has_wt:
            # 🔴 A live worktree outranks the integrated heuristic, and the
            # order of these two arms is the whole rule. `ahead == 0` used to
            # win, so the NORMAL end-state of a dispatch — work integrated to
            # dev, worktree still on disk — was reported "safe to delete"
            # while the row's own `has_worktree: true` said otherwise. The
            # tool contradicted itself, and `delete_integrated` then ran
            # `git branch -d` on it, which git REFUSES for a branch held by a
            # worktree ("cannot delete branch 'x' used by worktree at …",
            # verified 2026-08-22) — so every such branch became an entry in
            # `errors` and flipped the whole sweep's `ok` to False.
            #
            # Nothing was ever destroyed; git's own guard saw to that. What
            # was wrong is the advice, and advice is this tool's entire
            # product. Reaping a worktree-backed branch is `task_branch
            # cleanup` / `cleanup_stale_worktrees` — both refuse a DIRTY
            # tree, which a bare `git branch -d` never checks.
            cls = "active-worktree"
            sugg = (
                "live worktree exists — finish work or use task_branch cleanup"
                if ahead
                else (
                    f"live worktree exists and the branch is integrated "
                    f"({behind} behind) — reap it via task_branch cleanup / "
                    f"cleanup_stale_worktrees, which refuse a dirty tree; a "
                    f"bare `git branch -d` does not, and git refuses it anyway"
                )
            )
        elif ahead == 0:
            cls = "integrated"
            sugg = f"safe to delete (0 commits ahead of origin/dev; {behind} behind)"
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

    Protected branches (`PROTECTED_BRANCHES`) are refused here as well as
    excluded by `scan`, so a classifier regression cannot reach them.

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
        # 🔴 Belt AND braces. `scan` already classifies protected branches
        # as `protected`, so this can only fire if the classifier
        # regresses — which is exactly the failure that shipped once
        # already. The guard lives at the point of consequence too,
        # because a classification bug must not be one step away from
        # `git branch -d prod`.
        if is_protected(b["name"]):
            skipped.append({
                "name": b["name"],
                "reason": "protected branch — never auto-deleted",
            })
            continue
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
            "protected (main/dev/prod/prod-backup — NEVER deletable), "
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
            "stale-with-roadmap branches, and REFUSES the protected set "
            "(main/dev/prod/prod-backup) independently of classification."
        ),
    )
    def _delete(dry_run: bool = True) -> dict:
        return delete_integrated(dry_run=dry_run)


__all__ = [
    "PROTECTED_BRANCHES",
    "delete_integrated",
    "is_protected",
    "register",
    "scan",
]
