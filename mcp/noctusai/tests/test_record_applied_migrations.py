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
