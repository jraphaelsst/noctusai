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

Push idiom (rebase-onto-dev → FF-push, retry-on-race)
-----------------------------------------------------
Mirrors task_branch.cleanup + worktree_salvage FF-push-to-dev:
  stage ONLY the ledger+mirror → commit → fetch → divergence-guard →
  rebase onto origin/dev → FF-push HEAD:dev; single retry on a concurrent-push
  race.  The union-merge gitattribute makes the rebase conflict-free (the
  ledger files are append-only), so a behind/diverged local dev (e.g. a peer
  advanced origin/dev from a worktree) no longer wedges the push on a stale
  base.  The divergence-guard REFUSES to push when a non-ledger commit is ahead
  of origin/dev (never leak non-ledger work onto dev); a genuine rebase conflict
  is aborted + surfaced, never force-resolved.

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
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
LEDGER_REL = "project-history/branch-tree.ndjson"
LEDGER_PATH: Path = REPO_ROOT / LEDGER_REL
# Repo-tracked, human-accessible MIRROR — kept byte-identical to the canonical
# ledger BY CONSTRUCTION (every write goes to both; the check_branch_tree_mirror
# keeper hard-blocks any drift). Both are project-history/*.ndjson ⇒ merge=union +
# cache-exempt. KB § PATTERNS/architect/branch-tree-tracking.md (§2 the mirror).
MIRROR_NAME = "branch-tree.mirror.ndjson"
MIRROR_REL = "project-history/" + MIRROR_NAME
MIRROR_PATH: Path = REPO_ROOT / MIRROR_REL

# ── Cache-exemption sentinel ──────────────────────────────────────────────────
# ONLY these paths (the ledger + its mirror) are exempt — any other staged file
# re-enables cache refresh.
_CACHE_EXEMPT_PATHS: frozenset[str] = frozenset({LEDGER_REL, MIRROR_REL})


def _ledger_targets() -> tuple[Path, ...]:
    """Canonical ledger + its mirror, derived from the CURRENT module-level
    LEDGER_PATH so monkeypatching LEDGER_PATH (tests) relocates both."""
    return (LEDGER_PATH, LEDGER_PATH.with_name(MIRROR_NAME))


def _ledger_rels() -> tuple[str, ...]:
    """Repo-relative paths to stage — derived from the CURRENT LEDGER_REL."""
    from pathlib import PurePosixPath
    return (LEDGER_REL, str(PurePosixPath(LEDGER_REL).with_name(MIRROR_NAME)))


def _write_row(row: dict[str, Any]) -> None:
    """Append one row to BOTH the canonical ledger AND its mirror — drift-free by
    construction. Agents never populate one without the other; the
    check_branch_tree_mirror keeper enforces parity for any out-of-band edit."""
    for _p in _ledger_targets():
        _p.parent.mkdir(parents=True, exist_ok=True)
        with _p.open("a", encoding="utf-8") as _f:
            _f.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def _resolve_session_id() -> str | None:
    """Best-effort current Claude Code session id for branch-pointer auto-fill.

    The `session` field is the claude-tree's owning-session coordinate (KB §2)
    and MUST never be null — `check_branch_tree_mirror` hard-blocks a push when
    any pointer carries a null/empty session. So `append`/`update` auto-fill it
    from here when the caller passes none.

    Resolution order (most → least precise):
      1. ``$CLAUDE_CODE_SESSION_ID`` — the harness sets this to the live session
         UUID; the precise, always-current source.
      2. The stem of the newest ``*.jsonl`` transcript in this repo's Claude
         project dir (``~/.claude/projects/<encoded-cwd>/``) — the actively
         written transcript is the current session. Fallback when the env var
         is absent (older CLI, certain spawn paths).

    Returns None only when neither resolves (e.g. a non-Claude CI/cron context);
    `append` then errors rather than writing a null (no silent-null).
    """
    env = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if env and env.strip():
        return env.strip()
    try:
        encoded = "-" + str(REPO_ROOT).strip("/").replace("/", "-")
        proj_dir = Path.home() / ".claude" / "projects" / encoded
        transcripts = sorted(
            proj_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if transcripts:
            return transcripts[0].stem
    except Exception:  # noqa: BLE001 — best-effort; fall through to None
        pass
    return None


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
def _ff_or_rebase_push_to_dev(
    *,
    run,
    remote: str,
    dev_branch: str,
) -> dict[str, Any]:
    """One fetch → divergence-guard → rebase-onto-origin/dev → FF-push attempt.

    Precondition: the ledger commit is ALREADY made on HEAD.  Shared by the
    initial push and the single concurrent-push-race retry so both legs take
    the identical path (no naive "re-push the same stale commit" — that is the
    bug this replaces: when local dev is BEHIND origin/dev the new commit sits
    on a stale base and `push HEAD:dev` is rejected non-FF forever).

    Returns a structured result:
      * success           → {"ok": True, "status": "pushed", "pushed": True}
      * non-ledger ahead  → {"ok": False, "retryable": False, "committed_locally": True, ...}
      * rebase conflict   → {"ok": False, "retryable": False, "committed_locally": True, ...}
      * push leg failed   → {"ok": False, "retryable": True,  "committed_locally": True, ...}

    The caller decides whether to retry (retryable=True ⇒ a concurrent-push
    re-fetch+re-rebase may clear it).
    """
    ledger_rels = set(_ledger_rels())
    dev_ref = f"{remote}/{dev_branch}"

    # 1. Fetch so origin/<dev> reflects any peer push (incl. a worktree's
    #    task_branch integrate that advanced origin/dev under us).
    run(["git", "fetch", remote])

    # 2. Divergence guard — EVERY commit ahead of origin/<dev> must touch ONLY
    #    the two cache-exempt ledger paths, else pushing HEAD:dev would leak
    #    non-ledger work onto dev (drift 7761(2)).  Protective, not a fast-path.
    rc_rl, out_rl, _ = run(["git", "rev-list", f"{dev_ref}..HEAD"])
    ahead_shas = [s.strip() for s in (out_rl or "").splitlines() if s.strip()]
    non_ledger_shas: list[str] = []
    for sha in ahead_shas:
        _rc_dt, out_dt, _ = run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha]
        )
        changed = [f.strip() for f in (out_dt or "").splitlines() if f.strip()]
        if any(f not in ledger_rels for f in changed):
            non_ledger_shas.append(sha)
    if non_ledger_shas:
        shas = ", ".join(s[:8] for s in non_ledger_shas)
        return {
            "ok": False,
            "retryable": False,
            "error": (
                f"HEAD has non-ledger commit(s) ahead of {dev_ref} ({shas}) — "
                "pointer commit landed locally but was NOT pushed, to avoid "
                "leaking non-ledger work onto dev; reconcile the divergence then "
                "re-push"
            ),
            "committed_locally": True,
        }

    # 3. Rebase the ledger-only ahead-commits onto the freshly-fetched
    #    origin/<dev>.  Conflict-free by construction (the ledger files carry a
    #    merge=union gitattribute + are append-only), so a behind/diverged base
    #    replays cleanly.  A genuine conflict ⇒ abort + surface; NEVER
    #    -X/force/auto-resolve.
    rc_rb, _, err_rb = run(["git", "rebase", dev_ref])
    if rc_rb != 0:
        run(["git", "rebase", "--abort"])
        return {
            "ok": False,
            "retryable": False,
            "error": (
                f"git rebase onto {dev_ref} reported a conflict "
                f"({err_rb.strip()}); rebase aborted — manual resolution needed "
                "before the pointer can push"
            ),
            "committed_locally": True,
        }

    # 4. FF-push HEAD → dev.
    rc_p, _, err_p = run(["git", "push", remote, f"HEAD:refs/heads/{dev_branch}"])
    if rc_p != 0:
        return {
            "ok": False,
            "retryable": True,
            "error": f"FF-push to {dev_branch} failed: {err_p.strip()}",
            "committed_locally": True,
        }

    return {"ok": True, "status": "pushed", "pushed": True}


def _push_ledger_to_dev(
    *,
    commit_msg: str,
    runner=None,
    dev_branch: str = "dev",
    remote: str = "origin",
) -> dict[str, Any]:
    """Stage ONLY branch-tree.ndjson+mirror → commit → rebase-onto-dev → FF-push.

    Idempotent: if neither the ledger nor its mirror is dirty (nothing to
    commit), returns ok=True with status=already_clean.  After committing, the
    push leg is delegated to `_ff_or_rebase_push_to_dev` (fetch → divergence-
    guard → rebase onto origin/dev → FF-push), retried ONCE on a retryable
    push-leg failure (concurrent-push race).  A non-ledger-ahead guard refusal
    or a rebase conflict is NOT retried — it is surfaced immediately with
    committed_locally=True.
    """
    run = runner or _run

    # Ensure the file exists
    if not LEDGER_PATH.exists():
        return {"ok": False, "error": "branch-tree.ndjson does not exist; nothing to push"}

    rels = list(_ledger_rels())
    # Check if either the ledger OR its mirror is dirty
    rc_s, out_s, _ = run(["git", "status", "--porcelain", "--", *rels])
    if rc_s != 0 or not (out_s or "").strip():
        return {"ok": True, "status": "already_clean", "pushed": False}

    # Stage ONLY the ledger + mirror (both cache-exempt, merge=union)
    rc_a, _, err_a = run(["git", "add", "--", *rels])
    if rc_a != 0:
        logger.warning("branch_pointer: git add failed (%s)", err_a.strip())
        return {"ok": False, "error": f"git add failed: {err_a.strip()}"}

    # Commit
    rc_c, _, err_c = run(["git", "commit", "-m", commit_msg, "--", *rels])
    if rc_c != 0:
        logger.warning("branch_pointer: git commit failed (%s)", err_c.strip())
        return {"ok": False, "error": f"git commit failed: {err_c.strip()}"}

    # fetch → guard → rebase-onto-origin/dev → FF-push; retry ONCE on a
    # retryable (concurrent-push-race) failure.
    push_res = _ff_or_rebase_push_to_dev(run=run, remote=remote, dev_branch=dev_branch)
    if not push_res["ok"] and push_res.get("retryable"):
        push_res = _ff_or_rebase_push_to_dev(run=run, remote=remote, dev_branch=dev_branch)

    if not push_res["ok"]:
        logger.warning(
            "branch_pointer: push to %s failed (%s); commit landed locally — "
            "manual reconciliation needed", dev_branch, push_res.get("error", "")
        )
        return {
            "ok": False,
            "error": push_res.get("error", f"FF-push to {dev_branch} failed"),
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

    # Auto-fill the owning Claude session so a pointer is NEVER session=null
    # (check_branch_tree_mirror hard-blocks a push when any row is null).
    if session is None:
        session = _resolve_session_id()
    if not session or not str(session).strip():
        return {
            "ok": False,
            "error": (
                "session could not be auto-resolved (CLAUDE_CODE_SESSION_ID unset and no "
                "transcript found) — pass session= explicitly; a branch-tree pointer may "
                "never be written with a null/empty session"
            ),
        }

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

    _write_row(row)  # writes BOTH the canonical ledger and its mirror

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

    # Carry forward the prior session; auto-fill if the prior row predates the
    # always-fill rule (legacy null) so the delta row is never session=null.
    carried_session = prev.get("session") or _resolve_session_id()
    if not carried_session or not str(carried_session).strip():
        return {
            "ok": False,
            "error": (
                "session could not be carried forward or auto-resolved — pass it on the "
                "originating append; a branch-tree pointer may never be session=null"
            ),
        }

    row: dict[str, Any] = {
        "ts": _now_iso(),
        "branch": branch,
        "base": prev.get("base", ""),
        "commit": commit if commit is not None else prev.get("commit", ""),
        "worktree": prev.get("worktree"),
        "role": prev.get("role", ""),
        "agent": prev.get("agent", ""),
        "parent": prev.get("parent", ""),
        "session": carried_session,
        "paths": paths if paths is not None else prev.get("paths", []),
        "status": new_status,
        "brief": brief if brief is not None else prev.get("brief", ""),
        "notes": notes if notes is not None else prev.get("notes", ""),
    }

    _write_row(row)  # writes BOTH the canonical ledger and its mirror

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
