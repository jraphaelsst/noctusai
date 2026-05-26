"""`noctus.dev.cleanup_stale_worktrees` — remove merged engineer worktrees.

Behaviour-preserving native port of ``scripts/cleanup-stale-worktrees.sh``.

Why this exists
    Each ``Agent(isolation: "worktree")`` call creates a worktree at
    ``.claude/worktrees/agent-<id>/`` (hydrated with node_modules + Python
    venvs). The orchestrator integrates to dev; the worktree stays on disk
    ~880 MiB each. 75 stale worktrees = 67 GiB unrecoverable until cleanup.

What "stale" means (shared predicate — ``_worktree_staleness``, the SAME
core ``noctus.dev.mole``'s worktree scope consumes)
    Any worktree under ``.claude/worktrees/`` (an ``agent-<id>`` from
    ``Agent(isolation:"worktree")`` OR a self-branch ``feat/<slug>`` from
    ``task_branch`` / a raw ``git worktree add``) whose branch is either:
      (a) reachable from ``origin/dev`` by SHA ancestry (true merge), OR
      (b) all commits already present on ``origin/dev`` by PATCH-ID
          (cherry-pick — the orchestrator integrates via cherry-pick: new
          SHA, same patch; ``git cherry`` is the patch-id equivalent).
    Engineer worktrees fork from + integrate to the ``dev`` integration
    branch, NOT ``main`` (KB § PATTERNS/branching-and-merging.md § 0) — a
    merged-to-dev-but-not-yet-blessed-to-main worktree was never swept under
    the old ``origin/main`` keying. Unmerged work-in-progress worktrees are
    KEPT.

Safety (identical contract — the THE-P10 / THE-P11 lessons)
    * Never removes the main worktree.
    * Never removes sibling workspaces (paths NOT under
      ``.claude/worktrees/``).
    * Refuses to remove worktrees with uncommitted files or stashes —
      surfaces them as ``dirty`` manual-review findings. ``force=True`` does
      NOT override this (it only suppresses the interactive prompt).
    * Shared-stash subtraction: linked worktrees share ``refs/stash`` with
      main; main's stashes are subtracted before counting a worktree's WIP
      (THE-P11 false-positive fix).
    * Locked worktrees with a live PID are never destroyed; a lock held by a
      DEAD pid is auto-unlocked (THE-P11 fix). Git's safe ``worktree remove
      --force`` is used; a refusal surfaces the path as ``locked_skipped`` —
      NEVER ``rm -rf`` a git-registered locked path (THE-P10 lesson). Only
      TRUE orphans (on-disk dir git doesn't know about) get a direct rmtree.
    * Always ``git worktree prune`` after removal.

Dry-run unless ``force=True`` (the shell ``--dry-run``/``--force`` split;
``interactive`` mode is not portable to a tool call — default is dry-run).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root
from tools.noctus.dev import _worktree_staleness as wts
from tools.noctus.dev import _worktree_salvage as wsv

logger = logging.getLogger(__name__)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
    )


def _pid_alive(pid: int) -> bool:
    """True if ``pid`` is a live process (mirrors the shell ``kill -0``)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours — still alive
    except OSError:
        return False
    return True


def _registered_worktrees(root: Path) -> list[tuple[str, str | None, bool, str]]:
    """Parse ``git worktree list --porcelain``.

    Returns [(path, branch_or_None, locked_bool, lock_reason), ...]. Mirrors
    the shell's block parser (worktree / branch / locked lines, blank-line
    separated).
    """
    out = _git(root, "worktree", "list", "--porcelain").stdout
    entries: list[tuple[str, str | None, bool, str]] = []
    wt: str | None = None
    branch: str | None = None
    locked = False
    lock_reason = ""

    def flush() -> None:
        nonlocal wt, branch, locked, lock_reason
        if wt is not None:
            entries.append((wt, branch, locked, lock_reason))
        wt = None
        branch = None
        locked = False
        lock_reason = ""

    for line in out.splitlines():
        if line.startswith("worktree "):
            flush()
            wt = line[len("worktree "):]
        elif line.startswith("branch "):
            branch = line[len("branch refs/heads/"):]
        elif line.startswith("locked"):
            locked = True
            lock_reason = line[len("locked"):].strip()
        elif line == "":
            flush()
    flush()
    return entries


def cleanup_stale_worktrees(
    repo_root: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
    force: bool = False,
) -> dict:
    """Classify + (when ``force``) remove merged-to-dev agent worktrees.

    Behaviour-preserving native port of
    ``scripts/cleanup-stale-worktrees.sh``. **Dry-run unless
    ``force=True``** — default classifies and returns the buckets but
    removes nothing. ``force=True`` performs ``git worktree remove --force``
    on the stale set (NEVER overrides the dirty/locked safety gates).

    Args:
        repo_root: repo-root override (test seam). Wins over
            ``worktree_path``.
        worktree_path: caller-aware path resolution (same contract as the
            sibling dev tools).
        force: ``False`` (default) → dry-run classification only; ``True``
            → remove the stale set (safety gates still apply).

    Returns:
        ```
        {
          "main": "<repo root>",
          "active": [...],          # unmerged — kept (WIP)
          "dirty": [{"path": ..., "reason": ...}, ...],  # merged + work
          "locked": [...],          # merged + lock held — manual review
          "stale": [...],           # safe to auto-remove (merged + clean)
          "removed": int,           # 0 when dry_run
          "failed": int,
          "locked_skipped": [...],  # git refused (lock/active) — never rm'd
          "dry_run": bool,          # True == not force
          "status": "nothing"|"dry_run"|"removed",
        }
        ```
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT

    worktree_dir = root / ".claude" / "worktrees"

    if not worktree_dir.is_dir():
        return {
            "main": str(root),
            "active": [],
            "dirty": [],
            "locked": [],
            "stale": [],
            "removed": 0,
            "failed": 0,
            "locked_skipped": [],
            "dry_run": not force,
            "status": "nothing",
            "salvage_ledger": None,
            "salvaged": 0,
        }

    # Refresh dev's tip (best-effort, read-only). Engineer worktrees integrate
    # to the dev integration branch, not main (KB § branching-and-merging § 0).
    _git(root, "fetch", "origin", "dev", "--quiet")

    # Resolve comparison base (prefer origin/dev, fall back to dev) + the
    # merged predicate via the shared _worktree_staleness helper — the single
    # source of truth shared with noctus.dev.mole's worktree scope.
    wts_run = wts.make_subprocess_runner(root)
    base = wts.resolve_merged_base(wts_run)

    # Snapshot main-repo stashes for shared-stash subtraction (THE-P11).
    main_stashes = set(
        ln for ln in _git(
            root, "stash", "list", "--pretty=%H"
        ).stdout.splitlines() if ln.strip()
    )

    active: list[str] = []
    dirty: list[dict] = []
    locked: list[str] = []
    stale: list[str] = []

    worktrees_root = str(worktree_dir) + os.sep

    def classify(wt: str, branch: str | None, is_locked: bool, lock_reason: str) -> None:
        # Main repo or sibling workspace: ignore.
        if wt == str(root):
            return
        # Any worktree under .claude/worktrees/ (was `agent-*` only — which
        # left raw `git worktree add` + `task_branch` feat/<slug> self-branch
        # worktrees un-sweepable, the 2026-05-25 bare-`worktree remove`
        # hazard). The merged-to-dev + clean + unlocked gates below are the
        # real safety; the NAME was never the protection. Main repo + sibling
        # workspaces live OUTSIDE .claude/worktrees/, so they stay excluded.
        if not wt.startswith(worktrees_root):
            return
        if branch is None:
            return

        # Auto-unlock dead-pid locks (THE-P11). "(pid N)" with a dead pid.
        nonlocal_locked = is_locked
        if is_locked and "(pid " in lock_reason:
            try:
                pid = int(lock_reason.split("(pid ")[1].split(")")[0])
            except (IndexError, ValueError):
                pid = None
            if pid is not None and not _pid_alive(pid):
                if _git(root, "worktree", "unlock", wt).returncode == 0:
                    nonlocal_locked = False

        # Merge predicate (shared helper): ancestry OR patch-id equivalence.
        merged = wts.is_merged(wts_run, branch, base)
        if not merged:
            active.append(wt)
            return

        wt_path = Path(wt)
        # Merged + on-disk dir gone → PHANTOM, safe to remove.
        if not wt_path.is_dir():
            stale.append(wt)
            return

        # On-disk + merged. Check uncommitted / stashed / locked.
        status = _git(wt_path, "status", "--porcelain")
        n_dirty = len([ln for ln in status.stdout.splitlines() if ln.strip()])

        wt_stashes = set(
            ln for ln in _git(
                wt_path, "stash", "list", "--pretty=%H"
            ).stdout.splitlines() if ln.strip()
        )
        unique_stashes = len(wt_stashes - main_stashes)

        if n_dirty != 0:
            dirty.append({
                "path": wt,
                "reason": f"{n_dirty} uncommitted file(s) — INVESTIGATE before removing",
            })
        elif unique_stashes != 0:
            dirty.append({
                "path": wt,
                "reason": f"{unique_stashes} stash(es) — recover before removing",
            })
        elif nonlocal_locked:
            locked.append(wt)
        else:
            stale.append(wt)

    for wt, branch, is_locked, lock_reason in _registered_worktrees(root):
        classify(wt, branch, is_locked, lock_reason)

    # Orphan detection: on-disk `agent-*` dir NOT in `git worktree list`.
    # Stays `agent-*` CONSERVATIVE on purpose — an orphan (unregistered) dir
    # has no branch ⇒ NO merge gate, so only sweep ones unmistakably ours.
    # Registered worktrees of ANY name are handled by classify() above, where
    # the merged + clean gate is the real safety.
    registered_paths = {
        e[0] for e in _registered_worktrees(root)
    }
    for child in sorted(worktree_dir.iterdir()):
        if not child.is_dir() or not child.name.startswith("agent-"):
            continue
        if str(child) not in registered_paths:
            stale.append(str(child))

    # Dedupe stale (preserve order).
    seen: set[str] = set()
    stale = [p for p in stale if not (p in seen or seen.add(p))]

    if not stale:
        return {
            "main": str(root),
            "active": active,
            "dirty": dirty,
            "locked": locked,
            "stale": [],
            "removed": 0,
            "failed": 0,
            "locked_skipped": [],
            "dry_run": not force,
            "status": "nothing",
            "salvage_ledger": None,
            "salvaged": 0,
        }

    if not force:
        return {
            "main": str(root),
            "active": active,
            "dirty": dirty,
            "locked": locked,
            "stale": stale,
            "removed": 0,
            "failed": 0,
            "locked_skipped": [],
            "dry_run": True,
            "status": "dry_run",
            "salvage_ledger": None,
            "salvaged": 0,
        }

    # Recovery metadata (branch + SHA) captured BEFORE removal — the mechanical
    # "recovery record → tracked ledger" leg of learn/extract-before-delete
    # (KB § PATTERNS/storage-hygiene.md § 2.3). Stale = merged-to-dev, so this is
    # the recovery pointer + provenance, not a diff-salvage (no dirty in `stale`).
    branch_of = {e[0]: e[1] for e in _registered_worktrees(root)}
    recovery = {
        wt: {
            "path": wt,
            "branch": branch_of.get(wt),
            "sha": wsv.branch_sha(root, branch_of.get(wt)),
            "reason": "merged-to-dev",
        }
        for wt in stale
    }

    removed = 0
    failed = 0
    locked_skipped: list[str] = []
    removed_records: list[dict] = []
    for wt in stale:
        if _git(root, "worktree", "remove", "--force", wt).returncode == 0:
            removed += 1
            removed_records.append(recovery[wt])
            continue
        # git refused. Distinguish locked/active (NEVER rm -rf — THE-P10)
        # from true orphan (git doesn't know about it — safe rmtree).
        registered_now = {e[0] for e in _registered_worktrees(root)}
        if wt in registered_now:
            locked_skipped.append(wt)
            failed += 1
        else:
            try:
                if Path(wt).exists():
                    shutil.rmtree(wt)
                removed += 1
                removed_records.append(recovery[wt])
            except OSError as exc:
                logger.warning(
                    "cleanup_stale_worktrees: failed to rmtree orphan %s (%s)",
                    wt, exc,
                )
                failed += 1

    _git(root, "worktree", "prune")
    # Extract-before-delete: write recovery pointers to the tracked ledger
    # (caller commits it, like ledger.ndjson).
    salvage_ledger = wsv.record_sweep(root, removed_records)

    logger.info(
        "cleanup_stale_worktrees: %d removed, %d failed, %d locked-skipped",
        removed, failed, len(locked_skipped),
    )
    return {
        "main": str(root),
        "active": active,
        "dirty": dirty,
        "locked": locked,
        "stale": stale,
        "removed": removed,
        "failed": failed,
        "locked_skipped": locked_skipped,
        "dry_run": False,
        "status": "removed",
        "salvage_ledger": str(salvage_ledger) if salvage_ledger else None,
        "salvaged": len(removed_records),
    }


def register(server) -> None:
    """Register the stale-worktree cleanup MCP tool."""

    @server.tool(
        name="noctus.dev.cleanup_stale_worktrees",
        description=(
            "Remove engineer worktrees whose branch is merged to "
            "origin/dev (SHA-ancestry OR patch-id/cherry-pick) — the dev "
            "integration branch worktrees integrate to. DRY-RUN by "
            "default — force=True actually removes. NEVER removes the main "
            "worktree, sibling workspaces, or worktrees with uncommitted/"
            "stashed work (force does NOT override safety gates); git-refused "
            "locked paths are surfaced, never rm-rf'd (THE-P10). Shared-stash "
            "subtraction + dead-pid auto-unlock (THE-P11). Shares the "
            "merged-base + merged predicate with noctus.dev.mole via "
            "_worktree_staleness. Pass worktree_path when called from inside "
            "a git worktree."
        ),
    )
    def _cleanup_stale_worktrees(
        worktree_path: str | None = None,
        force: bool = False,
    ) -> dict:
        return cleanup_stale_worktrees(
            worktree_path=worktree_path, force=force,
        )
