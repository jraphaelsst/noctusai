"""Colocated tests for noctus.dev.task_branch.

Zero real git — `run` is injected (a FakeGit that scripts rev-parse / merge-base
/ log / worktree list|add|remove|prune / rebase / push / branch -d, and
simulates the FF push + the concurrent-push race + a rebase conflict). Covers
status / start / integrate (planned / up_to_date / integrated / retry-on-race /
conflict) / cleanup (planned / cleaned / blocked-unmerged + the salvage-before-
delete recovery-pointer leg recorded BEFORE the destructive remove), and the
load-bearing safety invariants:
  • the safe-git allowlist guard rejects an off-list subcommand;
  • the DEV-ONLY push boundary refuses a push whose dst is main/prod;
  • across a full start→integrate→cleanup the tool emits no banned token.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import task_branch as T  # noqa: E402


class FakeGit:
    """Scripts git IO. `refs` maps ref→sha. A push (when its scripted rc is 0)
    advances the dst ref to `head_sha` (the worktree HEAD), simulating the FF.
    `rebase_rcs` / `push_rcs` are consumed left-to-right (default → 0). `anc` is
    an ancestor predicate over shas. Records every (cmd, cwd).

    `status_output` overrides the `git status --porcelain` response (default: "").
    `stash_rc` controls the return code for `git stash push` (default: 0).
    `diff_output` overrides the plain (non `--diff-filter=U`) `git diff
    --name-only a...b` response — used by the migration-collision-gate tests
    to script "this branch introduces these migration files" (default: "",
    i.e. no files — the gate is a no-op unless a test opts in).
    """

    def __init__(self, refs, anc, logs=None, porcelain="", head_sha=None,
                 rebase_rcs=None, push_rcs=None, conflicts=None,
                 status_output="", stash_rc=0, diff_output=""):
        self.refs = dict(refs)
        self.anc = anc
        self.logs = logs or {}
        self.porcelain = porcelain
        self.head_sha = head_sha
        self.rebase_rcs = list(rebase_rcs or [])
        self.push_rcs = list(push_rcs or [])
        self.conflicts = conflicts or []
        self.status_output = status_output
        self.stash_rc = stash_rc
        self.diff_output = diff_output
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, cmd, cwd=None):
        self.calls.append((cmd, cwd))
        # Handle both `git <sub> ...` and `git -C <path> <sub> ...` forms.
        if len(cmd) > 1 and cmd[1] == "-C":
            sub = cmd[3] if len(cmd) > 3 else ""
        else:
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
            return (0, self.diff_output, "")
        if sub == "status":
            return (0, self.status_output, "")
        if sub == "worktree":
            if cmd[2] == "list" or (len(cmd) > 3 and cmd[3] == "list"):
                return (0, self.porcelain, "")
            return (0, "", "")  # add / remove / prune
        if sub == "stash":
            if "pop" in cmd:
                return (0, "", "")
            return (self.stash_rc, "", "stash-error" if self.stash_rc else "")
        if sub == "rebase":
            if "--abort" in cmd:
                return (0, "", "")
            rc = self.rebase_rcs.pop(0) if self.rebase_rcs else 0
            return (rc, "", "conflict" if rc else "")
        if sub == "push":
            rc = self.push_rcs.pop(0) if self.push_rcs else 0
            if rc == 0:
                # Handle both `git push origin HEAD:refs/heads/dev` and
                # `git -C <wt> push origin HEAD:dev` refspec forms.
                dst_tok = next((t for t in cmd if ":" in t and "refs/heads/" in t), None)
                if dst_tok:
                    dst = dst_tok.split(":refs/heads/")[1]
                    self.refs["origin/" + dst] = self.head_sha or self.refs.get("origin/" + dst)
                else:
                    # HEAD:dev form (used by cleanup's commit-push leg)
                    dst_tok2 = next((t for t in cmd if t.startswith("HEAD:")), None)
                    if dst_tok2:
                        dst = dst_tok2.split(":", 1)[1]
                        self.refs["origin/" + dst] = self.head_sha or self.refs.get("origin/" + dst)
            return (rc, "", "non-fast-forward" if rc else "")
        if sub == "add" or sub == "commit":
            return (0, "", "")
        if sub == "branch":      # branch -d <name>
            return (0, "", "")
        return (0, "", "")

    def subcmds(self):
        return [(c[1] if len(c) > 1 else "", c) for c, _cwd in self.calls]

    def pushes(self):
        """Return all push commands (both `git push ...` and `git -C <wt> push ...` forms)."""
        result = []
        for c, _cwd in self.calls:
            if len(c) > 1 and c[1] == "push":
                result.append(c)
            elif len(c) > 3 and c[1] == "-C" and c[3] == "push":
                result.append(c)
        return result

    def ran(self, *needles):
        flat = " ".join(" ".join(c) for c, _cwd in self.calls)
        return all(n in flat for n in needles)


def _anc_pairs(pairs):
    s = set(pairs)
    return lambda a, b: a == b or (a, b) in s


def _capture_recorder():
    """A fake salvage_recorder: captures (root, removed) and returns a ledger
    path WITHOUT real IO — so cleanup tests exercise the recovery-pointer leg
    deterministically (no settings import, no file write)."""
    captured: list[tuple] = []

    def rec(root, removed):
        captured.append((root, removed))
        return Path(root) / "project-history/worktree-salvage.ndjson"

    rec.captured = captured
    return rec


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
    # the salvage ritual is SURFACED in the plan (learn-before-delete) — dry-run
    # records nothing yet.
    assert set(res["cleanup_ritual"]) == {
        "1_extract_learnings", "2_record_recovery_pointer",
        "3_mole_sweep_before_delete", "4_remove"}
    assert "KB/memory" in res["learnings_checkpoint"]


def test_cleanup_confirm_removes_worktree_and_deletes_branch():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned" and res["exit_code"] == 0
    assert fake.ran("worktree remove .claude/worktrees/x")
    assert fake.ran("worktree prune")
    assert fake.ran("branch -d feat/x")
    # MECHANICAL recovery-pointer leg fired (branch+SHA recorded to the ledger).
    assert res["salvage_ledger"].endswith("worktree-salvage.ndjson")
    assert len(rec.captured) == 1
    _root, removed = rec.captured[0]
    assert removed[0]["branch"] == "feat/x" and removed[0]["sha"] == "b0"


def test_cleanup_records_recovery_pointer_before_removing_the_worktree():
    """Leg 2 is recorded BEFORE the destructive `worktree remove` — so a
    remove failure can't lose the recovery pointer."""
    order: list[str] = []

    def rec(root, removed):
        order.append("salvage")
        return Path(root) / "project-history/worktree-salvage.ndjson"

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    _orig = fake.__call__

    def spy(cmd, cwd=None):
        if len(cmd) > 1 and cmd[1] == "worktree" and cmd[2] == "remove":
            order.append("remove")
        return _orig(cmd, cwd)

    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=spy,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert order == ["salvage", "remove"]   # recovery pointer recorded first


def test_cleanup_resolves_actual_branch_for_reused_worktree_dir():
    """A reused/renamed worktree whose dir (`sw-waha-youtube`) ≠ feat/<slug>
    (`feat/salvage-before-delete`): cleanup must resolve the ACTUAL branch from the
    worktree list (keyed by dir) so the recovery-pointer leg records the real
    branch — not silently no-op on a nonexistent feat/<slug>, leaving the real
    branch dangling. The 2026-05-25 dogfood regression."""
    porcelain = (
        "worktree /repo\nHEAD m0\nbranch refs/heads/dev\n\n"
        "worktree /repo/.claude/worktrees/sw-waha-youtube\n"
        "HEAD b0\nbranch refs/heads/feat/salvage-before-delete\n"
    )
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/salvage-before-delete": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
        porcelain=porcelain,
    )
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="sw-waha-youtube", confirm=True,
                        run=fake, primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    # the ACTUAL branch (not feat/sw-waha-youtube) was resolved, recorded + deleted
    assert res["branch"] == "feat/salvage-before-delete"
    assert fake.ran("branch -d feat/salvage-before-delete")
    _root, removed = rec.captured[0]
    assert removed[0]["branch"] == "feat/salvage-before-delete"
    assert removed[0]["sha"] == "b0"
    # the worktree dir (the stable key) is still removed by its path
    assert fake.ran("worktree remove .claude/worktrees/sw-waha-youtube")


def test_cleanup_commits_dirty_salvage_ledger_before_remove():
    """The N=3 cross-tree-hazard fix (2026-05-28): when the salvage record leaves
    the ledger file dirty in the worktree, cleanup commits + pushes the entry to
    dev BEFORE the worktree remove. Without this leg, remove refused (dirty tree)
    and a retry was a no-op via idempotency yet STILL saw the same uncommitted
    file ⇒ infinite loop. This test asserts the stage → commit → push sequence
    happens between salvage record and worktree remove."""
    order: list[str] = []
    refs = {"origin/dev": "d0", "feat/x": "b0"}

    def runner(cmd, cwd=None):
        order.append(" ".join(cmd))
        if cmd[:2] == ["git", "-C"]:
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "status":          # dirty signal on the ledger file
                return (0, " M project-history/worktree-salvage.ndjson\n", "")
            if sub == "add" or sub == "commit" or sub == "fetch":
                return (0, "", "")
            if sub == "push":
                return (0, "", "")       # FF push succeeds
        # FakeGit handles the cleanup MCP tool's _git() wrapper calls.
        return fake(cmd, cwd)

    fake = FakeGit(refs=refs, anc=_anc_pairs([("b0", "d0")]))

    def rec(root, removed):
        order.append("salvage")
        return Path(root) / "project-history/worktree-salvage.ndjson"

    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert res["salvage_pushed"] is True
    flat = " | ".join(order)
    # The commit + push happen AFTER the salvage record and BEFORE the worktree
    # remove — the precise sequencing that breaks the N=3 loop.
    assert "salvage" in order
    assert any("status --porcelain -- project-history/worktree-salvage.ndjson"
               in o for o in order)
    assert any("add project-history/worktree-salvage.ndjson" in o for o in order)
    assert any("commit -m" in o for o in order)
    assert any("push origin HEAD:dev" in o for o in order)
    # Sequence: salvage → status/add/commit/push → remove
    salvage_idx = order.index("salvage")
    push_idx = next(i for i, o in enumerate(order) if "push origin HEAD:dev" in o)
    remove_idx = next(i for i, o in enumerate(order) if "worktree remove" in o)
    assert salvage_idx < push_idx < remove_idx


def test_cleanup_skips_commit_push_when_ledger_clean():
    """The idempotent case: second cleanup call sees ledger already canonical
    (append_ledger skipped the duplicate), so status reports clean and the
    commit+push leg is a no-op. Remove proceeds directly."""
    order: list[str] = []

    def runner(cmd, cwd=None):
        order.append(" ".join(cmd))
        if cmd[:2] == ["git", "-C"]:
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "status":          # clean — no dirty signal
                return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert res["salvage_pushed"] is False  # nothing to push — ledger was clean
    assert not any("commit -m" in o for o in order)
    assert not any("push origin HEAD:dev" in o for o in order)


def test_cleanup_salvage_push_lands_on_dev_when_origin_dev_advanced():
    """origin/dev advanced past the branch base (the rebase-integrated normal
    case): the salvage push must STILL land on dev. The primary-checkout commit is
    rebased onto the freshly-fetched origin/dev then FF-pushed (the 2026-06-30
    lost-row fix — the old worktree-HEAD:dev push was non-FF → rejected → the row
    was orphaned on the force-deleted branch). Asserts a rebase was issued from the
    PRIMARY checkout + the final push targeted :dev."""
    order: list[str] = []
    # b0 was merged into an OLD dev; origin/dev is now d1 (advanced past the base).
    refs = {"origin/dev": "d1", "feat/x": "b0"}

    def runner(cmd, cwd=None):
        order.append(" ".join(cmd))
        if cmd[:2] == ["git", "-C"]:
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "status":      # primary ledger dirty (this cleanup appended)
                return (0, " M project-history/worktree-salvage.ndjson\n", "")
            if sub == "rev-list":    # one commit ahead of origin/dev
                return (0, "s1\n", "")
            if sub == "diff-tree":   # it touches ONLY the ledger → guard passes
                return (0, "project-history/worktree-salvage.ndjson\n", "")
            if sub in ("add", "commit", "fetch", "rebase", "push"):
                return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(refs=refs, anc=_anc_pairs([("b0", "d1")]))  # b0 ancestor of d1
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert res["salvage_pushed"] is True
    # a rebase onto origin/dev was issued from the PRIMARY checkout (the FF path)
    assert any("git -C /repo rebase origin/dev" in o for o in order), order
    # the final push targeted :dev from the PRIMARY checkout
    assert any("git -C /repo push origin HEAD:dev" in o for o in order), order
    # ledger root was the PRIMARY root (canonical with the bulk sweeps)
    ledger_root, _ = rec.captured[0]
    from pathlib import Path
    assert Path(str(ledger_root)) == Path("/repo")


def test_cleanup_salvage_makes_no_worktree_side_commit():
    """The ledger write goes to the PRIMARY checkout, so NO add/commit/push/rebase
    is ever issued against the worktree branch — `git worktree remove` needs no
    worktree-side commit and nothing lands on the to-be-deleted branch."""
    order: list[str] = []

    def runner(cmd, cwd=None):
        order.append(" ".join(cmd))
        if cmd[:2] == ["git", "-C"]:
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "status":
                return (0, " M project-history/worktree-salvage.ndjson\n", "")
            if sub == "rev-list":
                return (0, "s1\n", "")
            if sub == "diff-tree":
                return (0, "project-history/worktree-salvage.ndjson\n", "")
            if sub in ("add", "commit", "fetch", "rebase", "push"):
                return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    # NO `git -C <worktree>` command was issued at all — every write targeted /repo.
    assert not any(o.startswith("git -C .claude/worktrees/x") for o in order), order
    # every -C write (add/commit/push/rebase) targeted the PRIMARY root
    for o in order:
        if o.startswith("git -C") and any(
                k in o for k in (" add ", " commit ", " push ", " rebase ")):
            assert o.split()[2] == "/repo", f"worktree-side write leaked: {o}"
    assert res["worktree_removed"] is True and res["branch_deleted"] is True


def test_cleanup_salvage_push_failure_is_best_effort():
    """A salvage push failure must NOT block teardown: cleanup still removes the
    worktree + deletes the branch + returns (no raise) with salvage_pushed=False
    surfaced. The row is on local dev (ships with the next dev push)."""
    order: list[str] = []

    def runner(cmd, cwd=None):
        order.append(" ".join(cmd))
        if cmd[:2] == ["git", "-C"]:
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "status":
                return (0, " M project-history/worktree-salvage.ndjson\n", "")
            if sub == "rev-list":
                return (0, "s1\n", "")
            if sub == "diff-tree":
                return (0, "project-history/worktree-salvage.ndjson\n", "")
            if sub in ("add", "commit", "fetch", "rebase"):
                return (0, "", "")
            if sub == "push":
                return (1, "", "non-fast-forward")  # push always rejected
        return fake(cmd, cwd)

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"                # teardown completed anyway
    assert res["worktree_removed"] is True and res["branch_deleted"] is True
    assert res["salvage_pushed"] is False            # surfaced, best-effort
    # the single retry path was exercised (two push attempts on the race)
    assert sum(1 for o in order if "git -C /repo push origin HEAD:dev" in o) == 2


def test_branch_for_path_keys_on_dir_not_slug():
    """Unit: _branch_for_path matches by dir path/basename, returns the real
    branch; None for a detached or absent worktree."""
    porcelain = (
        "worktree /repo/.claude/worktrees/sw-waha-youtube\n"
        "HEAD b0\nbranch refs/heads/feat/salvage-before-delete\n"
    )
    assert T._branch_for_path(porcelain, ".claude/worktrees/sw-waha-youtube") == \
        "feat/salvage-before-delete"
    assert T._branch_for_path(porcelain, ".claude/worktrees/absent") is None
    # detached HEAD (no branch line) → None
    assert T._branch_for_path("worktree /repo/.claude/worktrees/x\nHEAD b0\n",
                              ".claude/worktrees/x") is None


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
    T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                  primary_root="/repo", salvage_recorder=_capture_recorder())
    for cmd, _cwd in fake.calls:
        for tok in cmd:
            assert tok not in T._BANNED_TOKENS, f"banned token {tok!r} in {cmd}"
        if len(cmd) > 1 and cmd[1] == "push":
            dst = cmd[3].split(":refs/heads/")[1]
            assert dst == "dev", f"push to non-dev ref {dst!r}: {cmd}"


# ── env auto-wire (the §5a verification-env recipe) ──
def _seed_primary(primary, *, slugs=("alpha",), with_product_nm=True,
                  with_seed_nm=True, product_nm_entries=("react",),
                  with_dotenv=True, with_toolkit_nm=True):
    """Build a fixture PRIMARY tree under `primary` (a tmp Path): seed-frontend
    packages (+ their node_modules) and products/<slug>/frontend (+ node_modules
    seeded with `product_nm_entries` — fixture vendor packages the per-entry
    overlay should mirror in). Returns nothing — just lays out dirs for FsOps
    (real os) to read."""
    primary.mkdir(parents=True, exist_ok=True)
    if with_dotenv:
        (primary / ".env").write_text("VITE_SUPABASE_URL=https://fixture.invalid\n")
    if with_toolkit_nm:
        (primary / "mcp" / "noctusai" / "node" / "node_modules").mkdir(parents=True, exist_ok=True)
    for rel in ("seed/lib/frontend", "seed/framework/frontend"):
        (primary / rel).mkdir(parents=True, exist_ok=True)
        if with_seed_nm:
            (primary / rel / "node_modules").mkdir(exist_ok=True)
    for slug in slugs:
        fe = primary / "products" / slug / "frontend"
        fe.mkdir(parents=True, exist_ok=True)
        if with_product_nm:
            nm = fe / "node_modules"
            nm.mkdir(exist_ok=True)
            for entry in product_nm_entries:
                (nm / entry).mkdir(exist_ok=True)


def _seed_worktree_tree(wt_root):
    """A fresh worktree mirrors the tracked tree (the seed pkgs exist) but has NO
    node_modules anywhere (gitignored ⇒ absent) — exactly the state wire_env fixes."""
    for rel in ("seed/lib/frontend", "seed/framework/frontend"):
        (wt_root / rel).mkdir(parents=True, exist_ok=True)


def test_plan_env_wiring_lists_expected_symlink_targets(tmp_path):
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "alpha"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)

    wire, skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    links = {w["link"]: w for w in wire}

    # seed node_modules mirrored in WHOLE (target = PRIMARY's node_modules) —
    # nothing nests inside a seed pkg's node_modules, so this carries no
    # write-through hazard.
    for rel in ("seed/lib/frontend", "seed/framework/frontend"):
        link = str(wt_root / rel / "node_modules")
        assert link in links and links[link]["kind"] == "node_modules"
        assert links[link]["target"] == str(primary / rel / "node_modules")

    # the product frontend node_modules is NEVER a whole-dir symlink (the fixed
    # 2026-07-16 primary-contamination bug) — it stays a REAL worktree directory;
    # each primary vendor package gets its OWN per-entry symlink instead.
    pnm = wt_root / "products" / "alpha" / "frontend" / "node_modules"
    assert str(pnm) not in links, "product node_modules must never be a whole-dir symlink"
    react_link = str(pnm / "react")
    assert react_link in links and links[react_link]["kind"] == "node_modules_entry"
    assert links[react_link]["target"] == str(primary / "products/alpha/frontend/node_modules/react")

    # the repo-root .env — gitignored, so a fresh worktree never has one, and
    # without it vite's envDir yields no VITE_* and the SPA renders blank with
    # NO console error (createProductSupabase throws inside a module).
    env_link = str(wt_root / ".env")
    assert env_link in links and links[env_link]["kind"] == "dotenv"
    assert links[env_link]["target"] == str(primary / ".env")

    # the toolkit's ts-morph runtime — same gitignored-and-absent class as
    # `.env`; without it the lying-loading-state Mode-B scan degrades to a
    # WARNING that reads like a detector regression.
    tk = str(wt_root / "mcp" / "noctusai" / "node" / "node_modules")
    assert tk in links and links[tk]["kind"] == "node_modules"
    assert links[tk]["target"] == str(primary / "mcp" / "noctusai" / "node" / "node_modules")

    # the two @noctusai re-points (to the WORKTREE's own seed copies, never primary)
    lib_link = str(pnm / "@noctusai" / "lib")
    seed_link = str(pnm / "@noctusai" / "seed")
    assert links[lib_link]["kind"] == "@noctusai"
    assert links[lib_link]["target"] == str(wt_root / "seed/lib/frontend")
    assert links[seed_link]["target"] == str(wt_root / "seed/framework/frontend")
    assert skipped == []


def test_plan_env_wiring_reports_missing_toolkit_node_modules(tmp_path):
    """Absent toolkit node_modules → REPORTED, not silently omitted."""
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "zeta"
    _seed_primary(primary, slugs=("zeta",), with_toolkit_nm=False)
    _seed_worktree_tree(wt_root)

    wire, skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    assert not [w for w in wire if w["link"].endswith("mcp/noctusai/node/node_modules")]
    assert [s for s in skipped if "primary toolkit node_modules absent" in s["reason"]]


def test_plan_env_wiring_reports_missing_primary_dotenv(tmp_path):
    """No `.env` in primary → REPORTED, never silently omitted. The silent
    version of this is a blank page with an empty console."""
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "delta"
    _seed_primary(primary, slugs=("delta",), with_dotenv=False)
    _seed_worktree_tree(wt_root)

    wire, skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    assert not [w for w in wire if w["kind"] == "dotenv"]
    assert [s for s in skipped if "primary .env absent" in s["reason"]]


def test_apply_env_wiring_creates_dotenv_symlink(tmp_path):
    """End-to-end: the planned `.env` spec actually lands as a symlink whose
    content resolves to the primary file."""
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "epsilon"
    _seed_primary(primary, slugs=("epsilon",))
    _seed_worktree_tree(wt_root)

    wire, _ = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    created, failed = T._apply_env_wiring(
        [w for w in wire if w["kind"] == "dotenv"], T.FsOps()
    )
    assert failed == []
    link = wt_root / ".env"
    assert link.is_symlink()
    assert "VITE_SUPABASE_URL" in link.read_text()
    assert len(created) == 1


def test_plan_env_wiring_reports_missing_primary_node_modules(tmp_path):
    # primary seed dirs exist but their node_modules are ABSENT → reported, not crashed
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "beta"
    _seed_primary(primary, slugs=("beta",), with_seed_nm=False, with_product_nm=False,
                  with_dotenv=False, with_toolkit_nm=False)
    _seed_worktree_tree(wt_root)

    wire, skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    # nothing to mirror (no primary node_modules anywhere) → all node_modules skipped;
    # the @noctusai re-points target the WORKTREE seed (which exists) so they still plan
    nm_skips = [s for s in skipped if "primary node_modules absent" in s["reason"]]
    assert len(nm_skips) == 3  # 2 seed pkgs + 1 product frontend
    assert all(w["kind"] == "@noctusai" for w in wire)


def test_plan_env_wiring_converts_stale_product_symlink_to_real_dir(tmp_path):
    # a product node_modules that is ALREADY a whole-dir symlink (leftover from
    # the pre-fix scheme, or a not-yet-re-wired worktree) must be converted to a
    # REAL directory before any per-entry symlink is planned under it — else the
    # per-entry writes would still land through the stale symlink (the bug).
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "gamma"
    _seed_primary(primary, slugs=("gamma",))
    _seed_worktree_tree(wt_root)
    stale = wt_root / "products/gamma/frontend/node_modules"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.symlink_to(primary / "products/gamma/frontend/node_modules")

    wire, _skipped = T._plan_env_wiring(str(primary), str(wt_root), T.FsOps())
    kinds_at_stale = [w["kind"] for w in wire if w["link"] == str(stale)]
    assert kinds_at_stale == ["ensure_real_dir"]
    # the ensure_real_dir spec is ordered BEFORE the entries it hosts
    idx_ensure = next(i for i, w in enumerate(wire) if w["link"] == str(stale))
    idx_entry = next(i for i, w in enumerate(wire) if w["link"] == str(stale / "react"))
    assert idx_ensure < idx_entry

    created, failed = T._apply_env_wiring(wire, T.FsOps())
    assert not failed
    assert stale.is_dir() and not stale.is_symlink()
    assert (stale / "react").is_symlink()
    assert os.path.realpath(stale / "react") == os.path.realpath(
        primary / "products/gamma/frontend/node_modules/react")


def test_two_worktrees_wire_env_never_contaminates_primary(tmp_path):
    """The regression test for the 2026-07-16 bug (closed 2026-07-20): TWO
    worktrees off the SAME primary both wire_env — the primary's own product
    node_modules must be untouched by either, and each worktree's @noctusai/lib
    must resolve to ITS OWN seed copy, never the peer's and never the primary's.
    (`cleanup` is out of scope here — `git worktree remove` deletes only the
    worktree's own directory tree; it never touches the primary, so it cannot
    reintroduce this class of contamination.)"""
    primary = tmp_path / "primary"
    _seed_primary(primary, slugs=("alpha",))
    primary_pnm = primary / "products/alpha/frontend/node_modules"

    wt1 = primary / ".claude/worktrees/peer-one"
    wt2 = primary / ".claude/worktrees/peer-two"
    _seed_worktree_tree(wt1)
    _seed_worktree_tree(wt2)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    for slug, wt in (("peer-one", wt1), ("peer-two", wt2)):
        res = T.task_branch(action="start", slug=slug, confirm=True,
                            wire_env=True, primary_root=str(primary), run=fake)
        assert res["status"] == "started" and not res["wired"] == []

    # the PRIMARY's own product node_modules never grew an @noctusai entry —
    # neither worktree ever wrote THROUGH a symlink into it.
    assert not (primary_pnm / "@noctusai").exists()
    assert primary_pnm.is_dir() and not primary_pnm.is_symlink()

    # each worktree's @noctusai/lib resolves to ITS OWN seed copy — never the
    # peer's, never the primary's.
    lib1 = wt1 / "products/alpha/frontend/node_modules/@noctusai/lib"
    lib2 = wt2 / "products/alpha/frontend/node_modules/@noctusai/lib"
    assert os.path.realpath(lib1) == os.path.realpath(wt1 / "seed/lib/frontend")
    assert os.path.realpath(lib2) == os.path.realpath(wt2 / "seed/lib/frontend")
    assert os.path.realpath(lib1) != os.path.realpath(lib2)


def test_start_wire_env_dry_run_reports_plan_without_creating(tmp_path):
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "feat-x"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    res = T.task_branch(action="start", slug="feat-x", confirm=False,
                        wire_env=True, primary_root=str(primary), run=fake)
    assert res["status"] == "planned" and res["wire_env"] is True
    would_links = {w["link"] for w in res["would_wire"]}
    assert str(wt_root / "seed/lib/frontend/node_modules") in would_links
    assert str(wt_root / "products/alpha/frontend/node_modules/react") in would_links
    assert str(wt_root / "products/alpha/frontend/node_modules/@noctusai/lib") in would_links
    # dry-run created NOTHING on disk
    assert not (wt_root / "seed/lib/frontend/node_modules").exists()
    assert not (wt_root / "products/alpha/frontend/node_modules").exists()


def test_start_wire_env_confirm_creates_symlinks(tmp_path):
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "feat-y"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    res = T.task_branch(action="start", slug="feat-y", confirm=True,
                        wire_env=True, primary_root=str(primary), run=fake)
    assert res["status"] == "started" and res["wire_env"] is True
    # seed node_modules: whole-dir symlink to primary (safe — nothing nests here)
    seed_nm = wt_root / "seed/lib/frontend/node_modules"
    assert seed_nm.is_symlink()
    assert os.path.realpath(seed_nm) == os.path.realpath(primary / "seed/lib/frontend/node_modules")
    # product node_modules: a REAL directory (never a symlink) — the fix —
    # containing a per-entry symlink for each primary vendor package
    product_nm = wt_root / "products/alpha/frontend/node_modules"
    assert product_nm.is_dir() and not product_nm.is_symlink()
    react_link = product_nm / "react"
    assert react_link.is_symlink()
    assert os.path.realpath(react_link) == os.path.realpath(
        primary / "products/alpha/frontend/node_modules/react")
    lib_repoint = product_nm / "@noctusai/lib"
    assert lib_repoint.is_symlink()
    # the @noctusai/lib re-point resolves to the WORKTREE seed (crux), not PRIMARY
    assert os.path.realpath(lib_repoint) == os.path.realpath(wt_root / "seed/lib/frontend")
    assert len(res["wired"]) >= 4


def test_start_wire_env_skips_real_node_modules_never_clobbers(tmp_path):
    # a REAL node_modules already present in the worktree must NOT be replaced/nested
    primary = tmp_path / "primary"
    wt_root = primary / ".claude" / "worktrees" / "feat-z"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt_root)
    real_nm = wt_root / "seed/lib/frontend/node_modules"
    real_nm.mkdir(parents=True)
    sentinel = real_nm / "KEEP"
    sentinel.write_text("real")
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))

    res = T.task_branch(action="start", slug="feat-z", confirm=True,
                        wire_env=True, primary_root=str(primary), run=fake)
    # untouched: still a real dir, sentinel intact, NOT a symlink
    assert real_nm.is_dir() and not real_nm.is_symlink()
    assert sentinel.read_text() == "real"
    reasons = " ".join(s["reason"] for s in res["skipped"])
    assert "real node_modules already present" in reasons


def test_start_without_wire_env_is_unchanged(tmp_path):
    # the default path stays exactly as before — no wire_env key, no plan
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-x", confirm=False, run=fake)
    assert res["status"] == "planned"
    assert "wire_env" not in res and "would_wire" not in res


# ── Bug A: gitignored-only dirty worktree → cleanup succeeds (no manual --force) ──

class FakeGitWithGitIgnoredDirt(FakeGit):
    """Extends FakeGit to simulate a worktree that fails `git worktree remove`
    on the first attempt (because of gitignored files), but returns a clean
    `git status --porcelain` (confirming the dirt is all gitignored), and
    succeeds on the forced remove."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._remove_attempts = 0

    def __call__(self, cmd, cwd=None):
        self.calls.append((cmd, cwd))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "status":
            # Return empty output → worktree is clean (excluding gitignored files)
            return (0, "", "")
        if sub == "worktree" and cmd[2] == "remove":
            if "--force" in cmd:
                return (0, "", "")
            self._remove_attempts += 1
            if self._remove_attempts == 1:
                # First attempt fails (gitignored files present, e.g. .claude/cache/*.sqlite)
                return (1, "", "fatal: '.claude/cache/agent.sqlite' is dirty")
            return (0, "", "")
        return super().__call__(cmd, cwd=cwd)


def test_cleanup_succeeds_when_only_gitignored_files_are_present():
    """Bug A regression: if `git worktree remove` fails but `git status --porcelain`
    returns nothing (only gitignored files), the cleanup must proceed via
    force-remove instead of returning an error. N=4 workaround eliminator."""
    fake = FakeGitWithGitIgnoredDirt(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned", f"expected cleaned, got {res!r}"
    assert res["exit_code"] == 0
    force_removes = [
        c for c, _cwd in fake.calls
        if len(c) > 2 and c[1] == "worktree" and c[2] == "remove" and "--force" in c
    ]
    assert force_removes, "expected a --force worktree remove for gitignored-only dirt"
    assert res["worktree_removed"] is True and res["branch_deleted"] is True


def test_cleanup_still_blocks_when_real_uncommitted_changes_exist():
    """Bug A inverse: real uncommitted changes must still block cleanup — only
    gitignored-only dirt gets the force-remove pass-through."""

    class FakeGitRealDirty(FakeGit):
        def __call__(self, cmd, cwd=None):
            self.calls.append((cmd, cwd))
            sub = cmd[1] if len(cmd) > 1 else ""
            if sub == "status":
                return (0, " M seed/lib/backend/real_change.py\n", "")
            if sub == "worktree" and cmd[2] == "remove":
                return (1, "", "fatal: dirty worktree")
            return super().__call__(cmd, cwd=cwd)

    fake = FakeGitRealDirty(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                        primary_root="/repo", salvage_recorder=_capture_recorder())
    assert res["status"] == "error", f"expected error for real dirt, got {res!r}"
    assert "real uncommitted changes" in res["error"]
    force_removes = [
        c for c, _cwd in fake.calls
        if len(c) > 2 and c[1] == "worktree" and c[2] == "remove" and "--force" in c
    ]
    assert not force_removes, "must NOT force-remove when real uncommitted changes exist"


def test_is_dirty_excluding_gitignored_returns_false_for_clean_worktree():
    """Unit: helper returns False when git status --porcelain emits nothing."""
    runner = lambda cmd, cwd=None: (0, "", "")
    assert T._is_dirty_excluding_gitignored(runner, "/some/worktree") is False


def test_is_dirty_excluding_gitignored_returns_true_for_modified_files():
    """Unit: helper returns True when git status --porcelain lists tracked files."""
    runner = lambda cmd, cwd=None: (0, " M some/file.py\n", "")
    assert T._is_dirty_excluding_gitignored(runner, "/some/worktree") is True


def test_is_dirty_excluding_gitignored_returns_true_on_git_failure():
    """Unit: conservative — returns True when git status itself fails (rc != 0)."""
    runner = lambda cmd, cwd=None: (128, "", "not a git repo")
    assert T._is_dirty_excluding_gitignored(runner, "/some/worktree") is True


# ── Salvage ledger writes to the PRIMARY root (2026-06-30 lost-row fix) ──
# Earlier this leg recorded to the WORKTREE root + committed the row on the
# worktree's feature-branch HEAD, then pushed HEAD:dev. When origin/dev had
# advanced past the branch base (the normal case after later work landed), that
# push was non-FF → rejected; the salvage commit was orphaned on the rebase-
# integrated feature branch, which the operator force-deletes (branch -D) → the
# recovery row was LOST for every rebase-integrated slug. The fix: record to the
# PRIMARY ledger (canonical with the bulk mole / cleanup_stale_worktrees sweeps)
# + commit/FF-push it from the PRIMARY dev checkout, leaving the worktree clean
# and nothing on the deleted branch.

def test_cleanup_salvage_ledger_root_is_primary_not_worktree():
    """The recovery pointer lands in the PRIMARY tree's
    project-history/worktree-salvage.ndjson (canonical with the bulk sweeps —
    mole.py passes the primary `root`), NOT the worktree's — so it commits on the
    primary dev checkout, the worktree stays clean for remove, and nothing lands
    on the to-be-deleted branch."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=fake,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert len(rec.captured) == 1
    ledger_root, removed = rec.captured[0]
    from pathlib import Path
    assert Path(str(ledger_root)) == Path("/repo"), (
        f"Ledger root should be the PRIMARY root /repo (canonical with the bulk "
        f"sweeps), not the worktree. Got: {ledger_root!r}")
    # The recorded recovery pointer still references the worktree path + branch+SHA.
    assert removed[0]["path"].endswith(".claude/worktrees/x")
    assert removed[0]["branch"] == "feat/x" and removed[0]["sha"] == "b0"
    # The ledger the caller would commit IS in the primary tree.
    assert res["salvage_ledger"].startswith("/repo")


def test_cleanup_salvage_ledger_root_primary_independent_of_wt_path():
    """The ledger root tracks the PRIMARY root regardless of worktrees_dir — an
    absolute worktrees_dir (absolute wt_path) does NOT relocate the ledger to the
    worktree (the pre-2026-06-30 behavior); it stays on the primary tree."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/abs": "b0"},
        anc=_anc_pairs([("b0", "d0")]),
    )
    rec = _capture_recorder()
    res = T.task_branch(
        action="cleanup", slug="abs", confirm=True, run=fake,
        worktrees_dir="/abs/wt",  # absolute → wt_path = "/abs/wt/abs"
        primary_root="/repo", salvage_recorder=rec,
    )
    assert res["status"] == "cleaned", f"unexpected: {res!r}"
    ledger_root, removed = rec.captured[0]
    from pathlib import Path
    assert Path(str(ledger_root)) == Path("/repo"), (
        f"Expected the primary root /repo, got {ledger_root!r}")
    # The pointer still records the (absolute) worktree path it salvaged.
    assert removed[0]["path"] == "/abs/wt/abs"


# ── Bug C: integrate status=conflict + empty conflicted_files on clean FF rebase ──
# Root cause: pre-commit / cache-refresh hooks write known-benign files into the
# worktree (KNOWLEDGE-BASE/AGENT-CONTEXT.md, project-history/vector-costs.ndjson,
# etc.). `git rebase` refuses with "error: cannot rebase: You have unstaged
# changes" ⇒ rc≠0 ⇒ tool returns status=conflict + empty conflicted_files (the
# diff --diff-filter=U finds nothing because the rebase was BLOCKED, not CONFLICTED).
# Fix: auto-stash known-benign files before the rebase; pop after success.
# Observed N=5+ times this session (2026-05-28). Tests cover both legs.

def test_integrate_with_known_benign_dirty_files_succeeds():
    """The bug we hit N=5+: worktree has benign refresh artifacts as dirty files,
    but the actual rebase is a clean FF. The integrate must auto-stash them,
    rebase cleanly, and return status=integrated (not status=conflict)."""
    # Build a runner that: (1) reports benign dirty files on status, (2) reports
    # clean status after the stash push, (3) succeeds the rebase.
    stash_pushed = []

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "stash":
                if "pop" in cmd:
                    return (0, "", "")
                # stash push — remember it happened
                stash_pushed.append(True)
                return (0, "", "")
            return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        # status returns benign dirty file BEFORE stash, clean after
        status_output=" M KNOWLEDGE-BASE/AGENT-CONTEXT.md\n M project-history/vector-costs.ndjson\n",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner,
                        verbose=True)
    assert res["status"] == "integrated", (
        f"expected integrated, got {res!r} — benign artifacts should be auto-stashed")
    assert res["exit_code"] == 0
    assert stash_pushed, "stash push must be called for benign artifacts"


def test_integrate_with_real_dirty_conflict_blocks_loudly():
    """The inverse: real uncommitted changes (not in the benign list) must cause
    the rebase to fail AND surface conflicted_files loudly. We must never silently
    eat a real conflict."""
    calls = []

    def runner(cmd, cwd=None):
        calls.append(cmd)
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "stash":
                # Should NOT be called for real dirty files
                return (0, "", "")
            return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        rebase_rcs=[1],                  # rebase conflicts
        conflicts=["products/myapp/backend/real_work.py"],
        # Status shows a REAL file (not in the benign list)
        status_output=" M products/myapp/backend/real_work.py\n",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] == "conflict", f"expected conflict, got {res!r}"
    assert res["exit_code"] == 1
    assert res["conflicted_files"] == ["products/myapp/backend/real_work.py"]
    # No stash push should have occurred for real files
    stash_calls = [c for c in calls if len(c) > 3 and c[3] == "stash" and "pop" not in c]
    assert not stash_calls, "must NOT stash real dirty files"


def test_integrate_after_push_race_retries_once():
    """TOCTOU mitigation: if the push fails (concurrent peer), the next attempt
    re-fetches + re-rebases (the race loop). Benign stash is properly managed
    across retries — stash once before the loop, pop after final success."""
    stash_ops = []

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "stash":
                op = "pop" if "pop" in cmd else "push"
                stash_ops.append(op)
                return (0, "", "")
            return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        push_rcs=[1, 0],  # first push rejected (peer beat us), second FFs
        # Benign artifact present
        status_output=" M project-history/auto-improvement.ndjson\n",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] == "integrated", f"expected integrated, got {res!r}"
    assert res["attempts"] == 2
    # Stash pushed once before the loop, popped once after final success
    assert stash_ops.count("push") == 1, "should stash exactly once before the retry loop"
    assert stash_ops.count("pop") == 1, "should pop exactly once after success"


def test_cleanup_idempotent_under_concurrent_call():
    """The d2676bed fix invariant: a second cleanup call (after the first already
    appended + committed the ledger) sees a clean ledger → no duplicate commit/push.
    salvage_pushed is False on the second call."""
    call_count = [0]

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "status":
                # First call: ledger is dirty (new record appended)
                # Second call: ledger is clean (already committed)
                call_count[0] += 1
                if call_count[0] == 1:
                    return (0, " M project-history/worktree-salvage.ndjson\n", "")
                return (0, "", "")
            if inner_sub in ("add", "commit", "fetch"):
                return (0, "", "")
            if inner_sub == "push":
                return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    rec = _capture_recorder()

    # First call — ledger dirty → commit + push
    res1 = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                         primary_root="/repo", salvage_recorder=rec)
    assert res1["status"] == "cleaned"
    assert res1["salvage_pushed"] is True

    # Reset fake for second call with fresh state
    fake2 = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                    anc=_anc_pairs([("b0", "d0")]))
    rec2 = _capture_recorder()
    call_count[0] = 99  # Force "clean" status for subsequent calls

    def runner2(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "status":
                return (0, "", "")  # already committed — clean
        return fake2(cmd, cwd)

    res2 = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner2,
                         primary_root="/repo", salvage_recorder=rec2)
    assert res2["status"] == "cleaned"
    assert res2["salvage_pushed"] is False  # idempotent — nothing to push


def test_cleanup_skips_already_recorded_sha():
    """The d2676bed idempotency contract: when the salvage recorder returns a path
    but the ledger file is already clean (append_ledger skipped the duplicate),
    the commit/push leg is a no-op. `salvage_pushed` is False."""
    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "status":
                # Ledger is clean — idempotent append skipped the duplicate
                return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"},
                   anc=_anc_pairs([("b0", "d0")]))
    rec = _capture_recorder()
    res = T.task_branch(action="cleanup", slug="x", confirm=True, run=runner,
                        primary_root="/repo", salvage_recorder=rec)
    assert res["status"] == "cleaned"
    assert res["salvage_pushed"] is False
    # Recorder was still called (the attempt to append was made), but ledger was clean
    assert len(rec.captured) == 1


# ── Unit: _classify_dirty_files ──

def test_classify_dirty_files_separates_benign_from_real():
    """Unit: _classify_dirty_files correctly routes known-benign paths vs real ones."""
    status_out = (
        " M KNOWLEDGE-BASE/AGENT-CONTEXT.md\n"
        " M project-history/vector-costs.ndjson\n"
        " M project-history/auto-improvement.ndjson\n"
        " M products/myapp/backend/services.py\n"
        " M seed/lib/backend/core.py\n"
    )
    runner = lambda cmd, cwd=None: (0, status_out, "")
    benign, real = T._classify_dirty_files(runner, "/wt")
    assert "KNOWLEDGE-BASE/AGENT-CONTEXT.md" in benign
    assert "project-history/vector-costs.ndjson" in benign
    assert "project-history/auto-improvement.ndjson" in benign
    assert "products/myapp/backend/services.py" in real
    assert "seed/lib/backend/core.py" in real


def test_classify_dirty_files_cache_glob_matches():
    """Unit: .claude/cache/* pattern matches cache files."""
    status_out = " M .claude/cache/agent-context.sqlite\n M .claude/cache/noc-graph.sqlite\n"
    runner = lambda cmd, cwd=None: (0, status_out, "")
    benign, real = T._classify_dirty_files(runner, "/wt")
    assert ".claude/cache/agent-context.sqlite" in benign
    assert ".claude/cache/noc-graph.sqlite" in benign
    assert real == []


def test_classify_dirty_files_on_git_failure_is_conservative():
    """Unit: git status failure → conservative (no benign, one sentinel real entry)."""
    runner = lambda cmd, cwd=None: (128, "", "not a git repo")
    benign, real = T._classify_dirty_files(runner, "/wt")
    assert benign == []
    assert real == ["<git-status-failed>"]


# ── structural-cache settle (cross-tree shared-cache coherence, 2026-05-30) ──

def test_integrate_runs_settle_when_injected():
    """integrate success calls the injected settle once + surfaces its report."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
    )
    calls = []
    res = T.task_branch(
        action="integrate", slug="x", confirm=True, run=fake,
        settle=lambda: (calls.append(1) or {"noc_graph": {"ok": True, "status": "in-sync"}}),
    )
    assert res["status"] == "integrated"
    assert calls == [1]  # settle fired exactly once, AFTER the verified FF-push
    assert res["cache_settle"]["noc_graph"]["status"] == "in-sync"


def test_cleanup_runs_settle_when_injected():
    """cleanup success calls the injected settle once + surfaces its report."""
    fake = FakeGit(refs={"origin/dev": "d0", "feat/x": "b0"}, anc=_anc_pairs([("b0", "d0")]))
    calls = []
    res = T.task_branch(
        action="cleanup", slug="x", confirm=True, run=fake,
        primary_root="/repo", salvage_recorder=_capture_recorder(),
        settle=lambda: (calls.append(1) or {"ok": True}),
    )
    assert res["status"] == "cleaned"
    assert calls == [1] and res["cache_settle"] == {"ok": True}


def test_settle_skipped_with_injected_runner_and_no_explicit_settle():
    """Gating: an injected runner (test/custom context) must NOT trigger the real
    settle — only the default production path (run is None) does. Keeps unit tests
    from touching the real shared caches."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "integrated"
    assert "cache_settle" not in res


def test_settle_helper_is_only_stale_and_reports(monkeypatch):
    """_settle_structural_caches refreshes each cache ONLY-STALE (force=False) and
    returns an ok report."""
    import tools.noctus.dev.noc_graph_cache as ng
    import tools.noctus.dev.auto_improvement as ai
    seen: dict[str, object] = {}
    monkeypatch.setattr(ng, "refresh",
                        lambda force=False, **k: (seen.__setitem__("ng_force", force)
                                                  or {"status": "in-sync", "source_sha": "s1"}))
    monkeypatch.setattr(ai, "refresh",
                        lambda force=False, **k: (seen.__setitem__("ai_force", force)
                                                  or {"status": "in-sync", "source_sha": "s2"}))
    rep = T._settle_structural_caches()
    assert rep["noc_graph"] == {"ok": True, "status": "in-sync", "source_sha": "s1"}
    assert rep["auto_improvement"] == {"ok": True, "status": "in-sync", "source_sha": "s2"}
    assert seen["ng_force"] is False and seen["ai_force"] is False  # never force-rebuilds


def test_settle_helper_swallows_refresh_failure(monkeypatch):
    """A refresh that raises must NOT propagate — best-effort; the freshness keeper
    stays the net."""
    import tools.noctus.dev.noc_graph_cache as ng
    import tools.noctus.dev.auto_improvement as ai

    def boom(**k):
        raise RuntimeError("cache locked")

    monkeypatch.setattr(ng, "refresh", boom)
    monkeypatch.setattr(ai, "refresh", lambda force=False, **k: {"status": "in-sync"})
    rep = T._settle_structural_caches()  # must not raise
    assert rep["noc_graph"]["ok"] is False and "cache locked" in rep["noc_graph"]["error"]
    assert rep["auto_improvement"]["ok"] is True


# ── Bug A fix: worktree-salvage.ndjson is benign (list-driven extensibility) ──

def test_classify_dirty_files_worktree_salvage_ndjson_is_benign():
    """Bug A fix: project-history/worktree-salvage.ndjson is a gitattributes
    merge=union append-only ledger churned by the post-checkout/post-merge
    cache-settle hooks — it must be in the benign set so integrate is not
    blocked when the tool's own hooks dirty it."""
    status_out = " M project-history/worktree-salvage.ndjson\n"
    runner = lambda cmd, cwd=None: (0, status_out, "")
    benign, real = T._classify_dirty_files(runner, "/wt")
    assert "project-history/worktree-salvage.ndjson" in benign
    assert real == []


def test_integrate_with_only_worktree_salvage_dirty_succeeds():
    """Bug A integration: a worktree dirty ONLY with worktree-salvage.ndjson
    (churned by the tool's own post-checkout hooks) must NOT be blocked —
    the ledger is auto-stashed and integrate returns status=integrated."""
    stash_pushed = []

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "stash":
                if "pop" in cmd:
                    return (0, "", "")
                stash_pushed.append(True)
                return (0, "", "")
            return (0, "", "")
        return fake(cmd, cwd)

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        # The only dirty file is the salvage ledger — must be treated as benign.
        status_output=" M project-history/worktree-salvage.ndjson\n",
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] == "integrated", (
        f"expected integrated, got {res!r} — worktree-salvage.ndjson should be benign")
    assert res["exit_code"] == 0
    assert stash_pushed, "stash push must be called for the salvage ledger benign artifact"


def test_benign_patterns_contains_worktree_salvage():
    """Structural: the pattern constant itself includes worktree-salvage.ndjson
    so it is extensible by adding to the list, not buried in ad-hoc logic."""
    assert any(
        "worktree-salvage.ndjson" in p for p in T._BENIGN_REFRESH_PATTERNS
    ), f"worktree-salvage.ndjson missing from _BENIGN_REFRESH_PATTERNS: {T._BENIGN_REFRESH_PATTERNS}"


# ── Bug B fix: phantom conflict → dirty_blocked when rebase was refused ──

def _make_refused_rebase_runner(fake, *, git_dir_path="/wt/.git"):
    """Build a runner that simulates a rebase REFUSED before starting:
    - `git rev-parse --git-dir` returns the git dir path
    - `git rebase ...` returns rc=1 with "cannot rebase: unstaged changes" stderr
    - No rebase-merge / rebase-apply directory exists at git_dir_path
    (the caller is responsible for NOT creating those dirs in tmp_path)
    """
    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "rev-parse" and "--git-dir" in cmd:
            return (0, git_dir_path + "\n", "")
        if sub == "rebase" and "--abort" not in cmd:
            # Simulate refused: rc=1, no rebase-merge dir created
            return (1, "", "error: cannot rebase: You have unstaged changes")
        return fake(cmd, cwd)
    return runner


def test_rebase_refused_by_dirty_worktree_surfaces_dirty_blocked_not_conflict(tmp_path):
    """Bug B fix: when git rebase returns rc≠0 but the rebase was REFUSED
    (no rebase-merge directory, hook chatter re-dirtied files after stash),
    the tool must return status=dirty_blocked — NOT status=conflict — and
    conflicted_files must be empty. A status=conflict MUST imply real conflicts."""
    # Create a fake .git dir WITHOUT rebase-merge (simulates "refused" rebase).
    fake_git = tmp_path / ".git"
    fake_git.mkdir()
    # No rebase-merge subdir → rebase was refused, never started.

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        # Some dirty file re-appeared after stash (hook chatter)
        status_output=" M project-history/auto-improvement.ndjson\n",
    )
    runner = _make_refused_rebase_runner(fake, git_dir_path=str(fake_git))
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner,
                        verbose=True)
    # Must be dirty_blocked, NOT conflict.
    assert res["status"] == "dirty_blocked", (
        f"expected dirty_blocked (rebase refused, no rebase-merge dir), got {res!r}")
    assert res["exit_code"] == 1
    assert res["conflicted_files"] == [], (
        "conflicted_files must be empty when rebase was refused (not conflicted)")
    assert res.get("rebase_refused") is True
    # The message must mention dirty / refused (not merge conflicts).
    assert "REFUSED" in res["message"] or "dirty" in res["message"].lower()


def test_rebase_genuine_conflict_still_surfaces_conflict_status(tmp_path):
    """Bug B inverse: a genuine rebase conflict (rebase-merge dir exists,
    conflicted files present) must still produce status=conflict. The fix
    must not suppress real conflicts."""
    # Create a fake .git dir WITH rebase-merge → rebase is in-progress.
    fake_git = tmp_path / ".git"
    fake_git.mkdir()
    (fake_git / "rebase-merge").mkdir()  # present → rebase in-progress

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        rebase_rcs=[1],
        conflicts=["seed/lib/backend/x.py"],
        status_output="",  # clean before rebase
    )

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "rev-parse" and "--git-dir" in cmd:
            return (0, str(fake_git) + "\n", "")
        return fake(cmd, cwd)

    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] == "conflict", (
        f"expected conflict (rebase-merge dir present), got {res!r}")
    assert res["conflicted_files"] == ["seed/lib/backend/x.py"]


def test_rebase_in_progress_returns_false_when_no_rebase_dir(tmp_path):
    """Unit: _rebase_in_progress returns False when neither rebase-merge nor
    rebase-apply exists under the git dir."""
    fake_git = tmp_path / ".git"
    fake_git.mkdir()
    runner = lambda cmd, cwd=None: (0, str(fake_git) + "\n", "")
    assert T._rebase_in_progress(runner, str(tmp_path)) is False


def test_rebase_in_progress_returns_true_when_rebase_merge_exists(tmp_path):
    """Unit: _rebase_in_progress returns True when rebase-merge dir exists."""
    fake_git = tmp_path / ".git"
    fake_git.mkdir()
    (fake_git / "rebase-merge").mkdir()
    runner = lambda cmd, cwd=None: (0, str(fake_git) + "\n", "")
    assert T._rebase_in_progress(runner, str(tmp_path)) is True


def test_rebase_in_progress_returns_true_when_rebase_apply_exists(tmp_path):
    """Unit: _rebase_in_progress returns True when rebase-apply dir exists."""
    fake_git = tmp_path / ".git"
    fake_git.mkdir()
    (fake_git / "rebase-apply").mkdir()
    runner = lambda cmd, cwd=None: (0, str(fake_git) + "\n", "")
    assert T._rebase_in_progress(runner, str(tmp_path)) is True


def test_rebase_in_progress_conservative_on_rev_parse_failure(tmp_path):
    """Unit: _rebase_in_progress is conservative (True) when git rev-parse fails."""
    runner = lambda cmd, cwd=None: (128, "", "not a git repo")
    assert T._rebase_in_progress(runner, str(tmp_path)) is True


def test_hook_chatter_on_stdout_does_not_yield_conflict_when_rebase_refused(tmp_path):
    """Bug B: hook chatter on stdout/stderr (noc-graph/embedding output) must NOT
    produce status=conflict. When git rebase rc≠0 but no rebase-merge dir exists,
    the result is dirty_blocked — the hook chatter is correctly interpreted as a
    dirty-worktree refusal, not a merge conflict."""
    fake_git = tmp_path / ".git"
    fake_git.mkdir()
    # No rebase-merge → refused, not conflicted.

    # Chatter-heavy stdout that could be misread as conflict output
    chatter = (
        "Refreshing noc-graph cache...\n"
        "Embedding 42 KB chunks...\n"
        "auto-improvement: 3 new entries\n"
    )
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        status_output="",
    )

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "rev-parse" and "--git-dir" in cmd:
            return (0, str(fake_git) + "\n", "")
        if sub == "rebase" and "--abort" not in cmd:
            # Hook chatter on stdout; rc=1 due to pre-rebase dirty check
            return (1, chatter, "error: cannot rebase: You have unstaged changes")
        return fake(cmd, cwd)

    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    # Hook chatter must NOT be misread as conflict markers.
    assert res["status"] != "conflict", (
        "hook chatter on stdout/stderr must not produce status=conflict")
    assert res["conflicted_files"] == []
    # Must be dirty_blocked (the rebase was refused, not conflicted).
    assert res["status"] == "dirty_blocked"


# ── Three required regression tests per the SLICE D brief ──
# (a) worktree dirty ONLY with union-merge ledgers → NOT blocked
# (b) clean rebase emitting hook chatter on stdout/stderr → status != 'conflict'
# (c) genuinely dirty non-ledger file → STILL blocked (regression guard)

def test_worktree_dirty_only_with_all_union_merge_ledgers_not_blocked():
    """(a) Regression: a worktree dirty ONLY with all four gitattributes
    merge=union append-only ledgers (vector-costs, auto-improvement,
    worktree-salvage, branch-tree) must NOT be blocked — they are all in
    _BENIGN_REFRESH_PATTERNS, auto-stashed, and integrate returns integrated."""
    stash_pushed = []

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "stash":
                if "pop" in cmd:
                    return (0, "", "")
                stash_pushed.append(True)
                return (0, "", "")
            return (0, "", "")
        return fake(cmd, cwd)

    # All four union-merge ledger files dirty — no real task files.
    all_ledgers = (
        " M project-history/vector-costs.ndjson\n"
        " M project-history/auto-improvement.ndjson\n"
        " M project-history/worktree-salvage.ndjson\n"
        " M project-history/branch-tree.ndjson\n"
    )
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        status_output=all_ledgers,
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] == "integrated", (
        f"expected integrated — all four union-merge ledgers are benign, got {res!r}")
    assert res["exit_code"] == 0
    assert stash_pushed, "stash push must be called for the union-merge ledgers"
    # branch-tree.ndjson specifically is included in _BENIGN_REFRESH_PATTERNS
    assert any("branch-tree.ndjson" in p for p in T._BENIGN_REFRESH_PATTERNS), (
        "branch-tree.ndjson must be in _BENIGN_REFRESH_PATTERNS")


def test_clean_rebase_with_hook_chatter_on_stdout_stderr_not_conflict():
    """(b) Regression: a clean rebase that emits heavy hook chatter on stdout/stderr
    (noc-graph / embedding-refresh output) must NOT produce status='conflict'.
    The rebase succeeds (rc=0) and returns status=integrated regardless of chatter."""
    chatter_stdout = (
        "Refreshing noc-graph cache...\n"
        "CONFLICT (content): Merge conflict in foo.py\n"  # chatter that looks like a conflict
        "Embedding 128 KB chunks in auto-improvement...\n"
        "branch-tree: 7 new entries written\n"
    )
    chatter_stderr = (
        "warning: noc-graph: stale source_sha, refreshing\n"
        "warning: auto-improvement: appended 3 entries\n"
    )

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "rebase" and "--abort" not in cmd:
            # Rebase SUCCEEDS (rc=0) but dumps hook chatter on both streams.
            return (0, chatter_stdout, chatter_stderr)
        return fake(cmd, cwd)

    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        status_output="",  # worktree is clean before rebase
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] == "integrated", (
        f"hook chatter on stdout/stderr (even conflict-looking text) must not produce "
        f"conflict when rebase rc=0; got {res!r}")
    assert res["exit_code"] == 0
    assert res.get("conflicted_files") is None or res.get("conflicted_files") == []


def test_genuinely_dirty_non_ledger_file_still_blocked():
    """(c) Regression guard: a non-ledger real task file (not in _BENIGN_REFRESH_PATTERNS)
    must still block integrate — the benign-stash logic must never silently bypass a real
    conflict. Even when benign ledger files are stashed first (the correct code path when
    both benign and real files are present), the rebase must fail on the real dirty file
    and integrate must NOT push. status must be 'conflict' or 'dirty_blocked'."""
    push_calls = []

    def runner(cmd, cwd=None):
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "-C":
            inner_sub = cmd[3] if len(cmd) > 3 else ""
            if inner_sub == "push":
                push_calls.append(cmd)
            return (0, "", "")
        return fake(cmd, cwd)

    # A genuine task-work file alongside a benign ledger — the real file must
    # block even after the benign ledger is stashed. The rebase fails on the
    # real file (conflicted) so we never reach the push.
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": "e1 z"},
        head_sha="b0",
        rebase_rcs=[1],
        conflicts=["products/myapp/backend/api.py"],
        # Both a real file AND a benign ledger — the real file must dominate.
        status_output=(
            " M products/myapp/backend/api.py\n"
            " M project-history/branch-tree.ndjson\n"
        ),
    )
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=runner)
    assert res["status"] in ("conflict", "dirty_blocked"), (
        f"a non-ledger real file must block integrate; got {res!r}")
    assert res["exit_code"] == 1
    # CRITICAL: must NEVER push a conflicted/dirty state to dev.
    assert not push_calls, (
        f"must NEVER push when real task files are dirty; push_calls={push_calls}")


# ---------------------------------------------------------------------------
# `action='integrate'` migration-number-collision gate — the SECOND backstop.
#
# `migration_check` is injected (mirrors the `settle=` / `salvage_recorder=`
# test seams already used above) — no real filesystem scan here, only the
# gate's OWN logic: does it fire when relevant, stay silent when not, filter
# to the right directories, and never crash the whole integrate on an
# unexpected exception. The REAL `check_migration_number_collision` behavior
# is already covered end-to-end in test_compliance.py; the REAL
# `_default_migration_collision_check` wrapper is covered separately below
# against a real temp git repo.
# ---------------------------------------------------------------------------


def _migration_diff_output(*paths: str) -> str:
    return "\n".join(paths)


def test_migration_collision_blocks_before_push():
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        diff_output=_migration_diff_output(
            "products/core/backend/migrations/050_x.sql"
        ),
    )
    checked = []

    def fake_check(abs_wt_path):
        checked.append(abs_wt_path)
        return [{
            "product": "core",
            "file": "products/core/backend/migrations/",
            "issue": "migration number 050 is claimed by 2 files",
            "severity": "high",
        }]

    res = T.task_branch(
        action="integrate", slug="x", confirm=True, run=fake,
        migration_check=fake_check,
    )
    assert res["status"] == "blocked", res
    assert res["exit_code"] == 1
    assert len(res["migration_collision_findings"]) == 1
    assert res["introduced_migrations"] == ["products/core/backend/migrations/050_x.sql"]
    assert fake.pushes() == [], "must NEVER push when a migration collision is found"
    assert len(checked) == 1, "the checker must run exactly once"


def test_migration_collision_in_unrelated_directory_does_not_block():
    """A finding in a DIFFERENT product's migrations dir than what THIS
    branch introduces must not false-block an unrelated integrate."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        diff_output=_migration_diff_output(
            "products/core/backend/migrations/050_x.sql"
        ),
    )

    def fake_check(abs_wt_path):
        return [{
            "product": "other-product",
            "file": "products/other-product/backend/migrations/",
            "issue": "unrelated collision",
            "severity": "high",
        }]

    res = T.task_branch(
        action="integrate", slug="x", confirm=True, run=fake,
        migration_check=fake_check,
    )
    assert res["status"] == "integrated", res
    assert len(fake.pushes()) == 1


def test_no_introduced_migrations_skips_the_check_entirely():
    """Zero migrations touched by this branch ⇒ the checker is never called
    (scoped, not a blanket repo-wide gate on every integrate)."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        # diff_output defaults to "" — no migrations introduced.
    )

    def must_not_be_called(abs_wt_path):
        raise AssertionError("migration_check must not run when nothing was introduced")

    res = T.task_branch(
        action="integrate", slug="x", confirm=True, run=fake,
        migration_check=must_not_be_called,
    )
    assert res["status"] == "integrated", res
    assert len(fake.pushes()) == 1


def test_migration_check_exception_does_not_crash_integrate():
    """A broken checker degrades to 'no findings' rather than taking down
    the whole integrate — the gate is a net, not a new failure mode."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        diff_output=_migration_diff_output(
            "products/core/backend/migrations/050_x.sql"
        ),
    )

    def broken_check(abs_wt_path):
        raise RuntimeError("boom")

    res = T.task_branch(
        action="integrate", slug="x", confirm=True, run=fake,
        migration_check=broken_check,
    )
    assert res["status"] == "integrated", res
    assert len(fake.pushes()) == 1


def test_migration_check_not_invoked_with_injected_run_and_no_explicit_check():
    """Gating symmetry with settle_fn: an injected runner (test/custom
    context) must NOT trigger the REAL default checker."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        diff_output=_migration_diff_output(
            "products/core/backend/migrations/050_x.sql"
        ),
    )
    # No `migration_check=` passed — with an injected `run`, migration_check_fn
    # resolves to None, so the gate is skipped regardless of diff_output.
    res = T.task_branch(action="integrate", slug="x", confirm=True, run=fake)
    assert res["status"] == "integrated", res
    assert len(fake.pushes()) == 1


def test_migration_collision_blocks_before_stash_leaves_worktree_clean():
    """A blocked migration-collision integrate must still pop any benign
    auto-stash before returning — no orphan stash left behind."""
    fake = FakeGit(
        refs={"origin/dev": "d0", "feat/x": "b0"},
        anc=_anc_pairs([]),
        logs={"d0..b0": "c1 x", "b0..d0": ""},
        head_sha="b0",
        porcelain="",
        status_output=" M project-history/branch-tree.ndjson\n",
        diff_output=_migration_diff_output(
            "products/core/backend/migrations/050_x.sql"
        ),
    )

    def fake_check(abs_wt_path):
        return [{
            "product": "core", "file": "products/core/backend/migrations/",
            "issue": "collision", "severity": "high",
        }]

    res = T.task_branch(
        action="integrate", slug="x", confirm=True, run=fake,
        migration_check=fake_check,
    )
    assert res["status"] == "blocked", res
    # `-C <wt> stash ...` form (see `_stash_benign_artifacts` / `_pop_stash`)
    # — "stash" sits at cmd[3], not cmd[1].
    stash_calls = [c for c, _cwd in fake.calls if "stash" in c]
    assert stash_calls, f"expected at least one stash call; calls={fake.calls}"
    assert any("pop" in c for c in stash_calls), (
        f"stash must be popped before returning blocked; stash_calls={stash_calls}"
    )


class TestDefaultMigrationCollisionCheck:
    """`_default_migration_collision_check` against a real filesystem tree —
    the thin production wrapper around `check_migration_number_collision`,
    exercised for real (not injected) since it is trivial glue. Leg A (the
    on-disk duplicate scan) needs no real git repo; `tmp_path` is not one,
    so Leg B degrades gracefully to no findings (already covered directly in
    test_compliance.py's `TestCheckMigrationNumberCollision`)."""

    def test_flags_a_real_on_disk_duplicate(self, tmp_path):
        mig = tmp_path / "products" / "core" / "backend" / "migrations"
        mig.mkdir(parents=True)
        (mig / "050_a.sql").write_text("SELECT 1;\n")
        (mig / "050_b.sql").write_text("SELECT 1;\n")

        findings = T._default_migration_collision_check(str(tmp_path))

        assert any(f["severity"] == "high" and "050" in f["issue"] for f in findings), findings

    def test_clean_tree_returns_no_findings(self, tmp_path):
        mig = tmp_path / "products" / "core" / "backend" / "migrations"
        mig.mkdir(parents=True)
        (mig / "050_a.sql").write_text("SELECT 1;\n")

        assert T._default_migration_collision_check(str(tmp_path)) == []
