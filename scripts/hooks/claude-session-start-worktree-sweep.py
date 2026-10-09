#!/usr/bin/env python3
"""SessionStart hook - crash backstop for worktree reclamation.

`task_branch integrate` tears its own worktree down; this reclaims the ones a
session abandoned (crash, kill, `keep_worktree=True`, forgot). 2026-10-09: 37
fully-merged, clean worktrees (9.9 GB) made VS Code list ~42 repos.

It runs the EXISTING `cleanup_stale_worktrees` (via cli.py) with force=True
AND --cleanup-respect-min-age: every safety guard stays on (dirty / stash /
lock / live pointer / recent-mtime 60 min / min-age 60 min), so a peer
session's brand-new worktree is never taken, however many sessions start at
once. A lock file makes concurrent starters skip instead of racing.

Advisory by construction: always exits 0, silent on a no-op, one stdout line
when something was removed, failures only to stderr. Stdlib-only.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 50  # < the 60 s `timeout` in .claude/settings.json


def primary_root(start: Path) -> Path | None:
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       cwd=str(start), capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip()).parent


def python_for(root: Path) -> str:
    venv = root / "venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def summarize(payload: dict) -> str:
    """One line for what was removed; '' when nothing was."""
    removed = int(payload.get("removed") or 0)
    if removed <= 0:
        return ""
    names = [Path(p).name for p in payload.get("stale", [])]
    return f"noc: reclaimed {removed} merged worktree(s): {', '.join(names[:8])}" + (
        f" (+{len(names) - 8} more)" if len(names) > 8 else "")


def sweep(root: Path, *, timeout: float = TIMEOUT_S) -> str:
    wt_dir = root / ".claude" / "worktrees"
    if not wt_dir.is_dir() or not any(wt_dir.iterdir()):
        return ""
    cli = root / "mcp" / "noctusai" / "cli.py"
    if not cli.exists():
        return ""
    lock = (root / ".git" / "noc-worktree-sweep.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return ""  # a peer session is sweeping right now
    try:
        r = subprocess.run(
            [python_for(root), str(cli), "--cleanup-stale-worktrees", "--force",
             "--cleanup-respect-min-age"],
            cwd=str(root), capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            print(f"[noc-sweep] cli exited {r.returncode}: {r.stderr.strip()[:200]}", file=sys.stderr)
            return ""
        return summarize(json.loads(r.stdout))
    finally:
        lock.close()


def main() -> int:
    try:
        sys.stdin.read()  # drain hook payload
        start = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        root = primary_root(start)
        if root is None:
            return 0
        line = sweep(root)
        if line:
            print(line)
    except Exception as e:  # noqa: BLE001 - advisory; never block a session start
        print(f"[noc-sweep] skipped: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
