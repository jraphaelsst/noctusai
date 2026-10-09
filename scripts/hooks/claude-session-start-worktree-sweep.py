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

NEVER blocks session start (removing 37 worktrees took >120 s and the owner
opens several sessions at once): the hook only spawns the sweep DETACHED
(`start_new_session`) and returns at once. The detached child holds the flock,
runs the sweep and records its one-line summary in `<git-common-dir>/
noc-worktree-sweep.last`; the NEXT session start prints that line once if it
is new. Advisory by construction: always exits 0, failures only to stderr.
Stdlib-only.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 900  # the detached child may take its time; nobody waits on it
LAST_NAME = "noc-worktree-sweep.last"
LOCK_NAME = "noc-worktree-sweep.lock"


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
    """The sweep itself (runs in the detached child). Returns the summary line."""
    wt_dir = root / ".claude" / "worktrees"
    if not wt_dir.is_dir() or not any(wt_dir.iterdir()):
        return ""
    cli = root / "mcp" / "noctusai" / "cli.py"
    if not cli.exists():
        return ""
    lock = (root / ".git" / LOCK_NAME).open("w")
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


def run_child(root: Path) -> None:
    """Detached-child entry: sweep, then record a non-empty summary as unseen."""
    line = sweep(root)
    if line:
        (root / ".git" / LAST_NAME).write_text(json.dumps({"line": line, "shown": False}))


def spawn_detached(root: Path) -> None:
    """Start the sweep in its own session and return immediately."""
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child", str(root)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True)


def take_previous_line(root: Path) -> str:
    """The previous run's summary if not yet shown (marks it shown), else ''."""
    f = root / ".git" / LAST_NAME
    try:
        data = json.loads(f.read_text())
    except (OSError, ValueError):
        return ""
    if data.get("shown") or not data.get("line"):
        return ""
    f.write_text(json.dumps({"line": data["line"], "shown": True}))
    return str(data["line"])


def main() -> int:
    try:
        if len(sys.argv) > 2 and sys.argv[1] == "--child":
            run_child(Path(sys.argv[2]))
            return 0
        sys.stdin.read()  # drain hook payload
        start = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        root = primary_root(start)
        if root is None:
            return 0
        line = take_previous_line(root)
        if line:
            print(line)
        wt_dir = root / ".claude" / "worktrees"
        if wt_dir.is_dir() and any(wt_dir.iterdir()):
            spawn_detached(root)
    except Exception as e:  # noqa: BLE001 - advisory; never block a session start
        print(f"[noc-sweep] skipped: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
