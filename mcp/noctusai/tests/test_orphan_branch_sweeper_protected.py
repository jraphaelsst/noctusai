"""`orphan_branch_sweeper` — the protected-branch guard.

Regression cover for a real 2026-08-21 finding: a live sweep reported

    prod — safe to delete (0 commits ahead of origin/dev; 569 behind)

The classifier's rule is "0 commits ahead of origin/dev ⇒ integrated ⇒
safe to delete". A release branch is 0-ahead **by definition** — it
trails dev, it never leads it — so the production branch scored as the
most disposable thing in the repo. And it was not a theoretical risk:
`git branch -d` refuses only *unmerged* branches, and prod is fully
merged into dev, so the delete would have succeeded.

These tests build a real git repo with that exact topology rather than
stubbing `_ahead_behind`, because the bug lived in the interaction
between git's ahead/behind semantics and the classifier — a stub would
have encoded the same wrong assumption the code did.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.noctus.dev import orphan_branch_sweeper as obs


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo shaped like noc: dev ahead, prod merged-and-trailing.

    `origin/dev` is a real remote-tracking ref, created by cloning into a
    bare remote and fetching back, so `rev-list --left-right` resolves it
    exactly as it does in the live repo.
    """
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "init", str(work))
    _git(work, "config", "user.email", "t@t.test")
    _git(work, "config", "user.name", "t")
    _git(work, "remote", "add", "origin", str(remote))

    (work / "f.txt").write_text("1\n")
    _git(work, "add", "f.txt")
    _git(work, "commit", "-m", "c1")
    _git(work, "branch", "-M", "dev")

    # prod + main pinned at the first commit — merged into dev, trailing it.
    _git(work, "branch", "prod")
    _git(work, "branch", "main")
    _git(work, "branch", "prod-backup")

    # A genuinely integrated feature branch, also 0-ahead.
    _git(work, "branch", "feat/already-merged")

    # dev moves on, leaving prod/main/prod-backup behind.
    (work / "f.txt").write_text("2\n")
    _git(work, "add", "f.txt")
    _git(work, "commit", "-m", "c2")

    _git(work, "push", "origin", "dev")
    _git(work, "fetch", "origin")
    return work


def _by_name(result: dict) -> dict[str, dict]:
    return {b["name"]: b for b in result["branches"]}


class TestClassification:
    def test_prod_is_protected_not_integrated(self, repo: Path):
        """The exact finding: prod must never read as safe to delete."""
        rows = _by_name(obs.scan(repo_root=repo))

        assert rows["prod"]["classification"] == "protected"
        assert "NEVER delete" in rows["prod"]["suggestion"]

    def test_prod_really_is_zero_ahead(self, repo: Path):
        """Proves the fixture reproduces the bug's precondition.

        Without this, a passing guard test could be passing because the
        topology never triggered the heuristic in the first place.
        """
        rows = _by_name(obs.scan(repo_root=repo))

        assert rows["prod"]["ahead"] == 0
        assert rows["prod"]["behind"] > 0

    @pytest.mark.parametrize("name", ["main", "dev", "prod", "prod-backup"])
    def test_every_protected_branch_is_classified(self, repo: Path, name: str):
        rows = _by_name(obs.scan(repo_root=repo))

        assert rows[name]["classification"] == "protected"

    def test_protected_branches_are_returned_not_silently_dropped(
        self, repo: Path
    ):
        """The gap that hid the bug.

        `main`/`dev` used to be `continue`d, so the output never showed
        which branches the guard covered — and a missing `prod` was
        therefore invisible. A visible row is auditable.
        """
        rows = _by_name(obs.scan(repo_root=repo))

        assert obs.PROTECTED_BRANCHES <= set(rows)

    def test_an_ordinary_merged_branch_is_still_integrated(self, repo: Path):
        """The guard must not blunt the tool's actual job."""
        rows = _by_name(obs.scan(repo_root=repo))

        assert rows["feat/already-merged"]["classification"] == "integrated"


class TestDeleteRefusal:
    def test_dry_run_never_lists_a_protected_branch(self, repo: Path):
        result = obs.delete_integrated(repo_root=repo, dry_run=True)

        assert not (set(result["deleted"]) & obs.PROTECTED_BRANCHES)

    def test_dry_run_still_lists_ordinary_integrated_branches(self, repo: Path):
        result = obs.delete_integrated(repo_root=repo, dry_run=True)

        assert "feat/already-merged" in result["deleted"]

    def test_a_real_delete_leaves_prod_alive(self, repo: Path):
        """The consequence, asserted against git rather than the report.

        `git branch -d prod` would SUCCEED here — prod is fully merged
        into dev — so this is the test that would have caught the bug
        with the branch actually gone.
        """
        obs.delete_integrated(repo_root=repo, dry_run=False)

        branches = _git(repo, "branch", "--format=%(refname:short)").split()
        assert "prod" in branches
        assert "main" in branches
        assert "prod-backup" in branches
        assert "feat/already-merged" not in branches

    def test_protected_branches_are_reported_as_skipped(self, repo: Path):
        """Skipped-with-reason, not silently absent — the same visibility
        rule the classifier now follows."""
        result = obs.delete_integrated(repo_root=repo, dry_run=True)

        skipped = {s["name"] for s in result["skipped"]}
        assert obs.PROTECTED_BRANCHES <= skipped
        assert all(
            "protected" in s["reason"] for s in result["skipped"]
        )


class TestGuardPredicate:
    @pytest.mark.parametrize("name", ["main", "dev", "prod", "prod-backup"])
    def test_is_protected_true(self, name: str):
        assert obs.is_protected(name) is True

    @pytest.mark.parametrize(
        "name", ["feat/x", "prod-ish", "my-prod", "production", "devel"]
    )
    def test_is_protected_is_exact_not_substring(self, name: str):
        """A substring match would protect `feat/prod-roi` by accident and
        quietly stop the sweeper from ever cleaning it up."""
        assert obs.is_protected(name) is False
