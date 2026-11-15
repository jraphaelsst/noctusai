"""Filing by construction (2026-11-15): a filing queues for the heavy slot instead of bouncing (A), a refused request
exits non-zero with its own code (B), and a landed branch's tracking pointer is closed at landing / healed at push (C).

Seams only (clock / executor / injected runner / real git in tmp): nothing of ours is monkeypatched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.noctus.dev import branch_pointer as bp
from tools.noctus.dev import hw_admission as hw
from tools.noctus.dev import release_steward as rs
from tools.noctus.dev import task_branch as T
from tools.noctus.dev.compliance import check_stale_branch_pointers

REPO = Path(__file__).resolve().parents[3]
KNOBS = {"max_heavy": 1, "min_cpu_idle_pct": 50, "cpu_sample_s": 1, "min_reclaimable_mb": 1536,
         "max_swapout_per_s": 50, "max_claude_sessions_advisory": 3, "wait_s": 0, "poll_s": 0}
GOOD = {"cpu_idle_pct": 80.0, "reclaimable_mb": 3000, "swapout_per_s": 0.0, "claude_sessions": 2}
PEER = "22222222-bbbb"


@pytest.fixture()
def hw_env(tmp_path, monkeypatch):
    budget = tmp_path / "budget.json"
    budget.write_text(json.dumps({"phase": "build", "phases": {"build": KNOBS}, "hosts": {}}))
    monkeypatch.setenv("NOCTUS_HW_BUDGET_PATH", str(budget))
    monkeypatch.setenv("NOCTUS_HW_SLOT_DIR", str(tmp_path / "slots"))
    monkeypatch.setenv("NOCTUS_HW_LOG", str(tmp_path / "log.ndjson"))
    monkeypatch.setenv("NOCTUS_HW_QUEUE_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("NOCTUS_HW_SUSPEND", str(tmp_path / "no-suspend-flag"))
    monkeypatch.delenv("NOCTUS_HW_PHASE", raising=False)
    monkeypatch.delenv("NOCTUS_HW_SLOT_HELD", raising=False)
    return tmp_path


# ── A: queue for the slot ────────────────────────────────────────────────────
class TestQueueingForTheSlot:
    def test_waits_for_the_holder_and_reports_progress(self, hw_env):
        holder = hw._try_slot(1, "other-job")
        lines: list[str] = []
        sleeps = {"n": 0}

        def release_on_second_sleep(_s):
            sleeps["n"] += 1
            if sleeps["n"] == 2:
                holder[0].close()   # the other session finishes

        with hw.heavy_slot("me", wait_s=1000, probe_fn=lambda s: GOOD, sleep=release_on_second_sleep,
                           progress=lines.append, progress_every_s=0) as adm:
            assert adm.admitted and adm.verdict == "admitted"
        assert lines and "other-job" in lines[0] and "me" in lines[0]

    def test_deadline_expiry_names_the_holder_and_the_wait(self, hw_env):
        holder = hw._try_slot(1, "other-job")
        try:
            with hw.heavy_slot("me", wait_s=0, probe_fn=lambda s: GOOD) as adm:
                assert not adm.admitted and adm.verdict == "waiting_for_slot"
                assert "other-job" in adm.blocked_by[0] and adm.waited_s >= 0
        finally:
            holder[0].close()

    def test_budget_is_the_deadline_minus_a_run_reserve_never_under_half(self):
        assert rs.slot_wait_budget_s(3600.0) == 3600.0 - rs.SCOPED_RUN_RESERVE_S
        assert rs.slot_wait_budget_s(1000.0) == 500.0

    def test_unmeasured_names_the_wait_and_the_holder(self):
        adm = type("Adm", (), {"verdict": "waiting_for_slot", "waited_s": 1234.6,
                               "blocked_by": ["no free slot: deliverable:other(pid 5)"]})()
        d = rs.slot_refusal_detail(adm)
        assert d.startswith("UNMEASURED") and "1234s" in d and "deliverable:other(pid 5)" in d

    def test_the_default_filing_slot_queues_through_hw_admission_with_progress(self, hw_env):
        holder = hw._try_slot(1, "other-session")
        assert holder is not None
        lines: list[str] = []
        try:
            with rs._hw_slot("deliverable:x", wait_s=0.3, progress=lines.append) as adm:
                assert not adm.admitted and "other-session" in adm.blocked_by[0]
        finally:
            holder[0].close()
        assert lines and "other-session" in lines[0]


# ── B: exit code ─────────────────────────────────────────────────────────────
class _Clock:
    t = 1_800_000_000.0

    def __call__(self):
        return self.t


class TestRequestExitCode:
    def test_filed_is_zero(self):
        assert rs.cli_exit_code({"ok": True, "status": "queued_for_steward"}) == 0

    def test_a_refused_request_is_its_own_code(self, tmp_path):
        s = rs.StewardStore(tmp_path, clock=_Clock(), resolve_head=lambda b: "a" * 40, default_ttl_s=7200,
                            scoped_check=lambda b, h: {"ok": False, "detail": "UNMEASURED: x"},
                            progress=lambda m: None)
        r = s.request(PEER, "alpha")
        assert r["status"] == "needs_resync" and rs.cli_exit_code(r) == rs.EXIT_NEEDS_RESYNC == 3

    def test_a_deliverable_needs_resync_verdict_is_not_success(self):
        assert rs.cli_exit_code({"ok": True, "status": "needs_resync"}) == 3

    def test_any_other_failure_is_one(self):
        assert rs.cli_exit_code({"ok": False, "error": "boom"}) == 1

    def test_the_cli_exits_with_it(self, tmp_path):
        env = {**os.environ, "NOCTUS_STEWARD_DIR": str(tmp_path)}
        p = subprocess.run([sys.executable, str(REPO / "mcp/noctusai/cli.py"), "--release-steward", "request"],
                           capture_output=True, text=True, env=env, cwd=str(REPO), timeout=120)
        assert p.returncode == 1 and "needs slug" in p.stdout


# ── C: pointer closed at landing, healed at push, specialist roles ───────────
def _sh(cwd, *a):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


class FakePointerOps:
    def __init__(self, latest):
        self._latest, self.updates = dict(latest), []

    def latest(self, branch):
        return self._latest.get(branch)

    def update(self, **kw):
        self.updates.append(kw)
        return {"ok": True, "row": {"commit": kw.get("commit")}, "push": {"ok": True}}


def _landed_repo(tmp_path, *, remove_worktree: bool):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", str(bare)], check=True)
    primary = tmp_path / "primary"
    subprocess.run(["git", "clone", "-q", str(bare), str(primary)], check=True, capture_output=True)
    _sh(primary, "checkout", "-q", "-b", "dev")
    (primary / "base.txt").write_text("base\n")
    _sh(primary, "add", "."); _sh(primary, "commit", "-qm", "base"); _sh(primary, "push", "-q", "origin", "dev")
    wt = primary / ".claude" / "worktrees" / "x"
    _sh(primary, "worktree", "add", "-q", "-b", "feat/x", str(wt), "origin/dev")
    (wt / "a.txt").write_text("a\n"); _sh(wt, "add", "."); _sh(wt, "commit", "-qm", "add a")
    _sh(wt, "push", "-q", "origin", "feat/x:dev")   # the queue landed it (same shas)
    if remove_worktree:
        _sh(primary, "worktree", "remove", "--force", str(wt))
    return primary


def _landed(primary, ops):
    def run(cmd, cwd=None):
        r = subprocess.run(cmd, cwd=cwd or str(primary), capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr
    return T.task_branch(action="landed", slug="x", confirm=True, primary_root=str(primary), run=run,
                         keep_worktree=True, pointer_ops=ops, post_integrate=lambda *a: {"status": "skipped"},
                         queue_status_reader=lambda sha: {"state": "landed", "description": "landed"})


class TestLandingClosesThePointer:
    def test_worktree_already_gone_ships_the_pointer_at_landing_and_publishes(self, tmp_path):
        primary = _landed_repo(tmp_path, remove_worktree=True)
        ops = FakePointerOps({"feat/x": {"status": "on_going", "commit": "a"}})
        res = _landed(primary, ops)
        assert res["status"] == "integrated", res
        (u,) = ops.updates
        assert u["status"] == "shipped" and u["push_dev"] is True

    def test_worktree_still_present_stays_live_but_is_published(self, tmp_path):
        primary = _landed_repo(tmp_path, remove_worktree=False)
        ops = FakePointerOps({"feat/x": {"status": "on_going", "commit": "a"}})
        _landed(primary, ops)
        (u,) = ops.updates
        assert u["status"] == "integrated-worktree-live" and u["push_dev"] is True


def _runner(*, trailers=""):
    def run(args):
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return (0, args[-1], "") if args[-1] == "origin/dev" else (1, "", "")
        if args[:2] == ["git", "log"] and "--format=%(trailers:key=Noc-Branch,valueonly)" in args:
            return 0, trailers, ""
        if args[:3] == ["git", "worktree", "list"]:
            return 0, "", ""
        return 1, "", ""
    return run


def _ledger(tmp_path):
    p = tmp_path / "project-history"
    p.mkdir()
    (p / "branch-tree.ndjson").write_text(json.dumps(
        {"branch": "feat/mine", "status": "integrated-worktree-live", "commit": "a", "session": "S1"}) + "\n")
    return tmp_path


class TestPrePushHealsInsteadOfBlocking:
    def test_a_provably_landed_pointer_is_healed_not_reported(self, tmp_path):
        calls, healed = [], []
        issues = check_stale_branch_pointers(
            session="S1", repo_root=_ledger(tmp_path), run=_runner(trailers="feat/mine\n"),
            heal=lambda b, note: calls.append(b) or {"ok": True}, healed_out=healed)
        assert issues == [] and healed == ["feat/mine"] == calls

    def test_a_failed_heal_still_reports_the_pointer(self, tmp_path):
        issues = check_stale_branch_pointers(
            session="S1", repo_root=_ledger(tmp_path), run=_runner(trailers="feat/mine\n"),
            heal=lambda b, note: {"ok": False, "error": "ledger offline"})
        assert [i["severity"] for i in issues] == ["high"]

    def test_an_unlanded_pointer_is_never_healed(self, tmp_path):
        called = []
        check_stale_branch_pointers(session="S1", repo_root=_ledger(tmp_path), run=_runner(trailers=""),
                                    heal=lambda b, n: called.append(b) or {"ok": True})
        assert called == []


@pytest.mark.parametrize("given,want", [
    ("tooling-engineer", "engineer"), ("backend-engineer", "engineer"), ("architect", "engineer"),
    ("tech-lead", "orchestrator"), ("steward", "steward"), ("engineer", "engineer"),
])
def test_specialist_roles_map_to_the_pointer_role(given, want):
    assert bp.canonical_role(given) == want


def test_an_unknown_role_is_still_refused_by_append():
    assert bp.canonical_role("wizard") == "wizard"
    res = bp.append(branch="feat/x", base="origin/dev", commit="a", role="wizard", agent="a", parent="dev",
                    paths=[], status="on_going", brief="b", push_dev=False)
    assert res["ok"] is False and "role must be one of" in res["error"]
