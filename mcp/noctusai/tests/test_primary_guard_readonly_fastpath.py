"""Read-only tool calls never pay for the write guard's expensive path (2026-11-12).

Root cause measured in .claude/cache/guard-events.ndjson: a plain `grep`/`ls` Bash call still ran
`discover_context` (3 git subprocesses), the hook-integrity git probe, the auto-claim and a
`git status` baseline -- seconds under load, past the 8s alarm, so a read got DENIED "timed out".

Real subprocess runs of the real hook; `git` is a slow shim on PATH (no patching of the guard).
Asymmetry: a read-only call that still times out is ALLOWED with a logged warning; a write stays fail-closed.
"""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "scripts" / "hooks" / "claude-guard-primary-write.py"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "hooks"))
import _guard_failclosed as gf  # noqa: E402

BUDGET_S = 1.0  # read-only latency budget (idle machine ~0.1s; the shim below would cost 20s)


def _slow_git(tmp_path: Path) -> tuple[Path, Path]:
    shim = tmp_path / "bin"
    shim.mkdir()
    calls = tmp_path / "git-calls.log"
    real = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
    sh = shim / "git"
    sh.write_text(f'#!/bin/sh\necho "$@" >> {calls}\nsleep 20\nexec {real} "$@"\n')
    sh.chmod(sh.stat().st_mode | stat.S_IEXEC)
    return shim, calls


def _run(tmp_path: Path, tool: str, tool_input: dict, shim: Path):
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}",
           "NOCTUS_GUARD_EVENT_LOG": str(tmp_path / "events.ndjson")}
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(REPO_ROOT), "session_id": "ro-fast"}
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True,
                       text=True, env=env, timeout=60)
    return p, time.monotonic() - t0


def test_read_only_bash_makes_no_git_call_and_is_fast(tmp_path):
    shim, calls = _slow_git(tmp_path)
    for cmd in ("grep -rn foo mcp/noctusai/tools | head -5", "ls -la", "cat README.md"):
        p, dt = _run(tmp_path, "Bash", {"command": cmd}, shim)
        assert p.returncode == 0 and "deny" not in p.stdout, (cmd, p.stdout)
        assert dt < BUDGET_S, (cmd, dt)
    assert not calls.exists()  # no probe of the guard's own before a read


def test_write_bash_still_takes_the_full_path(tmp_path):
    shim, calls = _slow_git(tmp_path)
    _run(tmp_path, "Bash", {"command": "touch x.txt"}, shim)
    assert calls.exists()  # a write still discovers the checkout layout (fail-closed legs: see run_guard test)


def test_run_guard_timeout_allows_read_only_with_logged_warning(tmp_path):
    log = tmp_path / "ev.ndjson"
    out = io.StringIO()
    rc = gf.run_guard("t", lambda payload: time.sleep(2), stdin=io.StringIO('{"tool_name":"Bash"}'), stdout=out,
                      deadline_s=0.2, event_log=log, fail_open_when=lambda payload: True)
    assert rc == 0 and out.getvalue() == ""
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows[-1]["outcome"] == "allow-timeout"


def test_run_guard_timeout_denies_write(tmp_path):
    out = io.StringIO()
    gf.run_guard("t", lambda payload: time.sleep(2), stdin=io.StringIO('{"tool_name":"Edit"}'), stdout=out,
                 deadline_s=0.2, event_log=tmp_path / "ev.ndjson", fail_open_when=lambda payload: False)
    assert "deny" in out.getvalue()
