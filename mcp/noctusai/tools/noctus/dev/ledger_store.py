"""noctus.dev.ledger_store — the agent-facing surface of `_ledger_store`.

The append-only project-history ledgers live on the orphan `ledgers` branch
(owner decision 2026-09-24). Writers reach it through `_ledger_store.open_ledger`;
this tool is the operator's handle on the same store (MCP-first rule — a new
automation is a `noctus.dev.*` tool, never a bare script):

  status     tip sha + per-ledger row counts on origin/ledgers + spooled rows
  read       tail a ledger (dual-read: origin/ledgers ∪ the origin/dev copy)
  flush      publish rows a failed/offline append left in the local spool
  bootstrap  S0 — create origin/ledgers seeded from origin/dev's copies;
             DRY-RUN unless confirm=True; refuses when the branch exists

KB § PATTERNS/common/ledger-store.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.noctus.dev import _ledger_store as ls

ACTIONS = ("status", "read", "flush", "bootstrap")

README = """# ledgers — append-only project-history ledgers (orphan branch)

Written ONLY by git plumbing (`mcp/noctusai/tools/noctus/dev/_ledger_store.py`):
hash-object -> mktree -> commit-tree -> fast-forward push, retried on the race.
Never check this branch out, never force-push it, never delete it.

Seeded 2026-09-24 from origin/dev's `project-history/` copies. Until the dev
copies are deleted (roadmap `project-history/roadmaps/ledgers-off-dev-2026-09.md`,
deferred S4) every reader merges this branch with the dev copy.

Inspect: `noctus.dev.ledger_store action='status'` / `action='read' name=<file>`.
"""


def _dev_copy(store: ls.GitLedgerStore, name: str, ref: str = "origin/dev") -> str | None:
    r = store._git("cat-file", "-e", f"{ref}:project-history/{name}")
    if r.returncode != 0:
        return None
    return store._git("show", f"{ref}:project-history/{name}").stdout


def ledger_store(action: str = "status", name: str | None = None, tail: int = 20,
                 confirm: bool = False, repo_root: str | None = None) -> dict[str, Any]:
    if action not in ACTIONS:
        return {"ok": False, "error": f"action must be one of {ACTIONS}; got {action!r}"}
    store = ls.default_store(Path(repo_root) if repo_root else None)

    if action == "bootstrap":
        store._git("fetch", "--quiet", store.remote)
        seed: dict[str, str] = {"README.md": README}
        missing: list[str] = []
        for n in ls.MOVED_LEDGERS:
            text = _dev_copy(store, n)
            if text is None:
                missing.append(n)
            else:
                seed[n] = text
        plan = {"files": {k: len(v.splitlines()) for k, v in seed.items()},
                "absent_on_dev": missing}
        if not confirm:
            return {"ok": True, "status": "planned", "dry_run": True, **plan}
        out = store.bootstrap(seed, message="ledgers: seed from origin/dev project-history copies")
        return {**out, **plan}

    if action == "flush":
        return store.flush(message="flush spooled rows")

    if action == "read":
        if not name:
            return {"ok": False, "error": "name is required for action='read'"}
        led = ls.GitLedger(name=name, store=store)
        text, err = ls.read_dual(led, _dev_copy(store, name) or "", fetch=True)
        lines = text.splitlines()
        return {"ok": err is None, "error": err, "name": name, "rows": len(lines),
                "tail": lines[-max(0, tail):] if tail else []}

    # status
    ok, err = store.fetch()
    tip = store.tip()
    per: dict[str, Any] = {}
    if tip:
        for n in ls.MOVED_LEDGERS:
            per[n] = {"rows": len(store._blob(tip, n).splitlines()),
                      "spooled": len(store.pending_text(n).splitlines())}
    return {"ok": tip is not None, "branch": f"{store.remote}/{store.branch}", "tip": tip,
            "fetch_error": None if ok else err, "ledgers": per,
            "error": None if tip else "origin/ledgers not found — run action='bootstrap'"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.ledger_store",
        description=(
            "The append-only project-history ledgers (branch-tree, worktree-salvage, "
            "auto-improvement, vector-costs/-signals/-calibration, dispatch-budget, "
            "absorptions, ship-consent) live on the orphan `ledgers` branch on origin, "
            "written by git plumbing only (hash-object/mktree/commit-tree/FF push, retried "
            "on the race; never a checkout). action='status' (tip + row counts + locally "
            "spooled rows) · 'read' name=<file> tail=N (dual-read origin/ledgers ∪ the "
            "origin/dev copy) · 'flush' (publish rows an offline append left spooled) · "
            "'bootstrap' (S0: seed origin/ledgers from origin/dev; dry-run unless "
            "confirm=True; refuses when it exists). KB § PATTERNS/common/ledger-store.md."
        ),
    )
    def _ledger_store_tool(action: str = "status", name: str = "", tail: int = 20,
                           confirm: bool = False) -> dict:
        return ledger_store(action=action, name=name or None, tail=tail, confirm=confirm)


__all__ = ["ledger_store", "register", "README", "ACTIONS"]
