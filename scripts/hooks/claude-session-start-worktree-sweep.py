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

2026-10-09: the child FIRST fast-forwards the primary checkout to origin/dev
(`mcp/noctusai/primary_ff.py`, loaded by path; ff-only, refuses a non-dev
branch / detached HEAD / tracked edits / diverged dev, each reported in the
summary line). The sweep and every "run the primary's cli.py" path otherwise
execute stale toolkit code until someone fast-forwards by hand.
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 900  # the detached child may take its time; nobody waits on it
LAST_NAME = "noc-worktree-sweep.last"
FF_LOCK_NAME = "noc-primary-ff.lock"
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


def scrub_dotenvs(root: Path, *, timeout: float = TIMEOUT_S) -> str:
    """Convert worktrees whose `.env` still SYMLINKS the primary's (production
    secrets, the 2026-10-09 incident) into the scrubbed file — every session
    start, so a worktree created before the fix is fixed without anyone
    re-wiring it. Summary line ('' when nothing was converted)."""
    cli = root / "mcp" / "noctusai" / "cli.py"
    if not cli.exists():
        return ""
    r = subprocess.run([python_for(root), str(cli), "--scrub-worktree-dotenvs"],
                       cwd=str(root), capture_output=True, text=True, timeout=timeout)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        print(f"[noc-sweep] dotenv scrub: {r.stderr.strip()[:200]}", file=sys.stderr)
        return ""
    n = len(data.get("converted", []))
    failed = len(data.get("failed", []))
    parts = [f"{n} worktree .env symlink(s) scrubbed"] if n else []
    if failed:
        parts.append(f"{failed} worktree .env left alone (not ours)")
    return "; ".join(parts)


def fast_forward_primary(root: Path) -> str:
    """ff-only the primary to origin/dev; the summary line ('' if up to date)."""
    mod_path = root / "mcp" / "noctusai" / "primary_ff.py"
    if not mod_path.exists():
        return ""
    lock = (root / ".git" / FF_LOCK_NAME).open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return ""  # a peer session is fast-forwarding right now
    try:
        spec = importlib.util.spec_from_file_location("_noc_primary_ff", mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.summary_line(mod.ff_primary_to_dev(str(root), fetch=True))
    finally:
        lock.close()


def run_child(root: Path) -> None:
    """Detached-child entry: fast-forward the primary, sweep, then record a
    non-empty summary as unseen. The FF runs first so the sweep (and every
    later cli.py run from the primary) uses the code that is on dev."""
    lines = [fast_forward_primary(root), scrub_dotenvs(root), sweep(root)]
    line = " | ".join(x for x in lines if x)
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
        spawn_detached(root)  # always: the primary FF runs even with no worktrees
    except Exception as e:  # noqa: BLE001 - advisory; never block a session start
        print(f"[noc-sweep] skipped: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
