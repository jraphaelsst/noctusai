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


def _land_with_drift(primary, wt, *, same_content: bool):
    """The 2026-11-09 shapes: the entry carries a kb-counts [auto] commit the
    queue re-renders differently, and a batch-mate edits the line right next
    to the entry's change, so neither cherry nor a trial merge matches."""
    derived = sorted(T._KB_COUNTS_DERIVED)[0]
    (wt / "shared.txt").write_text("top\nmid\nbottom\n")
    os.makedirs((wt / derived).parent, exist_ok=True)
    (wt / derived).write_text("count: 1\n")
    _sh(wt, "add", "."); _sh(wt, "commit", "--amend", "-qm", "add a + shared")
    (wt / derived).write_text("count: 2\n")
    _sh(wt, "add", "."); _sh(wt, "commit", "-qm", "chore(kb-counts): regenerate derived counts at integrate [auto]")
    other = primary.parent / "other"
    subprocess.run(["git", "clone", "-q", str(primary.parent / "remote.git"), str(other)],
                   check=True, capture_output=True)
    _sh(other, "checkout", "-q", "dev")
    (other / "shared.txt").write_text("top\n")
    _sh(other, "add", "."); _sh(other, "commit", "-qm", "peer touches shared")
    (other / "a.txt").write_text("a\n" if same_content else "a-but-different\n")
    (other / "shared.txt").write_text("top\nmid\nbottom\n")
    os.makedirs((other / derived).parent, exist_ok=True)
    (other / derived).write_text("count: 7\n")
    _sh(other, "add", "."); _sh(other, "commit", "-qm", "entry as landed by the queue")
    _sh(other, "push", "-q", "origin", "dev")


def test_kb_counts_rerendered_and_context_shift_is_equivalent(tmp_path):
    primary, wt = _setup(tmp_path)
    _land_with_drift(primary, wt, same_content=True)
    res = _call(primary)
    assert res["status"] == "integrated", res
    assert res["content_equivalent"] is True


def test_post_image_mismatch_outside_derived_docs_is_still_refused(tmp_path):
    primary, wt = _setup(tmp_path)
    _land_with_drift(primary, wt, same_content=False)
    res = _call(primary)
    assert res["status"] == "error" and res["missing_commits"], res
    assert wt.exists()


def test_cleanup_still_refuses_unmerged_branch(tmp_path):
    primary, wt = _setup(tmp_path)
    res = T.task_branch(action="cleanup", slug="x", confirm=True, primary_root=str(primary),
                        run=_runner(primary))
    assert res["status"] == "blocked"


def _stale_landed(tmp_path, *, twin: bool):
    """Proof 4 shape: the queue replayed the entry onto a dev whose nearby lines
    had moved (patch-id context differs), and dev later edited the SAME line
    again, so `cherry` and a trial merge both miss it. `twin=False` lands a
    recommit with the same subject but a different author date instead."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", str(bare)], check=True)
    primary = tmp_path / "primary"
    subprocess.run(["git", "clone", "-q", str(bare), str(primary)], check=True, capture_output=True)
    _sh(primary, "checkout", "-q", "-b", "dev")
    (primary / "shared.txt").write_text("1\n2\n3\n4\n5\n6\n7\n")
    _sh(primary, "add", "."); _sh(primary, "commit", "-qm", "base")
    _sh(primary, "push", "-q", "origin", "dev")
    wt = primary / ".claude" / "worktrees" / "x"
    _sh(primary, "worktree", "add", "-q", "-b", "feat/x", str(wt), "origin/dev")
    (wt / "shared.txt").write_text("1\n2\n3\n4\n5b\n6\n7\n")
    _sh(wt, "add", ".")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "feat: five becomes 5b"],
                   cwd=wt, check=True, env={**os.environ, "GIT_AUTHOR_DATE": "@1762000000 +0000"})
    other = primary.parent / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True, capture_output=True)
    _sh(other, "checkout", "-q", "dev")
    (other / "shared.txt").write_text("1\n2\n3x\n4\n5\n6\n7\n")
    _sh(other, "add", "."); _sh(other, "commit", "-qm", "peer moves the context")
    if twin:
        _sh(other, "fetch", "-q", str(primary), "feat/x")
        _sh(other, "cherry-pick", "FETCH_HEAD")
    else:
        (other / "shared.txt").write_text("1\n2\n3x\n4\n5b\n6\n7\n")
        _sh(other, "add", "."); _sh(other, "commit", "-qm", "feat: five becomes 5b")
    (other / "shared.txt").write_text("1\n2\n3x\n4\n5c\n6\n7\n")
    _sh(other, "add", "."); _sh(other, "commit", "-qm", "later dev edit of the same line")
    _sh(other, "push", "-q", "origin", "dev")
    return primary, wt


def test_cleanup_accepts_a_long_landed_branch_by_its_rebased_twin(tmp_path):
    primary, wt = _stale_landed(tmp_path, twin=True)
    _sh(primary, "fetch", "-q", "origin")
    assert _sh(primary, "cherry", "origin/dev", "feat/x").startswith("+")  # proof 1 misses it
    res = T.task_branch(action="cleanup", slug="x", confirm=True, primary_root=str(primary),
                        run=_runner(primary))
    assert res["status"] == "cleaned", res
    assert not wt.exists()


def test_cleanup_refuses_a_same_subject_commit_that_is_not_a_twin(tmp_path):
    primary, wt = _stale_landed(tmp_path, twin=False)
    res = T.task_branch(action="cleanup", slug="x", confirm=True, primary_root=str(primary),
                        run=_runner(primary))
    assert res["status"] == "blocked", res
    assert wt.exists()
