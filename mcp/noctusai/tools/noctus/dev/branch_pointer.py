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

from settings import LEDGER_ROOT, REPO_ROOT

from tools.noctus.dev._ledger_push import commit_and_ff_push_ledger

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# LEDGER_ROOT (never REPO_ROOT) for the ledger FILE path — repo-global
# append-only ledger; must resolve to the PRIMARY checkout even when the
# MCP server booted with cwd inside a worktree (see
# workspace.get_ledger_root() docstring). NOTE: this is defense-in-depth
# only — the append/update path commits + FF-pushes to origin/dev in the
# SAME call regardless of which checkout hosts the commit, so a row is
# durable on origin/dev before this function returns in the common case;
# this constant only matters if that push fails.
LEDGER_REL = "project-history/branch-tree.ndjson"
LEDGER_PATH: Path = LEDGER_ROOT / LEDGER_REL
# Repo-tracked, human-accessible MIRROR — kept byte-identical to the canonical
# ledger BY CONSTRUCTION (every write goes to both; the check_branch_tree_mirror
# keeper hard-blocks any drift). Both are project-history/*.ndjson ⇒ merge=union +
# cache-exempt. KB § PATTERNS/architect/branch-tree-tracking.md (§2 the mirror).
MIRROR_NAME = "branch-tree.mirror.ndjson"
MIRROR_REL = "project-history/" + MIRROR_NAME
MIRROR_PATH: Path = LEDGER_ROOT / MIRROR_REL

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
# `integrated-worktree-live` (2026-09-17): a DISTINCT non-terminal status
# for "the branch landed in origin/dev, but a `.claude/worktrees/<slug>`
# directory for it still exists" — session_end_sweep's auto-heal writes this
# instead of `shipped` whenever the worktree directory is still on disk
# (see `session_end_sweep._autoheal_branch_pointers` +
# `_worktree_staleness.py`'s 2026-09-17 incident writeup). Deliberately NOT
# in TERMINAL_STATUSES: `pointer_blocks_removal` must keep refusing removal
# for it exactly like `on_going`, never bypassed by `force=True`. Every
# consumer of the status enum (this module's own validation, the
# `check_branch_tree_mirror` keeper in compliance.py, the CLI help text) is
# derived from these two frozensets — never hand-duplicated — so a new
# status here propagates by construction (KB § PATTERNS/devops/
# product-lockfile-and-slug-drift.md — "hand-maintained lists drift").
STATUSES: frozenset[str] = frozenset({
    "on_going", "shipped", "blocked", "canceled", "stale", "deferred",
    "integrated-worktree-live",
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


def effective_project(row: dict) -> str:
    """The SHIP-CONSENT approval unit a pointer row belongs to.

    `project` is optional on a row; an UNMAPPED branch is its own project —
    the default is the branch name itself (never None, never guessed from a
    sibling). KB § PATTERNS/devops/ship-consent-riders.md § attribution.
    """
    proj = str(row.get("project") or "").strip()
    return proj or str(row.get("branch") or "")


def project_for_branch(branch: str, rows: list[dict]) -> str:
    """Resolve `branch` → project via its LATEST pointer row; an unknown
    branch (no pointer at all) defaults to the branch name."""
    row = _latest_per_branch(rows).get(branch)
    return effective_project(row) if row else branch


def _inherit_project(parent: str, rows: list[dict]) -> str | None:
    """An engineer inherits its PARENT's project (owner decision 2026-09-22:
    the approval unit is the project/roadmap, not the branch).

    Resolution, most → least specific:
      1. `parent` is itself a branch with a pointer carrying `project`;
      2. the most recent pointer dispatched by the SAME `parent` that carries
         an explicit `project` (siblings of one orchestrator share it).
    Returns None when neither resolves — the row then stays unmapped and
    `effective_project` falls back to the branch name (documented default).
    """
    if not parent:
        return None
    best = _latest_per_branch(rows)
    prow = best.get(parent)
    if prow and str(prow.get("project") or "").strip():
        return str(prow["project"]).strip()
    siblings = sorted(
        (r for r in rows if r.get("parent") == parent and str(r.get("project") or "").strip()),
        key=lambda r: r.get("ts", ""),
        reverse=True,
    )
    return str(siblings[0]["project"]).strip() if siblings else None


def _paths_overlap(a: list[str], b: list[str]) -> bool:
    """True iff two path lists share at least one common element."""
    sa = set(a or [])
    sb = set(b or [])
    return bool(sa & sb)


# ── FF-push-to-dev (shared idiom lifted to _ledger_push, N=3 DRY) ─────────────
def _push_ledger_to_dev(
    *,
    commit_msg: str,
    runner=None,
    dev_branch: str = "dev",
    remote: str = "origin",
) -> dict[str, Any]:
    """Stage ONLY branch-tree.ndjson+mirror → commit → rebase-onto-dev → FF-push.

    Thin delegate to the shared :func:`commit_and_ff_push_ledger` helper (the
    N=3 DRY lift). Idempotent: if neither the ledger nor its mirror is dirty
    (nothing to commit), returns ok=True with status=already_clean. After
    committing, the shared helper does fetch → divergence-guard → rebase onto
    origin/dev → FF-push, retried ONCE on a concurrent-push race; a non-ledger-
    ahead guard refusal or a rebase conflict is surfaced immediately with
    committed_locally=True (never retried, never force-resolved).
    """
    return commit_and_ff_push_ledger(
        runner=runner or _run,
        root=None,
        rel_paths=list(_ledger_rels()),
        dev_branch=dev_branch,
        remote=remote,
        commit_msg=commit_msg,
        already_committed=False,
        check_exists=LEDGER_PATH,
        _log_prefix="branch_pointer",
    )


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
    project: str | None = None,
    push_dev: bool = True,
    runner=None,
    dev_branch: str = "dev",
) -> dict[str, Any]:
    """Append a new pointer row for `branch` and (default) push to dev.

    `project` (optional) is the ship-consent approval unit. Omitted ⇒ inherited
    from `parent` (see `_inherit_project`); still unresolved ⇒ the key is left
    off and `effective_project` reads the branch name.

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
    if project is None:
        try:
            project = _inherit_project(parent, _read_dev_ledger(runner=runner))
        except Exception as exc:  # noqa: BLE001 — inheritance is advisory; say so
            logger.warning("branch_pointer.append: project inheritance failed: %s", exc)
            project = None
    if project and str(project).strip():
        row["project"] = str(project).strip()

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
    project: str | None = None,
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
    carried_project = project if project is not None else prev.get("project")
    if carried_project and str(carried_project).strip():
        row["project"] = str(carried_project).strip()

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
    project: str | None = None,
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
        if project is not None and effective_project(row) != project:
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
    project: str | None = None,
    runner=None,
) -> list[dict]:
    """Return the live map: all non-terminal pointers by default.

    `include_terminal=True` adds shipped/canceled/stale rows (full history).
    Default from_dev=True so a fresh agent gets the globally-consistent view.
    """
    all_rows = query(from_dev=from_dev, project=project, runner=runner)
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
            "            Optional: notes, worktree, session, project, push_dev (default True).\n"
            "            `project` = the ship-consent approval unit (noctus.dev.ship_consent);\n"
            "            omitted ⇒ inherited from parent's pointer; unmapped ⇒ branch name.\n"
            "  update  — append a delta row for an existing branch (latest-by-ts wins).\n"
            "            Required: branch. Optional: status, commit, paths, brief, notes, project,\n"
            "            push_dev (default True), from_dev (default True).\n"
            "  query   — resolve latest-per-branch from dev's copy.\n"
            "            Optional: status, branch, agent, project, paths_overlap, from_dev (default True).\n"
            "            `paths_overlap=[...]` returns branches whose collision zone intersects\n"
            "            (the pre-dispatch planner — detect collisions before touch).\n"
            "  list    — live map: all non-terminal pointers (include_terminal=True for full view).\n"
            "            Optional: from_dev (default True), include_terminal (default False), project.\n\n"
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
        project: str | None = None,
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
                project=project, push_dev=push_dev,
            )
        elif action == "update":
            if not branch:
                return {"ok": False, "error": "update requires: branch"}
            return update(
                branch=branch, status=status, commit=commit, paths=paths,
                brief=brief, notes=notes, project=project, push_dev=push_dev,
                from_dev=from_dev,
            )
        elif action == "query":
            return query(
                from_dev=from_dev, status=status, branch=branch, agent=agent,
                paths_overlap=paths_overlap, project=project,
            )
        elif action == "list":
            return list_pointers(from_dev=from_dev, include_terminal=include_terminal,
                                 project=project)
        else:
            return {
                "ok": False,
                "error": f"unknown action {action!r}; must be one of: append, update, query, list",
            }
