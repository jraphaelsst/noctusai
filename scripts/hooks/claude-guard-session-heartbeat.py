#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit hook - keep an alive session's steward-role heartbeat fresh.

A session's guardian/steward role row only refreshed when the session called `release_steward`, so a
long-quiet but ALIVE session aged toward 'dead' (`StewardStore.session_state`: recorded pid gone AND heartbeat
older than the TTL). This hook calls the existing `StewardStore.role_touch(session_id, claude_pid)` for the
payload's session_id - nothing else: it never claims, hands off or reassigns a lease or role, never touches
another session's rows, and `role_touch` never touches the lease itself.

ADVISORY by construction (deliberately NOT `run_guard`, which fails closed): always exits 0, fails OPEN, a ~1s
internal deadline, and a per-session throttle (at most once per THROTTLE_S). A telemetry row is written on
ERROR only. The pid it records is the nearest ancestor process named `claude` (never a transient shell); when
none is found only the heartbeat is refreshed. Stdlib-only.
KB § PATTERNS/devops/release-steward.md.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parents[2]
STEWARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "release_steward.py"
THROTTLE_S = 60
DEADLINE_S = 1


def claude_ancestor_pid(start: int | None = None, max_hops: int = 6) -> int | None:
    """Nearest ancestor whose command is `claude` (a hook runs under a shell, so ppid alone is not Claude Code)."""
    pid = start if start is not None else os.getppid()
    for _ in range(max_hops):
        if pid <= 1:
            return None
        out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=0.5, check=False).stdout.strip()
        if not out:
            return None
        ppid, _, comm = out.partition(" ")
        if os.path.basename(comm.strip()) == "claude":
            return pid
        try:
            pid = int(ppid)
        except ValueError:
            return None
    return None


def throttled(root: Path, session_id: str, now: float, window: float = THROTTLE_S) -> bool:
    """True when this session was touched within `window`; otherwise records `now` and returns False."""
    marker = root / "heartbeat-throttle" / "".join(c for c in session_id if c.isalnum() or c in "-_")[:80]
    try:
        if now - marker.stat().st_mtime < window:
            return True
    except OSError:
        pass
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(now), encoding="utf-8")
    os.utime(marker, (now, now))
    return False


def _default_root() -> Path:
    """Mirrors `release_steward.default_root` (NOCTUS_STEWARD_DIR, else ~/.noctus) WITHOUT importing it; a test pins the parity."""
    return Path(os.environ.get("NOCTUS_STEWARD_DIR") or Path.home() / ".noctus")


def _telemetry(reason: str, session_id: str | None) -> None:
    try:
        from _guard_failclosed import log_event
        log_event("session-heartbeat", "error", reason, {"session_id": session_id},
                  extra={"kind": "hook", "owner": "tooling-engineer", "source": "hook"})
    except Exception:  # noqa: BLE001 - telemetry never changes the (always-0) outcome
        pass


def touch(payload: dict, *, root: Path | None = None, now: float | None = None,
          claude_pid: int | None = None, find_pid=claude_ancestor_pid) -> str:
    """The whole job, injectable for tests. Returns `touched` | `throttled` | `no-session`."""
    session_id = payload.get("session_id")
    if not session_id or not isinstance(session_id, str):
        return "no-session"
    base = root if root is not None else _default_root()
    clock = now if now is not None else time.time()
    if throttled(Path(base), session_id, clock):  # FIRST: a throttled prompt pays no release_steward module load
        return "throttled"
    from _guard_failclosed import load_module
    mod = load_module(STEWARD)
    pid = claude_pid
    if pid is None:
        try:
            pid = find_pid()
        except Exception:  # noqa: BLE001 - no pid => heartbeat only
            pid = None
    mod.StewardStore(Path(base)).role_touch(session_id, pid)
    return "touched"


def main() -> int:
    session_id = None
    try:
        def _on_alarm(_s, _f):
            raise TimeoutError(f"deadline {DEADLINE_S}s")
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(DEADLINE_S)
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
        touch(payload if isinstance(payload, dict) else {})
    except BaseException as exc:  # noqa: BLE001 - advisory: ANY failure is open, recorded, exit 0
        _telemetry(f"{type(exc).__name__}: {exc}"[:200], session_id)
    finally:
        try:
            signal.alarm(0)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
