"""noctus.dev.branch_pointer — the global live map of git-tree × claude-tree.

Append-only ndjson ledger (`project-history/branch-tree.ndjson`) tracking
branch ownership, collision zones, and agent coordination. Agents read
**dev's** copy to get the live cross-branch picture; pointer updates push
ONLY that file to dev so every agent sees the latest state in real time.

KB § CONTEXT/PATTERNS/architect/branch-tree-tracking.md.

Actions
-------
append  Create a new pointer row (first claim on a branch, pre-self-branch).
update  Append a delta row for an existing branch (carries forward last values
        + the supplied overrides — latest-by-ts wins per branch).
query   Resolve latest-per-branch from dev's copy; supports filtering by
        status, branch, agent, and collision-zone overlap.
list    Live map: all non-terminal pointers (add terminal with include_terminal).

Push idiom (FF-only to dev, retry-on-race)
------------------------------------------
Mirrors task_branch.cleanup + worktree_salvage FF-push-to-dev:
  fetch dev → stage ONLY branch-tree.ndjson → commit → push HEAD:dev
  (FF-only); single retry on concurrent-push race.  union-merge gitattribute
  handles concurrent appends without conflicts.

Cache-exemption (contract §3 "Cache-sync discipline")
------------------------------------------------------
A commit/push that touches ONLY `project-history/branch-tree.ndjson` MUST
NOT trigger any cache refresh (noc-graph / embeddings / structural).  The
exemption lives HERE (is_cache_exempt_path) and in noc_graph_cache._source_files
(branch-tree.ndjson excluded from the history aggregate input), NOT in the
hook shell scripts.  The hooks CALL this predicate for the trigger decision.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
LEDGER_REL = "project-history/branch-tree.ndjson"
LEDGER_PATH: Path = REPO_ROOT / LEDGER_REL

# ── Cache-exemption sentinel ──────────────────────────────────────────────────
# ONLY this path is exempt — any other staged file re-enables cache refresh.
_CACHE_EXEMPT_PATHS: frozenset[str] = frozenset({LEDGER_REL})


def is_cache_exempt_path(rel_path: str) -> bool:
    """Return True iff `rel_path` (repo-relative) is an exempt metadata path.

    A push/commit that changes ONLY exempt paths must skip all cache-refresh
    hooks (structural + embedding).  The pre-push hook calls this per-changed-
    file; if ALL changed files return True the refresh is skipped entirely.
    """
    return rel_path in _CACHE_EXEMPT_PATHS


def changed_files_are_all_cache_exempt(changed: list[str]) -> bool:
    """True iff every path in `changed` is cache-exempt (→ skip refresh)."""
    return bool(changed) and all(is_cache_exempt_path(p) for p in changed)


# ── Status enum ──────────────────────────────────────────────────────────────
STATUSES: frozenset[str] = frozenset({
    "on_going", "shipped", "blocked", "canceled", "stale", "deferred"
})
ROLES: frozenset[str] = frozenset({"orchestrator", "engineer"})
# Statuses that represent "done" — excluded from the default list view.
TERMINAL_STATUSES: frozenset[str] = frozenset({"shipped", "canceled", "stale"})


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run a subprocess command, return (rc, stdout, stderr)."""
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(REPO_ROOT))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _read_dev_ledger(runner=None) -> list[dict]:
    """Read branch-tree.ndjson from dev's copy (git-show origin/dev:<path>).

    Falls back to the local file if origin/dev is not available (e.g. no
    remote, or a test with an injected runner).  Returns a list of dicts.
    """
    run = runner or _run
    rc, out, _err = run(["git", "show", f"origin/dev:{LEDGER_REL}"])
    if rc == 0:
        text = out
    else:
        # Fallback: local file (test context or offline)
        if LEDGER_PATH.exists():
            text = LEDGER_PATH.read_text(encoding="utf-8")
        else:
            return []

    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip malformed; no silent-error pattern violation (parse-only)
    return rows


def _latest_per_branch(rows: list[dict]) -> dict[str, dict]:
    """Resolve the latest-by-ts row per branch (append-only → latest wins)."""
    best: dict[str, dict] = {}
    for row in rows:
        branch = row.get("branch", "")
        if not branch:
            continue
        prev = best.get(branch)
        if prev is None or row.get("ts", "") >= prev.get("ts", ""):
            best[branch] = row
    return best


def _paths_overlap(a: list[str], b: list[str]) -> bool:
    """True iff two path lists share at least one common element."""
    sa = set(a or [])
    sb = set(b or [])
    return bool(sa & sb)


# ── FF-push-to-dev (mirrors task_branch cleanup salvage-push idiom) ───────────
def _push_ledger_to_dev(
    *,
    commit_msg: str,
    runner=None,
    dev_branch: str = "dev",
    remote: str = "origin",
) -> dict[str, Any]:
    """Stage ONLY branch-tree.ndjson → commit → FF-push to dev.

    Idempotent: if the ledger is not dirty (nothing to commit), returns
    ok=True with status=already_clean.  Single retry on concurrent-push race
    (fetch + re-push).  Mirrors the task_branch.cleanup salvage-ledger push
    pattern and the auto_improvement append-on-merge FF idiom.
    """
    run = runner or _run

    # Ensure the file exists
    if not LEDGER_PATH.exists():
        return {"ok": False, "error": "branch-tree.ndjson does not exist; nothing to push"}

    # Fetch to ensure we can do a FF push
    run(["git", "fetch", remote])

    # Check if the file is dirty
    rc_s, out_s, _ = run(["git", "status", "--porcelain", "--", LEDGER_REL])
    if rc_s != 0 or not (out_s or "").strip():
        return {"ok": True, "status": "already_clean", "pushed": False}

    # Stage ONLY the ledger file
    rc_a, _, err_a = run(["git", "add", "--", LEDGER_REL])
    if rc_a != 0:
        logger.warning("branch_pointer: git add failed (%s)", err_a.strip())
        return {"ok": False, "error": f"git add failed: {err_a.strip()}"}

    # Commit
    rc_c, _, err_c = run(["git", "commit", "-m", commit_msg, "--", LEDGER_REL])
    if rc_c != 0:
        logger.warning("branch_pointer: git commit failed (%s)", err_c.strip())
        return {"ok": False, "error": f"git commit failed: {err_c.strip()}"}

    # Push HEAD→dev (FF-only); retry once on concurrent-push race
    rc_p, _, err_p = run(["git", "push", remote, f"HEAD:refs/heads/{dev_branch}"])
    if rc_p != 0:
        run(["git", "fetch", remote])
        rc_p, _, err_p = run(["git", "push", remote, f"HEAD:refs/heads/{dev_branch}"])
    if rc_p != 0:
        logger.warning(
            "branch_pointer: push to %s failed after retry (%s); "
            "commit landed locally — manual push needed", dev_branch, err_p.strip()
        )
        return {
            "ok": False,
            "error": f"FF-push to {dev_branch} failed after retry: {err_p.strip()}",
            "committed_locally": True,
        }

    return {"ok": True, "status": "pushed", "pushed": True}


# ── Core API ──────────────────────────────────────────────────────────────────
def append(
    *,
    branch: str,
    base: str,
    commit: str,
    role: str,
    agent: str,
    parent: str,
    paths: list[str],
    status: str,
    brief: str,
    notes: str = "",
    worktree: str | None = None,
    session: str | None = None,
    push_dev: bool = True,
    runner=None,
    dev_branch: str = "dev",
) -> dict[str, Any]:
    """Append a new pointer row for `branch` and (default) push to dev.

    Called before self-branching to claim the collision zone immediately,
    and on any status transition that needs a fresh row.

    push_dev=True (default): stage + commit + FF-push ONLY the ndjson to dev
    so every agent sees the updated map in real time (the no-skip guarantee).
    """
    if status not in STATUSES:
        return {"ok": False, "error": f"status must be one of {sorted(STATUSES)}; got {status!r}"}
    if role not in ROLES:
        return {"ok": False, "error": f"role must be one of {sorted(ROLES)}; got {role!r}"}

    row: dict[str, Any] = {
        "ts": _now_iso(),
        "branch": branch,
        "base": base,
        "commit": commit,
        "worktree": worktree,
        "role": role,
        "agent": agent,
        "parent": parent,
        "session": session,
        "paths": paths,
        "status": status,
        "brief": brief,
        "notes": notes,
    }

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    result: dict[str, Any] = {"ok": True, "row": row, "ledger_path": LEDGER_REL}

    if push_dev:
        push_result = _push_ledger_to_dev(
            commit_msg=(
                f"chore(branch-pointer): {status} — {agent} on {branch}\n\n"
                f"{brief}"
            ),
            runner=runner,
            dev_branch=dev_branch,
        )
        result["push"] = push_result
        if not push_result["ok"]:
            logger.warning(
                "branch_pointer.append: push to dev failed for %s — "
                "row is on disk, dev map may lag until next push", branch
            )

    return result


def update(
    *,
    branch: str,
    status: str | None = None,
    commit: str | None = None,
    paths: list[str] | None = None,
    brief: str | None = None,
    notes: str | None = None,
    push_dev: bool = True,
    runner=None,
    dev_branch: str = "dev",
    from_dev: bool = True,
) -> dict[str, Any]:
    """Append a delta row for `branch`, carrying forward the last known values.

    Reads the latest row from dev (from_dev=True, default) to carry forward
    unchanged fields, then merges in the supplied overrides.  Because the
    ledger is append-only, this writes a NEW row — not an in-place edit.
    """
    rows = _read_dev_ledger(runner=runner) if from_dev else (
        [json.loads(l) for l in LEDGER_PATH.read_text("utf-8").splitlines() if l.strip()]
        if LEDGER_PATH.exists() else []
    )
    best = _latest_per_branch(rows)
    prev = best.get(branch)
    if prev is None:
        return {
            "ok": False,
            "error": (
                f"branch '{branch}' not found in branch-tree.ndjson — "
                "use 'append' to create the initial pointer"
            ),
        }

    new_status = status if status is not None else prev.get("status", "on_going")
    if new_status not in STATUSES:
        return {"ok": False, "error": f"status must be one of {sorted(STATUSES)}; got {new_status!r}"}

    row: dict[str, Any] = {
        "ts": _now_iso(),
        "branch": branch,
        "base": prev.get("base", ""),
        "commit": commit if commit is not None else prev.get("commit", ""),
        "worktree": prev.get("worktree"),
        "role": prev.get("role", ""),
        "agent": prev.get("agent", ""),
        "parent": prev.get("parent", ""),
        "session": prev.get("session"),
        "paths": paths if paths is not None else prev.get("paths", []),
        "status": new_status,
        "brief": brief if brief is not None else prev.get("brief", ""),
        "notes": notes if notes is not None else prev.get("notes", ""),
    }

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    result: dict[str, Any] = {"ok": True, "row": row, "ledger_path": LEDGER_REL}

    if push_dev:
        push_result = _push_ledger_to_dev(
            commit_msg=(
                f"chore(branch-pointer): {new_status} — {row['agent']} on {branch}\n\n"
                f"{row['brief']}"
            ),
            runner=runner,
            dev_branch=dev_branch,
        )
        result["push"] = push_result
        if not push_result["ok"]:
            logger.warning(
                "branch_pointer.update: push to dev failed for %s — "
                "row is on disk, dev map may lag until next push", branch
            )

    return result


def query(
    *,
    from_dev: bool = True,
    status: str | None = None,
    branch: str | None = None,
    agent: str | None = None,
    paths_overlap: list[str] | None = None,
    runner=None,
) -> list[dict]:
    """Resolve latest-per-branch from dev's copy and apply optional filters.

    `paths_overlap`: return only branches whose collision zone (`paths` field)
    intersects the given list — the pre-dispatch planner.  Empty list ⇒ no
    filter (same as None).

    Default from_dev=True: reads origin/dev's copy so every calling agent
    sees the globally-updated map, regardless of its own branch state.
    """
    if from_dev:
        rows = _read_dev_ledger(runner=runner)
    else:
        rows = (
            [json.loads(l) for l in LEDGER_PATH.read_text("utf-8").splitlines() if l.strip()]
            if LEDGER_PATH.exists() else []
        )
    best = _latest_per_branch(rows)
    results: list[dict] = []
    for br, row in best.items():
        if status is not None and row.get("status") != status:
            continue
        if branch is not None and br != branch:
            continue
        if agent is not None and row.get("agent") != agent:
            continue
        if paths_overlap:
            if not _paths_overlap(row.get("paths", []), paths_overlap):
                continue
        results.append(row)
    # Sort by ts descending — most-recently-updated first
    results.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return results


def list_pointers(
    *,
    from_dev: bool = True,
    include_terminal: bool = False,
    runner=None,
) -> list[dict]:
    """Return the live map: all non-terminal pointers by default.

    `include_terminal=True` adds shipped/canceled/stale rows (full history).
    Default from_dev=True so a fresh agent gets the globally-consistent view.
    """
    all_rows = query(from_dev=from_dev, runner=runner)
    if include_terminal:
        return all_rows
    return [r for r in all_rows if r.get("status") not in TERMINAL_STATUSES]


# ── MCP registration ──────────────────────────────────────────────────────────
def register(server) -> None:  # noqa: ANN001
    @server.tool(
        name="noctus.dev.branch_pointer",
        description=(
            "Global live map of git-tree × claude-tree — read and update branch ownership, "
            "collision zones, and agent coordination.\n\n"
            "ACTIONS\n"
            "  append  — create the first pointer row for a branch (pre-self-branch claim).\n"
            "            Required: branch, base, commit, role, agent, parent, paths, status, brief.\n"
            "            Optional: notes, worktree, session, push_dev (default True).\n"
            "  update  — append a delta row for an existing branch (latest-by-ts wins).\n"
            "            Required: branch. Optional: status, commit, paths, brief, notes,\n"
            "            push_dev (default True), from_dev (default True).\n"
            "  query   — resolve latest-per-branch from dev's copy.\n"
            "            Optional: status, branch, agent, paths_overlap, from_dev (default True).\n"
            "            `paths_overlap=[...]` returns branches whose collision zone intersects\n"
            "            (the pre-dispatch planner — detect collisions before touch).\n"
            "  list    — live map: all non-terminal pointers (include_terminal=True for full view).\n"
            "            Optional: from_dev (default True), include_terminal (default False).\n\n"
            "PUSH IDIOM  push_dev=True (default): stage ONLY project-history/branch-tree.ndjson "
            "→ commit → FF-push to dev (retry on concurrent-push race). A pointer push must NEVER "
            "trigger cache refresh — this is the cache-exempt path (contract §3). "
            "KB § CONTEXT/PATTERNS/architect/branch-tree-tracking.md."
        ),
    )
    def _branch_pointer(
        action: str,
        branch: str | None = None,
        base: str | None = None,
        commit: str | None = None,
        role: str | None = None,
        agent: str | None = None,
        parent: str | None = None,
        paths: list[str] | None = None,
        status: str | None = None,
        brief: str | None = None,
        notes: str | None = None,
        worktree: str | None = None,
        session: str | None = None,
        push_dev: bool = True,
        from_dev: bool = True,
        include_terminal: bool = False,
        paths_overlap: list[str] | None = None,
    ) -> dict | list:
        if action == "append":
            missing = [f for f, v in [
                ("branch", branch), ("base", base), ("commit", commit),
                ("role", role), ("agent", agent), ("parent", parent),
                ("paths", paths), ("status", status), ("brief", brief),
            ] if v is None]
            if missing:
                return {"ok": False, "error": f"append requires: {', '.join(missing)}"}
            return append(
                branch=branch, base=base, commit=commit, role=role, agent=agent,
                parent=parent, paths=paths, status=status, brief=brief,
                notes=notes or "", worktree=worktree, session=session,
                push_dev=push_dev,
            )
        elif action == "update":
            if not branch:
                return {"ok": False, "error": "update requires: branch"}
            return update(
                branch=branch, status=status, commit=commit, paths=paths,
                brief=brief, notes=notes, push_dev=push_dev, from_dev=from_dev,
            )
        elif action == "query":
            return query(
                from_dev=from_dev, status=status, branch=branch, agent=agent,
                paths_overlap=paths_overlap,
            )
        elif action == "list":
            return list_pointers(from_dev=from_dev, include_terminal=include_terminal)
        else:
            return {
                "ok": False,
                "error": f"unknown action {action!r}; must be one of: append, update, query, list",
            }
