"""salvage_before_delete — mandatory pre-delete gate for any artifact.

Why this exists
    Before ANY destructive op (branch-delete / worktree-remove / file-delete /
    project-archive), this tool runs the learn-before-archive gate:

      1. Code/diffs    → archive as git format-patch (re-appliable via `git am`).
                         Skip when content is patch-equivalent on origin/dev.
      2. Lessons/docs  → absorbed by the caller into KB/memory (this tool logs
                         the obligation; absorption is the caller's responsibility).
      3. Recovery pointer → append a salvage-ndjson entry so the artifact can be
                         re-created from first principles.
      4. No dangling pointers left behind.

    Default dry_run=True — reports what would be preserved, never writes.

    For `kind='branch'`: runs git format-patch for any unique content, writes
    the patch archive under `project-history/orphan-remote-archive-<date>/`,
    and appends the ledger entry.

Composes with
    - `remote_branch_hygiene.delete_integrated_engineer_remote` (calls this first)
    - `orphan_branch_sweeper` (local analogue)
    - `session_end_sweep` (surfaces salvage obligations)

KB § CONTEXT/PATTERNS/common/learn-before-archive.md.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 60) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        logger.warning("salvage_before_delete: git timeout (%s)", e)
        return 1, "", f"timeout: {e}"
    except FileNotFoundError as e:
        logger.error("salvage_before_delete: git not found (%s)", e)
        return 1, "", str(e)


def _is_integrated_on_dev(repo_root: Path, ref: str) -> bool:
    """True if ref has no unique commits vs origin/dev (patch-equivalence via cherry)."""
    rc, out, err = _run_git(
        ["cherry", "origin/dev", ref],
        cwd=repo_root,
        timeout=60,
    )
    if rc != 0:
        logger.debug("salvage_before_delete: git cherry failed for %s: %s", ref, err.strip())
        return False
    plus_lines = [ln for ln in out.splitlines() if ln.startswith("+")]
    return len(plus_lines) == 0


def _unique_commit_count(repo_root: Path, ref: str) -> int:
    rc, out, _ = _run_git(
        ["rev-list", "--count", f"origin/dev..{ref}"],
        cwd=repo_root,
    )
    if rc != 0:
        return 0
    try:
        return int(out.strip())
    except ValueError:
        return 0


def _archive_branch_patch(
    repo_root: Path,
    branch: str,
    archive_dir: Path,
) -> dict[str, Any]:
    """Run git format-patch for unique commits in origin/<branch> vs origin/dev.

    Returns {ok, patch_files, skipped_reason}.
    """
    remote_ref = f"origin/{branch}"

    # Verify the ref exists.
    rc, _, _ = _run_git(["rev-parse", "--verify", remote_ref], cwd=repo_root)
    if rc != 0:
        return {"ok": False, "patch_files": [], "skipped_reason": f"{remote_ref} not found"}

    if _is_integrated_on_dev(repo_root, remote_ref):
        return {
            "ok": True,
            "patch_files": [],
            "skipped_reason": "content patch-equivalent on origin/dev — no patch needed",
        }

    archive_dir.mkdir(parents=True, exist_ok=True)
    rc, out, err = _run_git(
        ["format-patch", "origin/dev..{ref}".format(ref=remote_ref),
         "--output-directory", str(archive_dir)],
        cwd=repo_root,
        timeout=120,
    )
    if rc != 0:
        logger.error("salvage_before_delete: format-patch failed for %s: %s", branch, err.strip())
        return {"ok": False, "patch_files": [], "skipped_reason": f"format-patch failed: {err.strip()[:200]}"}

    patch_files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return {"ok": True, "patch_files": patch_files, "skipped_reason": None}


def _append_salvage_ledger(repo_root: Path, entry: dict[str, Any]) -> None:
    """Append entry to project-history/worktree-salvage.ndjson."""
    ledger = repo_root / "project-history" / "worktree-salvage.ndjson"
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("salvage_before_delete: cannot write salvage ledger: %s", e)


def salvage_before_delete(
    target: str,
    kind: str,
    repo_root: Path | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Pre-delete salvage gate for any artifact.

    Args:
      target: the artifact identifier.
        - kind='branch': bare branch name (no 'origin/' prefix)
        - kind='worktree': slug / path under .claude/worktrees/
        - kind='path': absolute or repo-relative file/dir path
        - kind='project': project slug under projects/
      kind: 'branch' | 'worktree' | 'path' | 'project'
      dry_run: when True (default), reports what would be preserved without writing.

    Returns:
      {
        ok: bool,
        dry_run: bool,
        target: str,
        kind: str,
        preserved: list[str],  # descriptions of what was/would be preserved
        ledger_entry_written: bool,
        warnings: list[str],
      }
    """
    if repo_root is None:
        from settings import REPO_ROOT
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)

    preserved: list[str] = []
    warnings: list[str] = []
    ledger_entry_written = False

    if kind == "branch":
        result = _salvage_branch(
            target=target,
            repo_root=repo_root,
            dry_run=dry_run,
            preserved=preserved,
            warnings=warnings,
        )
    elif kind == "worktree":
        result = _salvage_worktree_path(
            target=target,
            repo_root=repo_root,
            dry_run=dry_run,
            preserved=preserved,
            warnings=warnings,
        )
    elif kind in ("path", "project"):
        result = _salvage_generic(
            target=target,
            kind=kind,
            repo_root=repo_root,
            dry_run=dry_run,
            preserved=preserved,
            warnings=warnings,
        )
    else:
        return {
            "ok": False,
            "dry_run": dry_run,
            "target": target,
            "kind": kind,
            "preserved": [],
            "ledger_entry_written": False,
            "warnings": [f"unknown kind '{kind}' — expected branch|worktree|path|project"],
        }

    # Append salvage ledger entry (in live mode, or log in dry-run).
    ledger_entry: dict[str, Any] = {
        "ts": _now_iso(),
        "kind": f"salvage-before-delete:{kind}",
        "target": target,
        "dry_run": dry_run,
        "ok": result.get("ok", True),
        "preserved": preserved,
    }
    if not dry_run:
        _append_salvage_ledger(repo_root, ledger_entry)
        ledger_entry_written = True
    else:
        logger.debug("salvage_before_delete: DRY-RUN — would write ledger entry: %s", ledger_entry)

    return {
        "ok": result.get("ok", True),
        "dry_run": dry_run,
        "target": target,
        "kind": kind,
        "preserved": preserved,
        "ledger_entry_written": ledger_entry_written,
        "warnings": warnings,
        **{k: v for k, v in result.items() if k not in ("ok",)},
    }


def _salvage_branch(
    target: str,
    repo_root: Path,
    dry_run: bool,
    preserved: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Salvage a remote branch."""
    remote_ref = f"origin/{target}"

    # Verify ref exists.
    rc, tip_sha, _ = _run_git(["rev-parse", "--verify", remote_ref], cwd=repo_root)
    if rc != 0:
        warnings.append(f"{remote_ref} not found in remote refs — may already be deleted")
        return {"ok": True, "tip_sha": None, "patch_archive_dir": None}

    tip_sha = tip_sha.strip()

    # Get subject for the ledger.
    _, subject_out, _ = _run_git(["log", "-1", "--format=%s", remote_ref], cwd=repo_root)
    subject = subject_out.strip()

    # Get unique commit count.
    unique_count = _unique_commit_count(repo_root, remote_ref)
    preserved.append(f"recovery-pointer: origin/{target} @ {tip_sha[:12]} ({unique_count} unique commits, subject='{subject}')")

    patch_archive_dir: str | None = None
    patch_files: list[str] = []

    if unique_count > 0:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        archive_dir = repo_root / "project-history" / f"orphan-remote-archive-{date_str}"
        branch_archive_dir = archive_dir / target.replace("/", "_")

        if dry_run:
            preserved.append(
                f"DRY-RUN: would archive {unique_count} unique commits to "
                f"{branch_archive_dir.relative_to(repo_root)}"
            )
            patch_archive_dir = str(branch_archive_dir)
        else:
            arch_result = _archive_branch_patch(
                repo_root=repo_root,
                branch=target,
                archive_dir=branch_archive_dir,
            )
            if arch_result["ok"] and arch_result["patch_files"]:
                patch_files = arch_result["patch_files"]
                preserved.append(
                    f"patch-archive: {len(patch_files)} patches written to "
                    f"{branch_archive_dir.relative_to(repo_root)}"
                )
                patch_archive_dir = str(branch_archive_dir)
            elif arch_result["skipped_reason"]:
                preserved.append(f"patch-archive: skipped — {arch_result['skipped_reason']}")
            else:
                warnings.append(f"patch-archive failed: {arch_result.get('skipped_reason', 'unknown')}")
    else:
        preserved.append("patch-archive: skipped — 0 unique commits (content on dev)")

    return {
        "ok": True,
        "tip_sha": tip_sha,
        "subject": subject,
        "unique_commits": unique_count,
        "patch_archive_dir": patch_archive_dir,
        "patch_files": patch_files,
    }


def _salvage_worktree_path(
    target: str,
    repo_root: Path,
    dry_run: bool,
    preserved: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Salvage a worktree slug or path."""
    wt_path = repo_root / ".claude" / "worktrees" / target
    if not wt_path.exists():
        # Try as an absolute path.
        wt_path = Path(target)
    if not wt_path.exists():
        warnings.append(f"worktree path '{target}' not found — may already be removed")
        return {"ok": True}

    # Get the branch name.
    rc, branch_ref, _ = _run_git(["symbolic-ref", "HEAD"], cwd=wt_path)
    branch = branch_ref.strip().removeprefix("refs/heads/") if rc == 0 else "<detached>"
    preserved.append(f"recovery-pointer: worktree slug={wt_path.name} branch={branch}")

    # Check for uncommitted changes.
    rc, dirty_out, _ = _run_git(["status", "--porcelain"], cwd=wt_path)
    if rc == 0 and dirty_out.strip():
        dirty_files = [ln.strip() for ln in dirty_out.strip().splitlines() if ln.strip()]
        warnings.append(
            f"worktree has {len(dirty_files)} uncommitted file(s): "
            f"{', '.join(dirty_files[:5])}{'...' if len(dirty_files) > 5 else ''}"
        )
        if dry_run:
            preserved.append(f"DRY-RUN: would surface {len(dirty_files)} uncommitted change(s)")
        else:
            preserved.append(f"WARNING: {len(dirty_files)} uncommitted changes will be lost — "
                             "manually commit or extract before removing this worktree")

    return {"ok": True, "worktree_path": str(wt_path), "branch": branch}


def _salvage_generic(
    target: str,
    kind: str,
    repo_root: Path,
    dry_run: bool,
    preserved: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Generic salvage for path/project kinds — records a recovery pointer."""
    path = Path(target) if Path(target).is_absolute() else repo_root / target
    if not path.exists():
        warnings.append(f"path '{target}' not found — may already be deleted")
        return {"ok": True}

    preserved.append(f"recovery-pointer: {kind}={target} exists at {path}")

    if kind == "project":
        # Check for unabsorbed findings.md / PROJECT.md.
        for fname in ("findings.md", "PROJECT.md", "FINDINGS.md"):
            fpath = path / fname
            if fpath.exists():
                preserved.append(
                    f"absorption-obligation: {target}/{fname} contains durable context "
                    "— absorb to KB/memory before deleting (learn-before-archive gate)"
                )
    return {"ok": True}


# ── MCP registration ──────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.salvage_before_delete",
        description=(
            "Pre-delete salvage gate (learn-before-archive). Before ANY destructive op "
            "(branch-delete / worktree-remove / file-delete / project-archive), call this "
            "to: (1) archive unique code as git format-patch under project-history/; "
            "(2) record a recovery pointer in project-history/worktree-salvage.ndjson; "
            "(3) surface absorption obligations for lessons/docs. "
            "dry_run=True (DEFAULT) — reports what would be preserved without writing. "
            "kind ∈ 'branch' | 'worktree' | 'path' | 'project'. "
            "KB § CONTEXT/PATTERNS/common/learn-before-archive.md."
        ),
    )
    def _salvage(target: str, kind: str, dry_run: bool = True) -> dict:
        return salvage_before_delete(target=target, kind=kind, dry_run=dry_run)


__all__ = ["salvage_before_delete", "register"]
