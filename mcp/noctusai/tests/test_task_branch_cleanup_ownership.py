"""`landed` / `integrate` auto-cleanup and `cleanup` never tear down a worktree that is not the caller's.

2026-11-10: the guardian ran `task_branch action=landed slug=agents confirm=True` and the post-landing
tail removed ANOTHER session's long-lived integration worktree and deleted its local ref while that
session still worked there (a write into a worktree the caller does not own; auto-improvement 98e00cfe6).
Real temp git repos; the only injections are the documented seams (`run=`, `queue_status_reader=`,
`pointer_ops=`, `session_state=`, `caller_session=`).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tests.test_guardian_pure_push_enqueue import World, sh, sh_rc  # noqa: E402,F401
from tools.noctus.dev import primary_write_guard as PWG  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402

LANDED = lambda sha: {"state": "landed", "description": "merged by the queue"}  # noqa: E731


class FakePointers:
    """The documented `pointer_ops` seam: a latest-per-branch map; transitions are accepted."""

    def __init__(self, **by_branch):
        self.by_branch = by_branch

    def latest(self, branch):
        return self.by_branch.get(branch)

    def update(self, **kw):
        return {"ok": True, "row": {"commit": kw.get("commit")}}

    def append(self, **kw):
        return {"ok": True}


@pytest.fixture()
def landed_world(tmp_path):
    """feat/x was delivered and the queue landed it: its tip is now origin/dev."""
    w = World(tmp_path)
    wt = w.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    w.set_counts(wt)
    w.commit(wt, "feat: b")
    sh(wt, "git", "push", "-q", "origin", "feat/x:refs/heads/feat/x")
    sh(wt, "git", "push", "-q", "origin", "feat/x:refs/heads/dev")  # the queue's landing
    w.wt = wt
    return w


def landed(w, **kw):
    kw.setdefault("caller_session", "sess-guardian")
    kw.setdefault("keep_worktree", False)
    return T.task_branch(action="landed", slug="x", confirm=True, run=w.runner(), primary_root=str(w.repo),
                         queue_status_reader=LANDED, **kw)


def untouched(w):
    assert w.wt.is_dir() and (w.wt / "src" / "b.txt").is_file()
    assert sh(w.repo, "git", "rev-parse", "--verify", "refs/heads/feat/x")
    assert str(w.wt) in sh(w.repo, "git", "worktree", "list", "--porcelain")


def test_landed_with_a_live_foreign_claim_leaves_the_worktree_and_ref_alone(landed_world):
    w = landed_world
    assert PWG.write_claim(str(w.repo), "sess-owner", str(w.wt))["status"] == "claimed"
    res = landed(w, session_state=lambda sid: "live")
    assert res["status"] == "integrated" and res["exit_code"] == 0  # the landed verdict never fails over it
    for key in ("auto_cleanup", "cleanup"):
        assert res[key]["status"] == "skipped_owned" and res[key]["cwd_removed"] is False
        assert res[key]["owner"]["session_id"] == "sess-owner" and res[key]["owner"]["source"] == "worktree_claim"
        assert "claimed by session" in res[key]["reason"]
    untouched(w)


def test_an_owner_whose_liveness_is_unknown_is_treated_as_live(landed_world):
    w = landed_world
    PWG.write_claim(str(w.repo), "sess-owner", str(w.wt))
    res = landed(w)  # no session_state seam: nothing says the owner is gone
    assert res["auto_cleanup"]["status"] == "skipped_owned" and res["auto_cleanup"]["owner"]["state"] == "unknown"
    untouched(w)


def test_a_dead_foreign_claim_does_not_protect_the_worktree(landed_world):
    w = landed_world
    PWG.write_claim(str(w.repo), "sess-gone", str(w.wt))
    res = landed(w, session_state=lambda sid: "dead")
    assert res["auto_cleanup"]["status"] == "cleaned", res["auto_cleanup"]
    assert not w.wt.exists()


def test_landed_for_a_steward_branch_leaves_it_untouched_even_for_its_own_session(landed_world):
    w = landed_world
    ptr = FakePointers(**{"feat/x": {"branch": "feat/x", "role": "steward", "session": "sess-steward", "status": "on_going"}})
    for caller in ("sess-guardian", "sess-steward"):
        res = landed(w, pointer_ops=ptr, caller_session=caller)
        assert res["status"] == "integrated"
        assert res["auto_cleanup"]["status"] == "skipped_owned"
        assert res["auto_cleanup"]["owner"] == {"session_id": "sess-steward", "source": "steward_branch", "branch": "feat/x"}
        untouched(w)


def test_landed_for_an_unclaimed_engineer_slice_is_cleaned_as_before(landed_world):
    w = landed_world
    ptr = FakePointers(**{"feat/x": {"branch": "feat/x", "role": "engineer", "session": "sess-eng", "status": "on_going"}})
    res = landed(w, pointer_ops=ptr)
    assert res["auto_cleanup"]["status"] == "cleaned", res["auto_cleanup"]
    assert res["auto_cleanup"]["worktree_removed"] and res["auto_cleanup"]["branch_deleted"]
    assert not w.wt.exists()
    assert sh_rc(w.repo, "git", "rev-parse", "--verify", "-q", "refs/heads/feat/x").returncode != 0


def test_a_claim_held_by_the_caller_itself_does_not_block_its_own_cleanup(landed_world):
    w = landed_world
    PWG.write_claim(str(w.repo), "sess-me", str(w.wt))
    res = landed(w, caller_session="sess-me")
    assert res["auto_cleanup"]["status"] == "cleaned", res["auto_cleanup"]


def test_a_direct_cleanup_honours_the_same_ownership(landed_world):
    w = landed_world
    PWG.write_claim(str(w.repo), "sess-owner", str(w.wt))
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=w.runner(), primary_root=str(w.repo),
                        caller_session="sess-guardian", session_state=lambda s: "live")
    assert res["status"] == "skipped_owned" and res["exit_code"] == 0
    untouched(w)


def test_a_steward_may_clean_its_own_branch_directly_but_not_via_the_auto_path(landed_world):
    w = landed_world
    ptr = FakePointers(**{"feat/x": {"branch": "feat/x", "role": "steward", "session": "sess-steward", "status": "on_going"}})
    other = T.task_branch(action="cleanup", slug="x", confirm=True, run=w.runner(), primary_root=str(w.repo),
                          pointer_ops=ptr, caller_session="sess-other")
    assert other["status"] == "skipped_owned" and "only the owning session" in other["reason"]
    own = T.task_branch(action="cleanup", slug="x", confirm=True, run=w.runner(), primary_root=str(w.repo),
                        pointer_ops=ptr, caller_session="sess-steward")
    assert own["status"] == "cleaned", own
