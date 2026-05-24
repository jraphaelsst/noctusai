"""Colocated tests for noctus.dev.task_branch.

Zero real git — `run` is injected (a FakeGit that scripts rev-parse / merge-base
/ log / worktree list|add|remove|prune / rebase / push / branch -d, and
simulates the FF push + the concurrent-push race + a rebase conflict). Covers
status / start / integrate (planned / up_to_date / integrated / retry-on-race /
conflict) / cleanup (planned / cleaned / blocked-unmerged), and the load-bearing
safety invariants:
  • the safe-git allowlist guard rejects an off-list subcommand;
  • the DEV-ONLY push boundary refuses a push whose dst is main/prod;
  • across a full start→integrate→cleanup the tool emits no banned token.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import task_branch as T  # noqa: E402


class FakeGit:
    """Scripts git IO. `refs` maps ref→sha. A push (when its scripted rc is 0)
    advances the dst ref to `head_sha` (the worktree HEAD), simulating the FF.
    `rebase_rcs` / `push_rcs` are consumed left-to-right (default → 0). `anc` is
    an ancestor predicate over shas. Records every (cmd, cwd)."""

    def __init__(self, refs, anc, logs=None, porcelain="", head_sha=None,
                 rebase_rcs=None, push_rcs=None, conflicts=None):
        self.refs = dict(refs)
        self.anc = anc
        self.logs = logs or {}
        self.porcelain = porcelain
        self.head_sha = head_sha
        self.rebase_rcs = list(rebase_rcs or [])
        self.push_rcs = list(push_rcs or [])
        self.conflicts = conflicts or []
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, cmd, cwd=None):
        self.calls.append((cmd, cwd))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "fetch":
            return (0, "", "")
        if sub == "rev-parse":
            sha = self.refs.get(cmd[2])
            return (0, sha + "\n", "") if sha else (1, "", "bad ref")
        if sub == "merge-base":  # merge-base --is-ancestor a b
            return (0 if self.anc(cmd[3], cmd[4]) else 1, "", "")
        if sub == "log":         # log --oneline a..b
            return (0, self.logs.get(cmd[3], ""), "")
        if sub == "diff":        # diff --name-only [--diff-filter=U] a..b
            if "--diff-filter=U" in cmd:
                return (0, "\n".join(self.conflicts), "")
            return (0, "", "")
        if sub == "worktree":
            if cmd[2] == "list":
                return (0, self.porcelain, "")
            return (0, "", "")  # add / remove / prune
        if sub == "rebase":
            if "--abort" in cmd:
                return (0, "", "")
            rc = self.rebase_rcs.pop(0) if self.rebase_rcs else 0
            return (rc, "", "conflict" if rc else "")
        if sub == "push":
            rc = self.push_rcs.pop(0) if self.push_rcs else 0
            if rc == 0:
                dst = cmd[3].split(":refs/heads/")[1]
                self.refs["origin/" + dst] = self.head_sha or self.refs.get("origin/" + dst)
            return (rc, "", "non-fast-forward" if rc else "")
        if sub == "branch":      # branch -d <name>
            return (0, "", "")
        return (0, "", "")

    def subcmds(self):
        return [(c[1] if len(c) > 1 else "", c) for c, _cwd in self.calls]

    def pushes(self):
        return [c for c, _cwd in self.calls if len(c) > 1 and c[1] == "push"]

    def ran(self, *needles):
        flat = " ".join(" ".join(c) for c, _cwd in self.calls)
        return all(n in flat for n in needles)


def _anc_pairs(pairs):
    s = set(pairs)
    return lambda a, b: a == b or (a, b) in s


_PORCELAIN = (
    "worktree /repo\nHEAD m0\nbranch refs/heads/dev\n\n"
    "worktree /repo/.claude/worktrees/foo\nHEAD f0\nbranch refs/heads/feat/foo\n\n"
    "worktree /repo/.claude/worktrees/agent-xyz\nHEAD a0\nbranch refs/heads/worktree-agent-xyz\n"
)


# ── status ──
def test_status_lists_self_branch_worktrees_read_only():
    fake = FakeGit(
        refs={"origin/dev": "d0"},
        anc=_anc_pairs([]),
        logs={"d0..f0": "c1 x\nc2 y", "f0..d0": "z1 q"},
        porcelain=_PORCELAIN,
    )
    res = T.task_branch(action="status", run=fake)
    assert res["status"] == "status" and res["exit_code"] == 0
    # only the feat/* worktree under .claude/worktrees — NOT dev, NOT agent-* worktree
    assert len(res["active"]) == 1
    only = res["active"][0]
    assert only["slug"] == "foo" and only["branch"] == "feat/foo"
    assert only["ahead"] == 2 and only["behind"] == 1
    assert fake.pushes() == []  # never writes


# ── start ──
def test_start_dry_run_plans_without_creating():
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-x", confirm=False, run=fake)
    assert res["status"] == "planned" and res["exit_code"] == 0
    assert res["base_sha"] == "d0"
    assert not any(c[2] == "add" for c, _ in fake.calls if c[1] == "worktree" and len(c) > 2)


def test_start_confirm_forks_off_origin_dev():
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-x", confirm=True, run=fake)
    assert res["status"] == "started" and res["exit_code"] == 0
    assert fake.ran("worktree add .claude/worktrees/feat-x -b feat/feat-x origin/dev")


def test_start_requires_slug():
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", confirm=True, run=fake)
    assert res["status"] == "error" and "requires slug" in res["error"]


# ── integrate ──
def test_integrate_dry_run_plans_rebase_and_push():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x\nc2 y", "b0..d0": "e1 z"},
    )
    res = T.task_branch(action="integrate", slug="x", confirm=False, run=fake)
    assert res["status"] == "planned" and res["exit_code"] == 0
    assert res["ahead"] == 2 and res["behind"] == 1
    assert fake.pushes() == []


def test_integrate_up_to_date():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "d0"},
        anc=_anc_pairs([("d0", "d0")]),
        logs={"d0..d0": ""},
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "up_to_date"
    assert fake.pushes() == []


def test_integrate_confirm_pushes_to_dev_and_verifies():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "integrated" and res["exit_code"] == 0
    assert res["attempts"] == 1 and res["verified"] is True
    pushes = fake.pushes()
    assert len(pushes) == 1
    assert pushes[0] == ["git", "push", "origin", "HEAD:refs/heads/dev"]


def test_integrate_retries_on_concurrent_push_race():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        push_rcs=[1, 0],  # first push rejected (peer beat us), second FFs
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "integrated" and res["attempts"] == 2
    assert len(fake.pushes()) == 2


def test_integrate_conflict_aborts_and_surfaces():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        rebase_rcs=[1],                       # rebase conflicts
        conflicts=["seed/lib/backend/x.py"],
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "conflict" and res["exit_code"] == 1
    assert res["conflicted_files"] == ["seed/lib/backend/x.py"]
    assert fake.pushes() == []               # never pushes a conflicted state
    assert fake.ran("rebase --abort")        # worktree restored clean


# ── cleanup ──
def test_cleanup_dry_run_plans():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),       # branch merged into dev
    )
    res = T.task_branch(action="cleanup", slug="x", confirm=False, run=fake)
    assert res["status"] == "planned" and res["branch_merged"] is True


def test_cleanup_confirm_removes_worktree_and_deletes_branch():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake)
    assert res["status"] == "cleaned" and res["exit_code"] == 0
    assert fake.ran("worktree remove .claude/worktrees/x")
    assert fake.ran("worktree prune")
    assert fake.ran("branch -d feat/x")


def test_cleanup_blocked_when_branch_unmerged():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),                   # b0 NOT ancestor of d0 → unmerged
    )
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake)
    assert res["status"] == "blocked" and res["exit_code"] == 1
    assert "integrate first" in res["reason"]
    assert not fake.ran("worktree remove")


# ── safety invariants ──
def test_allowlist_guard_rejects_off_list_subcommand():
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "reset", "--hard")
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "stash")  # not on the allowlist


def test_banned_token_rejected():
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "push", "origin", "HEAD:refs/heads/dev", "--force")


def test_dev_only_push_boundary_refuses_main_and_prod():
    for bad in ("main", "prod"):
        with pytest.raises(ValueError):
            T._assert_push_targets_dev(("push", "origin", f"HEAD:refs/heads/{bad}"), "dev")
    # dev is allowed
    T._assert_push_targets_dev(("push", "origin", "HEAD:refs/heads/dev"), "dev")
    # and through _git
    with pytest.raises(ValueError):
        T._git(lambda *a, **k: (0, "", ""), "push", "origin", "HEAD:refs/heads/main")


def test_unknown_action_is_an_error_not_a_raise():
    res = T.task_branch(action="frobnicate", run=FakeGit(refs={}, anc=_anc_pairs([])))
    assert res["status"] == "error" and res["exit_code"] == 1


def test_full_lifecycle_emits_no_banned_token_and_only_dev_pushes():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
    )
    T.task_branch(action="start", slug="x", confirm=True, run=fake)
    T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    T.task_branch(action="cleanup", slug="x", confirm=True, run=fake)
    for cmd, _cwd in fake.calls:
        for tok in cmd:
            assert tok not in T._BANNED_TOKENS, f"banned token {tok!r} in {cmd}"
        if len(cmd) > 1 and cmd[1] == "push":
            dst = cmd[3].split(":refs/heads/")[1]
            assert dst == "dev", f"push to non-dev ref {dst!r}: {cmd}"
