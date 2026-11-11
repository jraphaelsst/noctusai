"""Regression: relative worktree from task_branch must resolve against the primary root, not cwd."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.record_applied_migrations import record_applied_migrations  # noqa: E402


def _fake_tb(primary: Path, calls: list):
    def tb(action, slug, **kw):
        calls.append(action)
        if action == "start":
            (primary / ".claude" / "worktrees" / slug).mkdir(parents=True, exist_ok=True)
            return {"status": "started", "worktree": f".claude/worktrees/{slug}"}
        return {"status": "integrated"}
    return tb


def test_relative_worktree_resolved_against_primary_not_cwd(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    be = primary / ".claude/worktrees/applied-record-x-1/products/x/backend"
    be.mkdir(parents=True)
    (be / "migrations-applied.json").write_text("{\"applied\": {}}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    calls: list = []
    tb = _fake_tb(primary, calls)
    tb_wrapped = lambda **kw: tb(**kw)  # noqa: E731
    res = record_applied_migrations(
        "x", {"001_a.sql": "ab" * 32}, task_branch_fn=tb_wrapped,
        git_fn=lambda wt, *a: (0, "abc", ""), primary_root=str(primary), slug_suffix="1")
    assert res["status"] == "recorded", res
    assert str(primary) in res["path"]
    assert "001_a.sql" in json.loads(Path(res["path"]).read_text())["applied"]


def test_failure_cleans_up_branch(tmp_path):
    primary = tmp_path / "primary"
    calls: list = []
    tb = _fake_tb(primary, calls)
    res = record_applied_migrations(
        "x", {"001_a.sql": "ab" * 32}, task_branch_fn=lambda **kw: tb(**kw),
        git_fn=lambda wt, *a: (1, "", "boom"), primary_root=str(primary), slug_suffix="2")
    assert res["status"] == "error"
    assert "cleanup" in calls


# ── integrate conflict is re-derived on fresh dev (b5 finding 2026-11-11) ─────
def _conflicting_tb(primary: Path, calls: list, conflicts: int):
    state = {"left": conflicts}

    def tb(action, slug, **kw):
        calls.append(action)
        if action == "start":
            be = primary / ".claude" / "worktrees" / slug / "products" / "x" / "backend"
            be.mkdir(parents=True, exist_ok=True)
            (be / "migrations-applied.json").write_text('{"applied": {}}')
            return {"status": "started", "worktree": f".claude/worktrees/{slug}"}
        if action == "integrate" and state["left"] > 0:
            state["left"] -= 1
            return {"status": "conflict", "error": "rebase conflict"}
        return {"status": "integrated"}
    return tb


def test_an_integrate_conflict_is_re_derived_on_fresh_dev(tmp_path):
    primary = tmp_path / "primary"
    calls: list = []
    git_calls: list = []

    def git(wt, *a):
        git_calls.append(a[0])
        return 0, "abc", ""
    res = record_applied_migrations(
        "x", {"073_c.sql": "ab" * 32}, task_branch_fn=_conflicting_tb(primary, calls, 1),
        git_fn=git, primary_root=str(primary), slug_suffix="3")
    assert res["status"] == "recorded", res
    assert res["attempts"] == 2
    assert calls.count("integrate") == 2
    # the retry rebuilt on fresh dev, then re-wrote and re-committed the rows
    assert git_calls.index("reset") < len(git_calls) - 1
    assert git_calls.count("commit") == 2
    assert "073_c.sql" in json.loads(Path(res["path"]).read_text())["applied"]


def test_a_persistent_conflict_is_reported_after_the_bounded_attempts(tmp_path):
    primary = tmp_path / "primary"
    calls: list = []
    res = record_applied_migrations(
        "x", {"073_c.sql": "ab" * 32}, task_branch_fn=_conflicting_tb(primary, calls, 99),
        git_fn=lambda wt, *a: (0, "abc", ""), primary_root=str(primary), slug_suffix="4")
    assert res["status"] == "error"
    assert calls.count("integrate") == 3
    assert "after 3 attempt(s)" in res["error"] and "kept for manual integrate" in res["error"]
