"""Tests for the pointer-lifecycle predicate + its safety-net keeper (2026-09-23).

`pointer_branch_landed` is shared by session_end_sweep's healer and the
`check_stale_branch_pointers` keeper so they can never disagree. The key case
is a REBASED branch: its recorded sha never reaches dev, but its Noc-Branch
trailer does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _worktree_staleness as wts  # noqa: E402
from tools.noctus.dev.compliance import check_stale_branch_pointers  # noqa: E402


def _runner(*, refs=(), ancestors=(), trailers="", ahead=None, worktrees=""):
    ahead = ahead or {}

    def run(args):
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return (0, args[-1], "") if args[-1] in refs or args[-1] == "origin/dev" else (1, "", "")
        if args[:3] == ["git", "merge-base", "--is-ancestor"]:
            return (0, "", "") if (args[3], args[4]) in ancestors else (1, "", "")
        if args[:2] == ["git", "log"] and "--format=%(trailers:key=Noc-Branch,valueonly)" in args:
            return 0, trailers, ""
        if args[:3] == ["git", "rev-list", "--count"]:
            return 0, str(ahead.get(args[3], 0)), ""
        if args[:2] == ["git", "cherry"]:
            return 0, "", ""
        if args[:3] == ["git", "log", "--oneline"]:
            return 0, "", ""
        if args[:3] == ["git", "worktree", "list"]:
            return 0, worktrees, ""
        return 1, "", ""

    return run


def test_rebased_and_deleted_branch_is_proven_by_its_trailer():
    run = _runner(trailers="dev\nfeat/x\n")
    assert wts.pointer_branch_landed(run, "feat/x", "prerebase", "origin/dev") == (
        True, "branch cleaned up; its Noc-Branch trailer commit is on base")


def test_deleted_branch_with_no_evidence_is_unproven():
    run = _runner(trailers="feat/other\n")
    assert wts.pointer_branch_landed(run, "feat/x", "abc", "origin/dev") == (False, "unproven")


def test_fresh_fork_still_on_its_fork_point_is_not_landed():
    # A fresh fork is trivially its own ancestor (the 2026-09-16 false positive).
    run = _runner(refs={"feat/x"}, ancestors={("feat/x", "origin/dev")}, trailers="")
    assert wts.pointer_branch_landed(run, "feat/x", "d0", "origin/dev", fork_sha="feat/x")[0] is False


def test_existing_branch_merged_past_its_fork_point_is_landed():
    run = _runner(refs={"feat/x"}, ancestors={("feat/x", "origin/dev")}, trailers="")
    assert wts.pointer_branch_landed(run, "feat/x", "b1", "origin/dev", fork_sha="d0") == (
        True, "branch ref merged into base")


def test_fork_sha_parsed_from_pointer_base():
    assert wts.fork_sha_from_pointer_base("origin/dev@c6e9445e7") == "c6e9445e7"
    assert wts.fork_sha_from_pointer_base("dev") == ""


def test_recorded_commit_ancestry_still_proves_landing():
    run = _runner(ancestors={("abc", "origin/dev")})
    assert wts.pointer_branch_landed(run, "feat/x", "abc", "origin/dev") == (
        True, "branch cleaned up; recorded commit is on base")


def _ledger(tmp_path, rows):
    p = tmp_path / "project-history"
    p.mkdir()
    (p / "branch-tree.ndjson").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


class TestStaleBranchPointers:
    """Regression pins for `check_stale_branch_pointers` (true + false positives)."""

    def test_keeper_blocks_only_on_the_pushing_sessions_own_stale_pointer(self, tmp_path):
        root = _ledger(tmp_path, [
            {"branch": "feat/mine", "status": "on_going", "commit": "a", "session": "S1"},
            {"branch": "feat/peer", "status": "integrated-worktree-live", "commit": "b", "session": "S2"},
        ])
        run = _runner(trailers="feat/mine\nfeat/peer\n")
        issues = check_stale_branch_pointers(session="S1", repo_root=root, run=run)
        sev = {i["issue"].split("'")[1]: i["severity"] for i in issues}
        assert sev == {"feat/mine": "high", "feat/peer": "warning"}


    def test_keeper_ignores_live_worktrees_terminal_and_unlanded_pointers(self, tmp_path):
        root = _ledger(tmp_path, [
            {"branch": "feat/live", "status": "integrated-worktree-live", "commit": "a", "session": "S1"},
            {"branch": "feat/done", "status": "shipped", "commit": "b", "session": "S1"},
            {"branch": "feat/wip", "status": "on_going", "commit": "c", "session": "S1"},
        ])
        run = _runner(trailers="feat/live\nfeat/done\n", worktrees="worktree /r/x\nbranch refs/heads/feat/live\n")
        assert check_stale_branch_pointers(session="S1", repo_root=root, run=run) == []
