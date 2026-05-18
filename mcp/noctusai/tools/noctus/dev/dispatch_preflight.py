"""noctus.dev.dispatch_preflight — one call before any engineer dispatch.

Turns R2 (verify-seed-on-fork-base) + R4 (merge-debt) + worktree-collision
from "remember to check" into "the tool checked". The base-mismatch class
this catches cost a full two-wave re-dispatch this session (engineers
fork origin/main; unmerged feature-branch lifts are invisible to them).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from settings import REPO_ROOT


def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), capture_output=True, text=True, timeout=120,
        cwd=cwd or str(REPO_ROOT),
    )


def dispatch_preflight(
    target_paths: list[str],
    wrap_paths: list[str] | None = None,
    base_ref: str = "origin/main",
) -> dict:
    """Pre-flight a brief. `wrap_paths` = seed paths the brief will
    wrap/consume (must exist on the engineers' fork base `base_ref`);
    `target_paths` = files the brief will edit (checked for live-worktree
    collision)."""
    missing_on_base: list[str] = []
    for p in wrap_paths or []:
        r = _run("git", "ls-tree", base_ref, "--", p)
        if not r.stdout.strip():
            missing_on_base.append(p)

    colliding: list[dict] = []
    wt_root = REPO_ROOT / ".claude" / "worktrees"
    if wt_root.exists():
        for wt in wt_root.glob("agent-*"):
            if not (wt / ".git").exists():
                continue
            dirty = {
                l[3:] for l in _run(
                    "git", "-C", str(wt), "status", "--porcelain"
                ).stdout.splitlines() if l.strip()
            }
            hits = sorted(t for t in target_paths if t in dirty)
            if hits:
                colliding.append({"worktree": wt.name, "paths": hits})

    md = _run("bash", str(REPO_ROOT / "scripts" / "merge-debt-monitor.sh"), "--json")
    merge_debt = md.stdout.strip().splitlines()[-1] if md.stdout.strip() else None

    ok = not missing_on_base and not colliding
    return {
        "ok": ok,
        "base_ref": base_ref,
        "missing_on_base": missing_on_base,
        "colliding_worktrees": colliding,
        "merge_debt": merge_debt,
        "recommendation": (
            "CLEAR to dispatch."
            if ok else
            (("BLOCK: wrap_paths absent on the fork base — engineers will "
              "STOP (R2 base-mismatch). Phase-push origin/main current "
              "first OR base the brief on the integration branch. "
              if missing_on_base else "")
             + ("BLOCK: target paths are dirty in a live agent worktree — "
                "collision risk; serialize or re-scope." if colliding else ""))
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_preflight",
        description=(
            "Pre-flight an engineer brief BEFORE dispatch: verifies "
            "wrap_paths (seed symbols the brief consumes) exist on the "
            "engineers' fork base (R2 — unmerged lifts are invisible to "
            "worktrees), target_paths don't collide with a live agent "
            "worktree, + reports merge-debt severity. Returns ok + a "
            "block/clear recommendation. Structurally kills the "
            "base-mismatch class that cost a 2-wave re-dispatch."
        ),
    )
    def _preflight(
        target_paths: list[str],
        wrap_paths: list[str] | None = None,
        base_ref: str = "origin/main",
    ) -> dict:
        return dispatch_preflight(target_paths, wrap_paths=wrap_paths, base_ref=base_ref)


__all__ = ["dispatch_preflight", "register"]
