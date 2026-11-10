"""The primary-write guard never spends the hook's budget on its best-effort legs (2026-11-10).

A read-only reviewer's scratchpad-only Bash was refused with "guard timed out (failed closed) after 8s": one guard
call makes several git probes, each allowed 10s on its own, and the worktree auto-claim waited on the claims flock
without bound. Under load that summed past run_guard's 8s alarm. Now one per-call deadline bounds every probe, the
auto-claim waits at most ~1s for the lock (claiming is an optimization), and the measurement baseline is skipped
when little budget is left. The refuse/allow decision itself still fails closed.

Real subprocess runs of the real hook on a throwaway repo; no patching of the guard.
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "scripts" / "hooks" / "claude-guard-primary-write.py"
GUARD_PATH = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "primary_write_guard.py"


def _guard():
    spec = importlib.util.spec_from_file_location("noc_pwg_deadline_ut", GUARD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pwg = _guard()


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def layout(tmp_path: Path) -> tuple[Path, Path]:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git("init", "-q", "-b", "dev", cwd=primary)
    _git("config", "user.email", "t@example.com", cwd=primary)
    _git("config", "user.name", "t", cwd=primary)
    (primary / "app.py").write_text("x = 1\n")
    (primary / ".gitignore").write_text(".claude/cache/\n.claude/worktrees/\n")
    _git("add", ".", cwd=primary)
    _git("commit", "-q", "-m", "init", cwd=primary)
    wt = primary / ".claude" / "worktrees" / "feat-x"
    _git("worktree", "add", "-q", "-b", "feat/x", str(wt), cwd=primary)
    return primary.resolve(), wt.resolve()


@pytest.fixture(autouse=True)
def _no_deadline_leak():
    yield
    pwg.set_deadline(None)


def _hold_claims_lock(primary: Path):
    path = primary / pwg.CLAIMS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(str(path) + ".lock", "a")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def test_git_probes_never_outlive_the_hook_deadline():
    assert pwg._git_timeout() == pwg._GIT_TIMEOUT_MAX_S  # outside a hook: unchanged
    pwg.set_deadline(0.5)
    assert pwg._git_timeout() <= 0.5
    pwg.set_deadline(-1)
    assert pwg._git_timeout() == 0.1  # past the deadline: a near-instant probe that reads as unanswered


def test_a_bounded_claim_reports_busy_instead_of_queueing(layout):
    primary, wt = layout
    held = _hold_claims_lock(primary)
    try:
        t0 = time.monotonic()
        res = pwg.write_claim(str(primary), "s1", str(wt), wait_s=0.3)
        assert res["status"] == "busy" and time.monotonic() - t0 < 2.0
    finally:
        held.close()
    assert pwg.write_claim(str(primary), "s1", str(wt), wait_s=0.3)["status"] == "claimed"


def test_auto_claim_is_skipped_when_the_budget_is_nearly_spent(layout):
    primary, wt = layout
    ctx = pwg.discover_context(str(wt))
    pwg.set_deadline(pwg.BEST_EFFORT_MIN_LEFT_S - 0.5)
    assert pwg.auto_claim("Bash", {"command": "ls"}, "s1", str(wt), ctx) is None
    assert "s1" not in pwg.read_claims(str(primary))


def test_the_hook_answers_promptly_while_another_session_holds_the_claims_lock(layout):
    """The incident shape: before the fix the auto-claim blocked on the flock until run_guard's 8s alarm refused."""
    primary, wt = layout
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "reviewer",
               "tool_input": {"command": "ls"}, "cwd": str(wt), "transcript_path": "/dev/null", "tool_use_id": "t"}
    held = _hold_claims_lock(primary)
    try:
        t0 = time.monotonic()
        proc = subprocess.run(["/usr/bin/python3", str(HOOK)], input=json.dumps(payload), capture_output=True,
                              text=True, timeout=30,
                              env={**{k: v for k, v in os.environ.items() if k != "NOCTUS_ALLOW_PRIMARY_WRITE"},
                                   "NOCTUS_GUARD_EVENT_LOG": str(primary / "guard-events.ndjson")})
        took = time.monotonic() - t0
    finally:
        held.close()
    assert proc.returncode == 0, proc.stderr
    assert "timed out" not in proc.stdout, proc.stdout
    assert not proc.stdout.strip(), proc.stdout  # allowed: `ls` in a worktree
    assert took < 5.0, took
