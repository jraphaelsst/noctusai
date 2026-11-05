"""task_branch `enqueue` / `landed` — the local half of the merge queue.

`enqueue` = everything integrate does locally minus the merged-tip gates, pushed
to `mq/<slug>--<sha7>` (never dev). `landed` reads the queue's commit-status
verdict and runs the post-landing tail only once the queue says LANDED.
"""
from __future__ import annotations

from tests.test_task_branch import FakeGit, _anc_pairs
from tools.noctus.dev import task_branch as T


def _fake(**kw):
    return FakeGit(refs={"origin/dev": "d0", "feat/x": "b0" * 20}, anc=_anc_pairs([]),
                   logs={"d0..b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0": "c1 x", f"{'b0' * 20}..d0": ""},
                   head_sha="b0" * 20, **kw)


def test_enqueue_pushes_to_a_queue_ref_never_dev_and_skips_merged_tip_gates():
    fake = _fake()
    called = []
    res = T.task_branch(action="enqueue", slug="x", confirm=True, run=fake,
                        merged_tip_check=lambda p, d: called.append(p) or {"status": "green", "gates": []})
    assert res["status"] == "queued", res
    assert res["queue_ref"] == "mq/x--b0b0b0b"
    assert fake.pushes() == [["git", "push", "origin", "HEAD:refs/heads/mq/x--b0b0b0b"]]
    assert called == []  # CI is the verdict, not this machine


def test_enqueue_dry_run_plans_without_pushing():
    fake = _fake()
    res = T.task_branch(action="enqueue", slug="x", confirm=False, run=fake)
    assert res["status"] == "planned" and fake.pushes() == []


def test_enqueue_hook_rejection_is_blocked():
    fake = _fake(push_rcs=[1])
    res = T.task_branch(action="enqueue", slug="x", confirm=True, run=fake)
    assert res["status"] == "blocked" and res["exit_code"] == 1


def test_push_guard_allows_queue_refs_but_still_refuses_main_prod():
    T._assert_push_targets_dev(("push", "origin", "HEAD:refs/heads/mq/x--abc1234"), "dev")
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


def test_landed_confirm_replays_onto_dev_then_runs_the_tail():
    fake = _fake()
    res = _landed(fake, "landed", keep_worktree=True)
    assert res["status"] == "integrated" and res["exit_code"] == 0
    assert [c for c, _ in fake.calls if c[:2] == ["git", "rebase"]]  # patches dropped onto dev
    assert "primary_ff" in res and "pointer" in res
    assert fake.pushes() == []  # landing already happened on CI


def test_landed_skips_the_replay_when_already_merged():
    fake = FakeGit(refs={"origin/dev": "d1", "feat/x": "b0"}, anc=_anc_pairs([("b0", "d1")]),
                   logs={}, head_sha="b0")
    res = _landed(fake, "landed", keep_worktree=True)
    assert res["status"] == "integrated"
    assert not [c for c, _ in fake.calls if c[:2] == ["git", "rebase"]]


class _MergeCarryingFake:
    """Wraps the FakeGit: `rev-list --merges` reports one merge commit."""

    def __init__(self, inner, merges: str):
        self.inner, self.merges = inner, merges
        self.calls = inner.calls

    def __call__(self, cmd, cwd=None):
        if cmd[:3] == ["git", "rev-list", "--merges"]:
            self.inner.calls.append((cmd, cwd))
            return 0, self.merges, ""
        return self.inner(cmd, cwd=cwd)

    def pushes(self):
        return self.inner.pushes()


def test_enqueue_keeps_merge_resolutions_of_a_merge_carrying_branch():
    # 2026-11-05 (feat/julia-golive): a branch that merged a feature line with
    # hand-resolved conflicts was flattened by a plain rebase and re-hit those
    # conflicts. Any merge-carrying branch now syncs dev in and rebases with
    # --rebase-merges, like a train.
    fake = _MergeCarryingFake(_fake(), "m" * 40 + "\n")
    T.task_branch(action="enqueue", slug="x", confirm=True, run=fake)
    rebases = [c for c, _ in fake.calls if c[:2] == ["git", "rebase"]]
    assert rebases and all("--rebase-merges" in c for c in rebases)
    assert [c for c, _ in fake.calls if c[:2] == ["git", "merge"]]  # dev synced in first


def test_enqueue_of_a_linear_branch_still_plain_rebases():
    fake = _MergeCarryingFake(_fake(), "")
    T.task_branch(action="enqueue", slug="x", confirm=True, run=fake)
    rebases = [c for c, _ in fake.calls if c[:2] == ["git", "rebase"]]
    assert rebases and not any("--rebase-merges" in c for c in rebases)
