"""`task_branch landed` is the BRANCH STEWARD's post-landing tail (guardian spec: the requester owns its worktree).

The release-steward guard used to refuse `landed slug=<x> confirm=True` from the requester ("steward-only ... that is
<guardian>") while the guardian told the requester the tail was theirs. A non-lease session may now run `landed` when ALL
hold: the branch's work is already on origin/dev, its worktree is clean, and the caller is that branch's requester /
claim holder (/ pointer session). Everything else stays steward-only. Real git; the store takes a repo_cwd seam.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_guardian_pure_push_enqueue import World, sh  # noqa: E402
from tools.noctus.dev import primary_write_guard as PWG  # noqa: E402
from tools.noctus.dev import release_steward as RS  # noqa: E402

TOOL = "mcp__noctusai__noctus_dev_task_branch"
GUARDIAN, REQUESTER, THIRD = "guardian-sess", "requester-sess", "third-sess"


def _store(w: World, tmp_path: Path):
    store = RS.StewardStore(
        root=tmp_path / "steward", repo_cwd=w.repo,
        resolve_head=lambda b: sh(w.repo, "git", "rev-parse", f"refs/heads/{b}"))
    assert store.claim(GUARDIAN, name="guardian", reason="t", claude_pid=os.getpid()).get("ok")
    return store


def _world(tmp_path: Path, *, landed: bool):
    w = World(tmp_path)
    wt = w.worktree()
    (wt / "src" / "b.txt").write_text("b\n")
    w.set_counts(wt)
    head = w.commit(wt, "feat: b")
    sh(wt, "git", "push", "-q", "origin", "feat/x:refs/heads/feat/x")
    if landed:
        sh(wt, "git", "push", "-q", "origin", "feat/x:refs/heads/dev")  # the queue's landing
    sh(w.repo, "git", "fetch", "-q", "origin")
    w.wt, w.head = wt, head
    return w


def _decide(store, session, args=None, tool=TOOL):
    args = args or {"action": "landed", "slug": "x", "confirm": True}
    return RS.decide({"tool_name": tool, "tool_input": args, "session_id": session}, store=store, env={})


@pytest.fixture()
def landed(tmp_path):
    w = _world(tmp_path, landed=True)
    store = _store(w, tmp_path)
    store.request(REQUESTER, "x", branch="feat/x", head_sha=w.head)
    return w, store


def test_the_requester_runs_landed_on_a_landed_clean_branch(landed):
    _w, store = landed
    assert _decide(store, REQUESTER) is None
    assert any(e.get("event") == "landed_by_branch_steward" for e in
               [__import__("json").loads(x) for x in store.audit_path.read_text().splitlines()])


def test_the_guardian_may_still_run_it(landed):
    assert _decide(landed[1], GUARDIAN) is None


def test_a_third_session_is_refused_and_told_why(landed):
    _w, store = landed
    v = _decide(store, THIRD)
    assert v and v["status"] == "refused_not_steward"
    assert "BRANCH STEWARD" in v["reason"] and "not the branch's requester" in v["reason"]


def test_the_requester_is_refused_on_an_unlanded_head(tmp_path):
    w = _world(tmp_path, landed=False)
    store = _store(w, tmp_path)
    store.request(REQUESTER, "x", branch="feat/x", head_sha=w.head)
    v = _decide(store, REQUESTER)
    assert v and v["status"] == "refused_not_steward" and "not on origin/dev" in v["reason"]


def test_the_requester_is_refused_when_the_worktree_is_dirty(landed):
    w, store = landed
    (w.wt / "src" / "a.txt").write_text("uncommitted work\n")
    v = _decide(store, REQUESTER)
    assert v and "dirty" in v["reason"]


def test_the_claim_holder_of_the_worktree_may_run_it_too(landed):
    w, store = landed
    assert _decide(store, "claimer-sess") is not None
    assert PWG.write_claim(str(w.repo), "claimer-sess", str(w.wt))["status"] == "claimed"
    assert _decide(store, "claimer-sess") is None


@pytest.mark.parametrize("args", [
    {"action": "enqueue", "slug": "x", "confirm": True},
    {"action": "integrate", "slug": "x", "confirm": True},
])
def test_everything_else_stays_steward_only_for_the_requester(landed, args):
    assert _decide(landed[1], REQUESTER, args)["status"] == "refused_not_steward"


def test_other_steward_class_tools_stay_steward_only(landed):
    v = _decide(landed[1], REQUESTER, {"stage": "bless", "confirm": True}, tool="mcp__noctusai__noctus_dev_release")
    assert v and v["status"] == "refused_not_steward"


def test_the_cli_form_is_recognised_too(landed):
    _w, store = landed
    cmd = "python mcp/noctusai/cli.py --task-branch=landed --task-branch-slug=x --task-branch-confirm"
    ok = RS.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": REQUESTER}, store=store, env={})
    assert ok is None
    third = RS.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": THIRD}, store=store, env={})
    assert third and third["status"] == "refused_not_steward"


def test_a_dry_run_landed_was_never_gated(landed):
    assert _decide(landed[1], THIRD, {"action": "landed", "slug": "x", "confirm": False}) is None
