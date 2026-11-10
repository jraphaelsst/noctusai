"""task_branch `landed` + the push guard — the local half of the merge queue.

`enqueue` is a PURE PUSH of the exact sha to `mq/<slug>--<sha7>` (never dev) after a
read-only delivery-contract check; its behaviour is proven on REAL git in
`test_guardian_pure_push_enqueue.py`. (The FakeGit enqueue tests that lived here asserted
the old behaviour - `rebase`/`merge`/a kb-counts commit inside the requester's worktree,
`HEAD:` refspecs - and are superseded by that file.) `landed` reads the queue's
commit-status verdict and runs the post-landing tail only once the queue says LANDED.
"""
from __future__ import annotations

from tests.test_task_branch import FakeGit, _anc_pairs
from tools.noctus.dev import task_branch as T


def _fake(**kw):
    return FakeGit(refs={"origin/dev": "d0", "feat/x": "b0" * 20}, anc=_anc_pairs([]),
                   logs={"d0..b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0": "c1 x", f"{'b0' * 20}..d0": ""},
                   head_sha="b0" * 20, **kw)


def test_push_guard_allows_queue_refs_but_still_refuses_main_prod():
    T._assert_push_targets_dev(("push", "origin", "abc1234def:refs/heads/mq/x--abc1234"), "dev")
    for bad in ("main", "prod", "release/x"):
        try:
            T._assert_push_targets_dev(("push", "origin", f"HEAD:refs/heads/{bad}"), "dev")
        except ValueError:
            continue
        raise AssertionError(f"push to {bad} was not refused")


def _landed(fake, state, confirm=True, **kw):
    return T.task_branch(action="landed", slug="x", confirm=confirm, run=fake,
                         queue_status_reader=lambda sha: {"state": state, "description": f"{state} desc"},
                         **kw)


def test_landed_reports_queued_and_ejected_without_side_effects():
    for state, status, code in (("queued", "queued", 0), ("pending", "pending", 0), ("ejected", "ejected", 1)):
        fake = _fake()
        res = _landed(fake, state)
        assert res["status"] == status and res["exit_code"] == code
        assert fake.pushes() == []
        assert not [c for c, _ in fake.calls if "rebase" in c]


def test_landed_dry_run_only_reports():
    fake = _fake()
    res = _landed(fake, "landed", confirm=False)
    assert res["status"] == "landed" and "confirm=True" in res["message"]
    assert not [c for c, _ in fake.calls if "rebase" in c]


def test_landed_confirm_decides_by_content_then_runs_the_tail():
    fake = _fake()
    fake.cherry_equiv = True  # every patch is on dev (queue rebased the entry)
    res = _landed(fake, "landed", keep_worktree=True)
    assert res["status"] == "integrated" and res["exit_code"] == 0
    assert not [c for c, _ in fake.calls if c[:2] == ["git", "rebase"]]  # worktree never touched
    assert "primary_ff" in res and "pointer" in res
    assert fake.pushes() == []  # landing already happened on CI


def test_landed_skips_the_replay_when_already_merged():
    fake = FakeGit(refs={"origin/dev": "d1", "feat/x": "b0"}, anc=_anc_pairs([("b0", "d1")]),
                   logs={}, head_sha="b0")
    res = _landed(fake, "landed", keep_worktree=True)
    assert res["status"] == "integrated"
    assert not [c for c, _ in fake.calls if c[:2] == ["git", "rebase"]]
