"""noctus.dev.branch_pointer — the global live map of git-tree × claude-tree.

Append-only ndjson ledger (`branch-tree.ndjson`) tracking branch ownership,
collision zones, and agent coordination. Since 2026-09-24 it lives on the
ORPHAN `origin/ledgers` branch, written by git plumbing through `_ledger_store`
— a pointer write is never a commit on dev (465 `chore(branch-pointer)` dev
commits since 2026-08-01 were this ledger). Reads are the DUAL-READ
(origin/ledgers ∪ the legacy `project-history/branch-tree.ndjson` dev copy)
until S4 of `project-history/roadmaps/ledgers-off-dev-2026-09.md`, so a pointer
a peer's stale-code session still pushes to dev is never invisible.

KB § CONTEXT/PATTERNS/architect/branch-tree-tracking.md.

Actions
-------
append  Create a new pointer row (first claim on a branch, pre-self-branch).
update  Append a delta row for an existing branch (carries forward last values
        + the supplied overrides — latest-by-ts wins per branch).
query   Resolve latest-per-branch from dev's copy; supports filtering by
        status, branch, agent, and collision-zone overlap.
list    Live map: all non-terminal pointers (add terminal with include_terminal).

Publish idiom (origin/ledgers, plumbing only)
---------------------------------------------
`push_dev=True` (default; the name predates the move) publishes the row to
origin/ledgers at once: fetch → hash-object → mktree → commit-tree → FF push,
retried on the race (KB § PATTERNS/common/ledger-store.md). `push_dev=False`
spools the row locally (read-your-writes holds) for the next publish. The
`branch-tree.mirror.ndjson` copy was DELETED the same day (owner decision) —
one ledger, no parity to keep.

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

from tools.noctus.dev._ledger_store import (
    Ledger,
    LedgerStoreError,
    merge_ndjson_text,
    open_ledger,
)

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# The legacy dev copy — the dual-read source until S4 and the Fake store's
# backing file. LEDGER_ROOT (never REPO_ROOT): must resolve to the PRIMARY
# checkout even when the MCP server booted with cwd inside a worktree (see
# workspace.get_ledger_root() docstring).
LEDGER_REL = "project-history/branch-tree.ndjson"
LEDGER_PATH: Path = LEDGER_ROOT / LEDGER_REL
LEDGER_NAME = "branch-tree.ndjson"
# The deleted mirror's path — kept ONLY so a push of a stale-code peer that
# still writes it stays cache-exempt until S4. Nothing here writes it any more.
MIRROR_NAME = "branch-tree.mirror.ndjson"
MIRROR_REL = "project-history/" + MIRROR_NAME

# ── Cache-exemption sentinel ──────────────────────────────────────────────────
# ONLY these paths are exempt — any other staged file re-enables cache refresh.
_CACHE_EXEMPT_PATHS: frozenset[str] = frozenset({LEDGER_REL, MIRROR_REL})


def _ledger() -> Ledger:
    """The branch-tree ledger on the store — resolved per call so a patched
    ``LEDGER_PATH`` (tests) relocates the Fake."""
    return open_ledger(LEDGER_NAME, LEDGER_PATH)


def _write_row(row: dict[str, Any], *, publish: bool, message: str) -> dict[str, Any]:
    """Append one pointer row through the ledger store (origin/ledgers).

    Returns the store result; ``status='pending'`` means the row is durably
    spooled on this clone (readable here) and publishes with the next write."""
    return _ledger().append([json.dumps(row, ensure_ascii=False)],
                            message=message, publish=publish)


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


def _parse_rows(text: str) -> list[dict]:
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


def _store_text() -> str:
    """origin/ledgers' copy (+ this clone's spooled rows). A store read failure
    is LOGGED and the dev copy still answers — the S2 dual-read contract."""
    try:
        return _ledger().read_text()
    except LedgerStoreError as exc:
        logger.warning("branch_pointer: origin/ledgers unreadable (%s) — dev copy only", exc)
        return ""


def _read_dev_ledger(runner=None) -> list[dict]:
    """The GLOBAL map: origin/ledgers ∪ origin/dev's legacy copy (dual-read).

    The dev half is ``git show origin/dev:<path>`` (the local file when
    origin/dev is unavailable, e.g. no remote or an injected test runner);
    the store half is origin/ledgers. Exact-duplicate rows collapse (the S0
    seed put every pre-move row in both); resolution is latest-by-ts, so the
    merged order does not matter.
    """
    run = runner or _run
    rc, out, _err = run(["git", "show", f"origin/dev:{LEDGER_REL}"])
    if rc == 0:
        dev_text = out
    else:
        dev_text = LEDGER_PATH.read_text(encoding="utf-8") if LEDGER_PATH.exists() else ""
    return _parse_rows(merge_ndjson_text(dev_text, _store_text()))


def _read_local_ledger() -> list[dict]:
    """``from_dev=False``: this checkout's dev copy ∪ the store."""
    dev_text = LEDGER_PATH.read_text(encoding="utf-8") if LEDGER_PATH.exists() else ""
    return _parse_rows(merge_ndjson_text(dev_text, _store_text()))


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

    push_dev=True (default): publish the row to origin/ledgers at once so every
    agent sees the updated map in real time (the no-skip guarantee) — never a
    commit on dev. push_dev=False spools it for the next publish.
    `runner` is only used for the dual-read's `git show origin/dev:…` half.
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

    push_result = _write_row(row, publish=push_dev,
                             message=f"branch-pointer {status} — {agent} on {branch}")
    result: dict[str, Any] = {"ok": True, "row": row, "ledger_path": f"origin/ledgers:{LEDGER_NAME}",
                              "push": push_result}
    if push_dev and not push_result.get("ok"):
        logger.warning(
            "branch_pointer.append: publish to origin/ledgers failed for %s (%s) — "
            "row is spooled locally and publishes with the next write",
            branch, push_result.get("error"))
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
    rows = _read_dev_ledger(runner=runner) if from_dev else _read_local_ledger()
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

    push_result = _write_row(row, publish=push_dev,
                             message=f"branch-pointer {new_status} — {row['agent']} on {branch}")
    result: dict[str, Any] = {"ok": True, "row": row, "ledger_path": f"origin/ledgers:{LEDGER_NAME}",
                              "push": push_result}
    if push_dev and not push_result.get("ok"):
        logger.warning(
            "branch_pointer.update: publish to origin/ledgers failed for %s (%s) — "
            "row is spooled locally and publishes with the next write",
            branch, push_result.get("error"))
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
    rows = _read_dev_ledger(runner=runner) if from_dev else _read_local_ledger()
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
            "PUBLISH  the ledger lives on the ORPHAN origin/ledgers branch (git plumbing, never a "
            "commit on dev — 2026-09-24). push_dev=True (default) publishes the row at once "
            "(FF push, retried on the race); push_dev=False spools it for the next publish. "
            "Reads merge origin/ledgers with the legacy dev copy. "
            "KB § CONTEXT/PATTERNS/architect/branch-tree-tracking.md · "
            "KB § PATTERNS/common/ledger-store.md."
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
