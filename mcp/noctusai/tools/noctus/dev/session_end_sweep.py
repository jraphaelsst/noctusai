"""session_end_sweep — manual session-close cleanup orchestration.

Why this exists
    The original diagnostic asked for an "auto-salvage at session close":
    sweep all worktrees, salvage-and-cleanup the integrated ones, append
    ledger entries. The harness does NOT expose a session-close hook, so
    we ship this as a USER-INVOKED orchestration that does the same
    sweep on-demand.

What it does
    1. Detect every `.claude/worktrees/<slug>/` on disk.
    2. For each: check if its branch is integrated into origin/dev (0
       commits ahead).
    3. For integrated worktrees: surface as safe-to-cleanup. Caller can
       run `noctus.dev.task_branch action=cleanup slug=<slug>` to remove.
    4. For non-integrated worktrees: surface with reason ("3 commits
       ahead — finish or salvage").
    5. Also detect orphan branches (no worktree, no project artifacts)
       via `orphan_branch_sweeper.scan`.
    6. Combine both views + log a summary entry to
       `project-history/worktree-salvage.ndjson`.

Why not auto-delete
    Worktrees can carry uncommitted work even when their branch is
    integrated (architect made tweaks but didn't commit). Auto-delete
    would silently lose work. The tool SURFACES + suggests; the user
    confirms.

Composes with
    - `task_branch` (the actual cleanup primitive)
    - `orphan_branch_sweeper` (the local-branch view)
    - `mole` (custodial scanner)

KB § CONTEXT/PATTERNS/common/session-end-sweep.md.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Append-only, union-merge, cache-EXEMPT ledgers — the only paths safe to
# auto-commit + FF-push at session close (a push touching only these never
# triggers a cache/embedding refresh, so it can never spawn NEW churn).
_LEDGER_PATHS = [
    "project-history/vector-costs.ndjson",
    "project-history/auto-improvement.ndjson",
    "project-history/ledger.ndjson",
    "project-history/worktree-salvage.ndjson",
    "project-history/branch-tree.ndjson",
]


def _ledger_git_runner(cmd: list[str]) -> tuple[int, str, str]:
    """git runner for `commit_and_ff_push_ledger`. `cmd` already starts with
    'git' (the helper builds the full `git -C <root> …`). Runs with the refresh
    + cost-log-auto-commit SKIP flags set, so the FF-push it issues canNOT trigger
    an embedding refresh → canNOT append a fresh cost row → the delivery converges
    in ONE push (this is what makes 'session ends local==remote' hold)."""
    env = {**os.environ, "NOCTUS_SKIP_EMBED_REFRESH": "1", "NOCTUS_SKIP_COSTLOG_COMMIT": "1"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, "", str(e)


def deliver_trailing_ledgers(
    repo_root: Path,
    *,
    dev_branch: str = "dev",
    remote: str = "origin",
    _runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Auto-deliver any trailing append-only ledger churn (the recurring
    `chore(cost-log)` commit + any dirty ledger row) from the PRIMARY dev checkout
    to `origin/dev`, so a session ends `local==remote` with nothing that looks
    like stale/pending work.

    Safe by construction: reuses `commit_and_ff_push_ledger` (fetch → divergence-
    guard that REFUSES if any NON-ledger commit is ahead → rebase → FF-push, never
    force), runs the push with refresh SKIPPED so it can't spawn new churn, and
    never raises. Returns a structured `{status, pushed, detail}`.
    """
    runner = _runner or _ledger_git_runner
    root = str(repo_root)
    dev_ref = f"{remote}/{dev_branch}"
    try:
        from ._ledger_push import commit_and_ff_push_ledger  # lazy — avoid import cycle
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "pushed": False, "error": f"ledger-push helper unavailable: {e}"}

    # SAFETY: the push helper does `rebase origin/dev` + `push HEAD:dev`, so the
    # primary checkout MUST be on `dev` — otherwise we'd rebase/push the wrong
    # branch. If it isn't, skip cleanly (the churn ships on the next on-dev sweep).
    rc_b, cur_branch, _ = runner(["git", "-C", root, "symbolic-ref", "--quiet", "--short", "HEAD"])
    if rc_b != 0 or (cur_branch or "").strip() != dev_branch:
        return {"status": "skipped", "pushed": False,
                "reason": f"primary checkout not on '{dev_branch}' (on '{(cur_branch or '').strip() or 'detached'}')"}

    # Is any ledger path dirty (uncommitted), or is there a trailing committed row?
    rc_s, out_s, _ = runner(["git", "-C", root, "status", "--porcelain", "--", *_LEDGER_PATHS])
    dirty = bool((out_s or "").strip())
    rc_a, out_a, _ = runner(["git", "-C", root, "rev-list", f"{dev_ref}..{dev_branch}"])
    ahead = [s for s in (out_a or "").splitlines() if s.strip()]
    if not dirty and not ahead:
        return {"status": "clean", "pushed": False, "reason": "no trailing ledger churn"}

    result = commit_and_ff_push_ledger(
        runner=runner,
        rel_paths=_LEDGER_PATHS,
        dev_branch=dev_branch,
        remote=remote,
        root=root,
        already_committed=not dirty,  # dirty → commit+push; clean-but-ahead → push existing
        commit_msg=(
            "chore(cost-log): deliver session ledger churn [auto]\n\n"
            "Session-end auto-delivery (session_end_sweep) so dev ends local==remote "
            "and the append-only ledger churn never lingers as apparent stale work.\n\n"
            "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
        ) if dirty else None,
    )
    return {
        "status": result.get("status", "error" if not result.get("ok") else "?"),
        "pushed": bool(result.get("pushed", False)),
        "detail": result,
    }


def _run_git(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None,
                           capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, "", str(e)


def _worktree_branches(repo_root: Path) -> list[tuple[str, str, Path]]:
    """Return [(slug, branch, worktree_path)] for every .claude/worktrees entry."""
    out: list[tuple[str, str, Path]] = []
    wt_dir = repo_root / ".claude" / "worktrees"
    if not wt_dir.is_dir():
        return out
    rc, plist, _ = _run_git(["worktree", "list", "--porcelain"], cwd=repo_root)
    if rc != 0:
        return out
    # Parse porcelain output into (path, branch) pairs.
    current_path = None
    for line in plist.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line[len("worktree "):])
        elif line.startswith("branch "):
            branch_ref = line[len("branch "):]
            if branch_ref.startswith("refs/heads/"):
                branch = branch_ref[len("refs/heads/"):]
                if current_path and ".claude/worktrees" in str(current_path):
                    slug = current_path.name
                    out.append((slug, branch, current_path))
            current_path = None
    return out


def _ahead_behind(repo_root: Path, branch: str, base: str = "origin/dev") -> tuple[int, int] | None:
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


def _has_uncommitted(repo_root: Path, worktree_path: Path) -> bool:
    """True if the worktree has uncommitted changes (any kind)."""
    rc, out, _ = _run_git(["status", "--porcelain"], cwd=worktree_path)
    if rc != 0:
        return True  # defensive — if we can't tell, assume dirty
    return bool(out.strip())


def sweep(repo_root: Path | None = None, deliver_ledgers: bool = True) -> dict[str, Any]:
    """Survey all worktrees + orphan branches; classify each.

    Returns:
      {
        ok: True,
        worktrees: [{slug, branch, path, classification, suggestion,
                     ahead, behind, uncommitted}],
        orphan_branches: <output from orphan_branch_sweeper.scan>,
        sweep_ts: ISO timestamp,
      }
    """
    if repo_root is None:
        from settings import REPO_ROOT
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)
    _run_git(["fetch", "origin", "--quiet"], cwd=repo_root)

    wt_findings: list[dict[str, Any]] = []
    for slug, branch, wt_path in _worktree_branches(repo_root):
        ab = _ahead_behind(repo_root, branch)
        ahead = ab[0] if ab else None
        behind = ab[1] if ab else None
        uncommitted = _has_uncommitted(repo_root, wt_path)
        if ahead == 0 and not uncommitted:
            cls = "safe-to-cleanup"
            sugg = (
                f"`noctus.dev.task_branch action=cleanup slug={slug}` — "
                f"integrated + clean."
            )
        elif uncommitted:
            cls = "uncommitted-work"
            sugg = (
                f"worktree has uncommitted changes — review + commit / salvage "
                f"before cleanup."
            )
        elif ahead and ahead > 0:
            cls = "ahead-of-dev"
            sugg = (
                f"{ahead} commit(s) not integrated to origin/dev — finish "
                f"the slice or use task_branch action=integrate."
            )
        else:
            cls = "unknown"
            sugg = "could not determine state — investigate manually"
        wt_findings.append({
            "slug": slug, "branch": branch, "path": str(wt_path),
            "ahead": ahead, "behind": behind,
            "uncommitted": uncommitted,
            "classification": cls, "suggestion": sugg,
        })

    # Also include orphan-branch findings (local branches).
    try:
        from . import orphan_branch_sweeper as obs
        orphan_result = obs.scan(repo_root=repo_root)
    except Exception as e:  # noqa: BLE001
        orphan_result = {"ok": False, "error": str(e)[:200], "branches": []}

    # Remote branch classification (P3.4 — remote-aware session-end sweep).
    # Read-only advisory — reports integrated vs unique-aged; never auto-deletes.
    remote_summary: dict = {"ok": False, "error": "not run"}
    try:
        from . import remote_branch_hygiene as rbh
        remote_branches = rbh.classify_remote_branches(repo_root=repo_root)
        integrated_remotes = [b["branch"] for b in remote_branches if b["verdict"] == "integrated"]
        unique_remotes = [b for b in remote_branches if b["verdict"] == "unique"]
        unique_aged = [
            b for b in unique_remotes
            if b.get("age_days") is not None and b["age_days"] > 7
        ]
        remote_summary = {
            "ok": True,
            "total": len(remote_branches),
            "protected": sum(1 for b in remote_branches if b["verdict"] == "protected"),
            "integrated_count": len(integrated_remotes),
            "integrated_suggest_delete": integrated_remotes,
            "unique_count": len(unique_remotes),
            "unique_aged_count": len(unique_aged),
            "unique_aged_suggest_salvage": [
                {
                    "branch": b["branch"],
                    "age_days": b["age_days"],
                    "subject": b["subject"],
                    "unique_commits": b["unique_commits"],
                }
                for b in unique_aged
            ],
        }
    except Exception as e:  # noqa: BLE001
        remote_summary = {"ok": False, "error": str(e)[:200]}

    # Log sweep summary to ledger.
    try:
        ledger = repo_root / "project-history" / "worktree-salvage.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _now_iso(),
            "kind": "session-end-sweep",
            "worktree_count": len(wt_findings),
            "safe_to_cleanup": [w["slug"] for w in wt_findings
                                if w["classification"] == "safe-to-cleanup"],
            "uncommitted": [w["slug"] for w in wt_findings
                            if w["classification"] == "uncommitted-work"],
            "ahead_of_dev": [w["slug"] for w in wt_findings
                             if w["classification"] == "ahead-of-dev"],
            "remote_integrated_count": remote_summary.get("integrated_count", 0),
            "remote_unique_aged_count": remote_summary.get("unique_aged_count", 0),
        }
        with ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass

    # AUTO-DELIVER trailing ledger churn (the recurring `chore(cost-log)` commit +
    # any dirty ledger row, incl. the sweep-summary row just appended above) →
    # origin/dev, so the session ends local==remote with nothing that looks like
    # stale/pending work. Best-effort, ledger-only, FF, refresh-skipped. Runs LAST
    # (after the summary append) so it also delivers that row.
    ledger_delivery: dict[str, Any] = {"status": "skipped", "reason": "deliver_ledgers=False"}
    if deliver_ledgers:
        try:
            ledger_delivery = deliver_trailing_ledgers(repo_root)
        except Exception as e:  # noqa: BLE001 — never fail the survey over delivery
            ledger_delivery = {"status": "error", "pushed": False, "error": str(e)[:200]}

    return {
        "ok": True,
        "sweep_ts": _now_iso(),
        "worktrees": wt_findings,
        "orphan_branches": orphan_result,
        "remote_branches": remote_summary,
        "ledger_delivery": ledger_delivery,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.session_end_sweep",
        description=(
            "Surface every .claude/worktrees/*, every local branch diverged "
            "from origin/dev, AND every origin/* remote branch — with "
            "classification + suggestion. User-invoked end-of-session cleanup "
            "orchestration (the harness has no auto session-close hook). "
            "Worktree classifications: safe-to-cleanup / uncommitted-work / "
            "ahead-of-dev / unknown. Remote branch section: integrated "
            "(suggest delete-integrated via noctus.dev.delete_integrated_remote) / "
            "unique-aged (suggest salvage+triage). Squash-aware classification. "
            "Logs a sweep entry to project-history/worktree-salvage.ndjson. "
            "Never auto-deletes; always surfaces + suggests. "
            "KB § CONTEXT/PATTERNS/common/session-end-sweep.md · "
            "KB § CONTEXT/PATTERNS/common/learn-before-archive.md."
        ),
    )
    def _sweep() -> dict:
        return sweep()


__all__ = ["sweep", "register"]
