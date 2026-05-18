"""noctus.dev.mole — MCP exposure of the storage-hygiene `mole`.

MCP-first: `scripts/mole.sh` (+ the worktree-cleanup predicate it shares
with `scripts/cleanup-stale-worktrees.sh`) was bash-only. This wraps it
so an agent can scan/sweep storage waste — artifacts (regenerable
caches/builds), environments (venv/node_modules dup, advisory-only),
worktrees (stale `.claude/worktrees/agent-*/`).

Project cleanup is a DIFFERENT surface — already `noctus.dev.archive`.

═══ SAFE-GATE (what makes a sweep safe to execute) ═══════════════════════
`scripts/mole.sh` is destructive only under `mode="sweep", force=True`.
Its classifier NEVER removes:
  • a worktree with uncommitted changes,
  • a worktree whose branch is NOT merged-to-`main` — "merged" =
    reachable from `origin/main` by SHA-ancestry OR all commits present
    by PATCH-ID (our orchestrator FFs via cherry-pick → new SHA, same
    patch; the patch-id check covers that),
  • the main worktree, sibling/seed workspaces, `.env`, or migration
    files.
Additional operator gate (NOT enforced by the script — caller's duty):
  • Confirm NO other agent is mid-flight in a target worktree. A branch
    can be patch-id-merged while an agent still has that worktree open;
    sweeping it mid-flight destroys live work. `mode="scan"` first,
    eyeball the STALE/ORPHAN list, only then `sweep` with `force=True`.
`mode="sweep"` WITHOUT `force=True` is a **dry-run** (lists what would
go, deletes nothing) — the safe default this tool returns by default.
═════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Literal

from settings import REPO_ROOT
from workspace import resolve_caller_root


def run_mole(
    mode: Literal["scan", "sweep"] = "scan",
    scope: Literal["all", "artifacts", "environments", "worktrees"] = "all",
    force: bool = False,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Run `scripts/mole.sh <mode> [--scope] [--force] --json` and parse it.

    `force` is honored ONLY with `mode="sweep"` — and even then the
    script's own safe-gate (see module docstring) is the real guard.
    `scan` is always read-only. `sweep` without `force` is a dry-run.
    """
    root = resolve_caller_root(worktree_path) if worktree_path else REPO_ROOT
    script = root / "scripts" / "mole.sh"
    if not script.exists():
        return {
            "ok": False,
            "error": f"mole.sh not found at {script}",
            "executed": False,
        }

    argv = ["bash", str(script), mode]
    if scope != "all":
        argv.append(f"--{scope}")
    will_delete = mode == "sweep" and force
    if will_delete:
        argv.append("--force")
    argv.append("--json")

    try:
        proc = subprocess.run(
            argv, cwd=str(root), capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "mole.sh timed out (600s)", "executed": False}

    parsed: dict[str, Any] = {}
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    return {
        "ok": proc.returncode in (0, 1, 2, 3),
        "mode": mode,
        "scope": scope,
        "executed_destructive": will_delete,
        "dry_run": mode == "sweep" and not force,
        "exit_code": proc.returncode,
        "severity": parsed.get("severity"),
        "artifacts_mb": parsed.get("artifacts_mb"),
        "environments_mb": parsed.get("environments_mb"),
        "worktrees_stale": parsed.get("worktrees_stale"),
        "next_action": parsed.get("next_action"),
        "safe_gate": (
            "sweep deletes ONLY merged-to-main (SHA-ancestry|patch-id) "
            "worktrees + regenerable artifacts; never uncommitted / "
            "unmerged / main / siblings / .env / migrations. Caller MUST "
            "also confirm no agent is mid-flight in a target worktree. "
            "Run scan first; sweep needs force=True (else dry-run)."
        ),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-12:]),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.mole",
        description=(
            "Storage-hygiene mole (custodial sibling of keeper/hound). "
            "`mode='scan'` (default, READ-ONLY) reports artifacts/env/"
            "worktree waste + severity + next_action. `mode='sweep'` "
            "removes it — but ONLY with `force=True`; without force it is "
            "a DRY-RUN. SAFE-GATE: the script never deletes uncommitted / "
            "unmerged / main / sibling / .env / migration content; it "
            "removes a worktree only when its branch is merged-to-main by "
            "SHA-ancestry OR patch-id. Caller's extra duty: confirm no "
            "other agent is mid-flight in a target worktree before "
            "force-sweeping. Project cleanup is the separate "
            "noctus.dev.archive tool. Pass worktree_path when called from "
            "inside a git worktree. See KB § PATTERNS/storage-hygiene.md."
        ),
    )
    def _mole(
        mode: Literal["scan", "sweep"] = "scan",
        scope: Literal["all", "artifacts", "environments", "worktrees"] = "all",
        force: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return run_mole(
            mode=mode, scope=scope, force=force, worktree_path=worktree_path
        )


__all__ = ["run_mole", "register"]
