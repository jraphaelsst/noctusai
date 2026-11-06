"""task_branch `landed` — the merge queue REBASED the entry before landing it.

Real git against a local bare remote: the branch's shas are not ancestors of
dev, but their patches are. `landed` must decide "merged" by CONTENT (cherry /
empty trial-merge), tear down worktree+branch, and refuse (worktree untouched)
when the content genuinely is not on dev.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.noctus.dev import task_branch as T


def _sh(cwd, *a):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a],
                       cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


def _runner(root):
    def run(cmd, cwd=None):
        r = subprocess.run(cmd, cwd=cwd or str(root), capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr
    return run


def _setup(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", str(bare)], check=True)
    primary = tmp_path / "primary"
    subprocess.run(["git", "clone", "-q", str(bare), str(primary)], check=True, capture_output=True)
    _sh(primary, "checkout", "-q", "-b", "dev")
    (primary / "base.txt").write_text("base\n")
    _sh(primary, "add", "."); _sh(primary, "commit", "-qm", "base")
    _sh(primary, "push", "-q", "origin", "dev")
    wt = primary / ".claude" / "worktrees" / "x"
    _sh(primary, "worktree", "add", "-q", "-b", "feat/x", str(wt), "origin/dev")
    (wt / "a.txt").write_text("a\n"); _sh(wt, "add", "."); _sh(wt, "commit", "-qm", "add a")
    return primary, wt


def _land(primary, wt, rebased: bool):
    """Simulate the CI steward: replay the branch onto a newer dev (new shas)."""
    other = primary.parent / "other"
    subprocess.run(["git", "clone", "-q", str(primary.parent / "remote.git"), str(other)],
                   check=True, capture_output=True)
    _sh(other, "checkout", "-q", "dev")
    (other / "peer.txt").write_text("peer\n"); _sh(other, "add", "."); _sh(other, "commit", "-qm", "peer")
    if rebased:
        _sh(other, "fetch", "-q", str(primary), "feat/x")
        _sh(other, "cherry-pick", "FETCH_HEAD")
    _sh(other, "push", "-q", "origin", "dev")


def _call(primary):
    return T.task_branch(
        action="landed", slug="x", confirm=True, primary_root=str(primary),
        run=_runner(primary), keep_worktree=False, post_integrate=lambda *a: {"status": "skipped"},
        queue_status_reader=lambda sha: {"state": "landed", "description": "landed"},
    )


def test_rebased_equivalent_entry_is_integrated_and_cleaned(tmp_path):
    primary, wt = _setup(tmp_path)
    _land(primary, wt, rebased=True)
    res = _call(primary)
    assert res["status"] == "integrated", res
    assert res["content_equivalent"] is True
    assert res["auto_cleanup"]["status"] == "cleaned", res["auto_cleanup"]
    assert not wt.exists()
    assert _sh(primary, "branch", "--list", "feat/x") == ""


def test_genuinely_diverged_branch_is_refused_and_untouched(tmp_path):
    primary, wt = _setup(tmp_path)
    _land(primary, wt, rebased=False)
    before = _sh(wt, "rev-parse", "HEAD")
    res = _call(primary)
    assert res["status"] == "error" and res["exit_code"] == 1
    assert res["missing_commits"] and "NOT on" in res["error"]
    assert wt.exists() and _sh(wt, "rev-parse", "HEAD") == before
    assert _sh(wt, "status", "--porcelain") == ""
    assert not os.path.exists(wt / ".git" / "rebase-merge")
    assert _sh(primary, "branch", "--list", "feat/x") != ""


def test_cleanup_still_refuses_unmerged_branch(tmp_path):
    primary, wt = _setup(tmp_path)
    res = T.task_branch(action="cleanup", slug="x", confirm=True, primary_root=str(primary),
                        run=_runner(primary))
    assert res["status"] == "blocked"
