"""record_applied_migrations: the record is written + committed in an isolated worktree, never the primary."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.record_applied_migrations import record_applied_migrations  # noqa: E402


def _g(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    _g(primary, "init", "-q", "-b", "dev")
    _g(primary, "config", "user.email", "t@t")
    _g(primary, "config", "user.name", "t")
    _g(primary, "config", "core.hooksPath", "/dev/null")
    (primary / "products" / "orbity" / "backend").mkdir(parents=True)
    (primary / "products" / "orbity" / "backend" / "x.py").write_text("1\n")
    _g(primary, "add", "-A")
    _g(primary, "commit", "-q", "-m", "base")
    return primary


class _FakeTaskBranch:
    def __init__(self, primary, integrate_status="integrated"):
        self.primary, self.calls, self.integrate_status = primary, [], integrate_status

    def __call__(self, **kw):
        self.calls.append(kw["action"])
        if kw["action"] == "start":
            wt = self.primary.parent / "wt"
            _g(self.primary, "worktree", "add", "-q", "-b", "feat/" + kw["slug"], str(wt))
            return {"status": "started", "worktree": str(wt)}
        return {"status": self.integrate_status}


def test_record_is_committed_in_isolated_worktree_and_primary_stays_clean(tmp_path):
    primary = _repo(tmp_path)
    tb = _FakeTaskBranch(primary)
    r = record_applied_migrations("orbity", {"001_a.sql": "ab"}, task_branch_fn=tb, slug_suffix="t")
    assert r["status"] == "recorded", r
    assert tb.calls == ["start", "integrate"]
    assert _g(primary, "status", "--porcelain") == ""
    assert not (primary / "products/orbity/backend/migrations-applied.json").exists()
    wt = tmp_path / "wt"
    assert json.loads((wt / "products/orbity/backend/migrations-applied.json").read_text())["applied"] == {"001_a.sql": "ab"}
    assert "migrations-applied.json" in _g(wt, "show", "--stat", "HEAD")


def test_integrate_failure_is_reported_not_raised(tmp_path):
    primary = _repo(tmp_path)
    r = record_applied_migrations("orbity", {"001_a.sql": "ab"},
                                  task_branch_fn=_FakeTaskBranch(primary, "conflict"), slug_suffix="t")
    assert r["status"] == "error" and "conflict" in r["error"] and r["files"] == {"001_a.sql": "ab"}


def test_nothing_to_record_does_not_branch(tmp_path):
    tb = _FakeTaskBranch(tmp_path)
    assert record_applied_migrations("orbity", {}, task_branch_fn=tb)["status"] == "nothing_to_record"
    assert tb.calls == []
