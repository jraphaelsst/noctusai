"""Root cause of the branch-pointer-agent-worktree wall (GW-7e9f3dd8) (3 hand-written role=steward pointers).

An engineer pointer (base=origin/dev, parent=dev) was judged "unrelated histories" because the keeper resolved
parent `dev` to the LOCAL dev branch, which on a primary checkout carries local-only commits and so diverges from
origin/dev. `dev` and `origin/dev` are the same integration branch: the remote-tracking ref is the truth, the
local branch is not. The rule is also role-independent (a steward pointer passed only because that role skipped
the pairing check). Real git in a tmp dir, no patching of our own code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_check_branch_tree_mirror import _add_commit, _base_row, _git, _init_repo, _write_ledger  # noqa: E402
from tools.noctus.dev.compliance import check_branch_tree_mirror  # noqa: E402


@pytest.fixture()
def diverged(tmp_path):
    root, sha = _init_repo(tmp_path)
    _git(root, "branch", "dev")
    _git(root, "checkout", "dev")
    _add_commit(root, message="local only commit on dev")
    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "tmp-remote", sha)
    remote_tip = _add_commit(root, message="remote only commit")
    _git(root, "update-ref", "refs/remotes/origin/dev", remote_tip)
    _git(root, "checkout", "main")
    _git(root, "branch", "feat/e", remote_tip)
    return root, remote_tip


def test_engineer_origin_dev_base_with_parent_dev_passes(diverged):
    root, tip = diverged
    _write_ledger(root, [_base_row("feat/e", tip, role="engineer", base="origin/dev", parent="dev")])
    assert check_branch_tree_mirror(branch="feat/e", repo_root=root) == []


@pytest.mark.parametrize("role", ["steward", "engineer", "orchestrator"])
def test_every_role_is_judged_alike(diverged, role):
    root, tip = diverged
    _write_ledger(root, [_base_row("feat/e", tip, role=role, base="origin/dev", parent="dev")])
    assert check_branch_tree_mirror(branch="feat/e", repo_root=root) == []


def test_a_genuinely_unrelated_feature_parent_is_still_refused(diverged):
    root, tip = diverged
    _git(root, "checkout", "--orphan", "feat/orch")
    _git(root, "commit", "--allow-empty", "-m", "unrelated root")
    _git(root, "checkout", "main")
    _write_ledger(root, [_base_row("feat/e", tip, role="engineer", base="origin/dev", parent="feat/orch")])
    issues = check_branch_tree_mirror(branch="feat/e", repo_root=root)
    assert any("unrelated" in i["issue"] for i in issues), issues
