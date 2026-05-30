"""remote_branch_hygiene — squash-aware remote branch classifier + guarded deleter.

Why this exists
    Dispatched-engineer worktrees push their branch to `origin` for durability;
    their content is cherry-picked/squashed to `dev`; the remote branch is NEVER
    deleted by any existing tool. Result: 330 dangling remotes accumulated
    (cleaned 2026-05-30). This module prevents re-accumulation.

    `classify_remote_branches()` — read-only, squash-aware.
    `delete_integrated_engineer_remote()` — DESTRUCTIVE, dry_run=True default,
        requires salvage-log entry FIRST, not auto-wired anywhere yet.

Squash-aware classification (critical — raw rev-list lies after squash/cherry-pick)
    1. `integrated` if `git cherry origin/dev <branch>` has zero `+` lines
       (patch-equivalence); OR
    2. `integrated` if the branch-tip subject EXACTLY matches a subject in
       `git log origin/dev` (squash-merge keeps the subject); OR
    3. `unique` otherwise.

    Verdict ∈ `integrated` | `unique` | `protected`.
    Protected: dev / main / prod — always excluded.

Composition
    - `compliance.check_dangling_remote_branches` consumes `classify_remote_branches`.
    - `session_end_sweep.sweep` includes a "remote branches" section via this module.
    - `delete_integrated_engineer_remote` is exposed as `noctus.dev.delete_integrated_remote`
      and MUST be called explicitly by the orchestrator (never auto-fires).

KB § CONTEXT/PATTERNS/common/learn-before-archive.md.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROTECTED_BRANCHES: frozenset[str] = frozenset({"dev", "main", "prod"})


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command. Returns (rc, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        logger.warning("remote_branch_hygiene: git timeout (%s)", e)
        return 1, "", f"timeout: {e}"
    except FileNotFoundError as e:
        logger.error("remote_branch_hygiene: git not found (%s)", e)
        return 1, "", str(e)


def _list_remote_branches(repo_root: Path) -> list[str]:
    """Return remote branch names under origin/ (excluding HEAD)."""
    rc, out, err = _run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/"],
        cwd=repo_root,
    )
    if rc != 0:
        logger.warning("remote_branch_hygiene: cannot list remote branches: %s", err.strip())
        return []
    branches = []
    for ln in out.splitlines():
        name = ln.strip()
        if not name or name == "origin/HEAD":
            continue
        # Strip "origin/" prefix → bare branch name
        if name.startswith("origin/"):
            branches.append(name[len("origin/"):])
    return branches


def _branch_age_days(repo_root: Path, branch: str) -> float | None:
    """Return float age in days of the branch tip commit, or None on failure."""
    rc, out, _ = _run_git(
        ["log", "-1", "--format=%ct", f"origin/{branch}"],
        cwd=repo_root,
    )
    if rc != 0 or not out.strip():
        return None
    try:
        commit_ts = int(out.strip())
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return (now_ts - commit_ts) / 86400.0
    except ValueError:
        return None


def _branch_tip_subject(repo_root: Path, branch: str) -> str | None:
    """Return the commit subject (first line) of the branch tip, or None."""
    rc, out, _ = _run_git(
        ["log", "-1", "--format=%s", f"origin/{branch}"],
        cwd=repo_root,
    )
    if rc != 0 or not out.strip():
        return None
    return out.strip()


def _unique_commits_count(repo_root: Path, branch: str) -> int | None:
    """Return count of commits in origin/<branch> not in origin/dev."""
    rc, out, _ = _run_git(
        ["rev-list", "--count", f"origin/dev..origin/{branch}"],
        cwd=repo_root,
    )
    if rc != 0:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def _dev_subjects(repo_root: Path, max_count: int = 2000) -> frozenset[str]:
    """Return the set of commit subjects from origin/dev (last max_count)."""
    rc, out, _ = _run_git(
        ["log", "--format=%s", f"--max-count={max_count}", "origin/dev"],
        cwd=repo_root,
    )
    if rc != 0:
        return frozenset()
    return frozenset(line.strip() for line in out.splitlines() if line.strip())


def _is_integrated_by_cherry(repo_root: Path, branch: str) -> bool:
    """True if git cherry reports zero `+` lines (patch-equiv with origin/dev)."""
    rc, out, err = _run_git(
        ["cherry", "origin/dev", f"origin/{branch}"],
        cwd=repo_root,
        timeout=60,
    )
    if rc != 0:
        logger.debug(
            "remote_branch_hygiene: git cherry failed for %s: %s", branch, err.strip()
        )
        return False
    # `git cherry` outputs lines starting with `+` (not on dev) or `-` (equiv on dev).
    # Integrated ⟺ zero `+` lines.
    plus_lines = [ln for ln in out.splitlines() if ln.startswith("+")]
    return len(plus_lines) == 0


def classify_remote_branches(
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Classify every origin/* branch (except protected) by integration state.

    Squash-aware: uses git-cherry (patch equivalence) + subject-on-dev
    (squash-merge keeps the original PR subject), NOT raw rev-list count.

    Returns a list of dicts:
      {
        branch: str,            # bare name (no "origin/" prefix)
        verdict: str,           # 'integrated' | 'unique' | 'protected'
        age_days: float | None, # days since tip commit
        subject: str | None,    # tip commit subject
        unique_commits: int | None,  # commits in branch not on dev
      }
    """
    if repo_root is None:
        from settings import REPO_ROOT
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)

    # Fetch to make sure our remote refs are up-to-date.
    rc, _, err = _run_git(["fetch", "origin", "--quiet", "--prune"], cwd=repo_root, timeout=60)
    if rc != 0:
        logger.warning("remote_branch_hygiene: fetch failed (continuing with stale refs): %s", err.strip())

    branches = _list_remote_branches(repo_root)
    dev_subs = _dev_subjects(repo_root)

    results: list[dict[str, Any]] = []
    for branch in sorted(branches):
        if branch in _PROTECTED_BRANCHES:
            results.append({
                "branch": branch,
                "verdict": "protected",
                "age_days": None,
                "subject": None,
                "unique_commits": None,
            })
            continue

        age = _branch_age_days(repo_root, branch)
        subject = _branch_tip_subject(repo_root, branch)
        unique_count = _unique_commits_count(repo_root, branch)

        # Squash-aware integration check — two independent heuristics:
        # (1) git cherry: patch-level equivalence (catches cherry-pick replay)
        # (2) subject match: squash-merged PRs keep the first commit's subject
        integrated = False
        if _is_integrated_by_cherry(repo_root, branch):
            integrated = True
        elif subject and subject in dev_subs:
            integrated = True

        results.append({
            "branch": branch,
            "verdict": "integrated" if integrated else "unique",
            "age_days": round(age, 1) if age is not None else None,
            "subject": subject,
            "unique_commits": unique_count,
        })

    return results


def delete_integrated_engineer_remote(
    branch: str,
    repo_root: Path | None = None,
    dry_run: bool = True,
    salvage_log_required: bool = True,
) -> dict[str, Any]:
    """Delete origin/<branch> ONLY when ALL guards pass.

    Guards (all must hold):
      (a) classify_remote_branches says verdict == 'integrated'
      (b) branch is NOT protected (dev / main / prod)
      (c) salvage_before_delete logged an entry (when salvage_log_required=True)

    dry_run=True (DEFAULT): reports what would be deleted, never runs `git push --delete`.
    Do NOT call this automatically — expose only via the explicit MCP tool.

    Returns:
      {ok, dry_run, branch, action, reason}
      action ∈ 'would-delete' | 'deleted' | 'skipped'
      reason: human-readable why
    """
    if repo_root is None:
        from settings import REPO_ROOT
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)

    if branch in _PROTECTED_BRANCHES:
        return {
            "ok": False,
            "dry_run": dry_run,
            "branch": branch,
            "action": "skipped",
            "reason": f"branch '{branch}' is protected — will NEVER be deleted by this tool",
        }

    # Classify (fetch happens inside classify_remote_branches).
    classifications = classify_remote_branches(repo_root=repo_root)
    entry = next((c for c in classifications if c["branch"] == branch), None)
    if entry is None:
        return {
            "ok": False,
            "dry_run": dry_run,
            "branch": branch,
            "action": "skipped",
            "reason": f"branch 'origin/{branch}' not found in remote refs",
        }

    if entry["verdict"] != "integrated":
        return {
            "ok": False,
            "dry_run": dry_run,
            "branch": branch,
            "action": "skipped",
            "reason": (
                f"branch has unique_commits={entry['unique_commits']} — "
                f"verdict={entry['verdict']}; run salvage_before_delete first to "
                f"archive the unique content, then re-classify"
            ),
        }

    # Salvage-log gate — verify a salvage entry exists for this branch.
    if salvage_log_required:
        salvage_ok = _check_salvage_log(repo_root, branch)
        if not salvage_ok:
            return {
                "ok": False,
                "dry_run": dry_run,
                "branch": branch,
                "action": "skipped",
                "reason": (
                    f"no salvage-log entry found for branch '{branch}' in "
                    "project-history/worktree-salvage.ndjson — call "
                    "`noctus.dev.salvage_before_delete(target='{branch}', kind='branch')` "
                    "first, even for integrated content (preserves recovery pointer)"
                ),
            }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "branch": branch,
            "action": "would-delete",
            "reason": (
                f"DRY-RUN: would run `git push origin --delete {branch}` "
                f"(age={entry['age_days']}d, unique_commits={entry['unique_commits']}, "
                f"subject='{entry['subject']}'). Pass dry_run=False to execute."
            ),
        }

    # Execute the delete.
    rc, _, err = _run_git(
        ["push", "origin", "--delete", branch],
        cwd=repo_root,
        timeout=60,
    )
    if rc != 0:
        logger.error(
            "remote_branch_hygiene: git push --delete %s failed: %s", branch, err.strip()
        )
        return {
            "ok": False,
            "dry_run": False,
            "branch": branch,
            "action": "skipped",
            "reason": f"git push --delete failed: {err.strip()[:200]}",
        }

    logger.info("remote_branch_hygiene: deleted origin/%s", branch)
    return {
        "ok": True,
        "dry_run": False,
        "branch": branch,
        "action": "deleted",
        "reason": f"deleted origin/{branch} (integrated, salvage-logged)",
    }


def _check_salvage_log(repo_root: Path, branch: str) -> bool:
    """Return True if a salvage-log entry mentions this branch."""
    import json
    ledger = repo_root / "project-history" / "worktree-salvage.ndjson"
    if not ledger.exists():
        return False
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Check common fields where a branch name might appear.
            if (
                entry.get("target") == branch
                or entry.get("branch") == branch
                or branch in str(entry.get("targets", []))
                or branch in str(entry.get("branches_processed", []))
            ):
                return True
    except OSError as e:
        logger.warning("remote_branch_hygiene: cannot read salvage ledger: %s", e)
    return False


# ── MCP registration ──────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.classify_remote_branches",
        description=(
            "Squash-aware remote branch classifier. For each origin/* head "
            "EXCEPT dev/main/prod: returns verdict ∈ integrated | unique | protected, "
            "age_days, tip subject, and unique_commits count. "
            "Integration check uses git-cherry (patch-equivalence) + subject-on-dev "
            "(squash-merge detection) — NOT raw rev-list which lies after squash/cherry-pick. "
            "Read-only. Fetches from origin before classifying. "
            "KB § CONTEXT/PATTERNS/common/learn-before-archive.md."
        ),
    )
    def _classify() -> list[dict]:
        return classify_remote_branches()

    @server.tool(
        name="noctus.dev.delete_integrated_remote",
        description=(
            "DESTRUCTIVE — delete origin/<branch> only when ALL guards pass: "
            "(a) branch is classified 'integrated' by squash-aware git-cherry + subject check, "
            "(b) not protected (dev/main/prod), "
            "(c) a salvage-log entry exists. "
            "dry_run=True (DEFAULT) — only reports what would be deleted. "
            "Set dry_run=False ONLY with explicit tech-lead approval. "
            "NOT auto-wired anywhere — orchestrator must call explicitly. "
            "KB § CONTEXT/PATTERNS/common/learn-before-archive.md."
        ),
    )
    def _delete(branch: str, dry_run: bool = True) -> dict:
        return delete_integrated_engineer_remote(branch=branch, dry_run=dry_run)


__all__ = ["classify_remote_branches", "delete_integrated_engineer_remote", "register"]
