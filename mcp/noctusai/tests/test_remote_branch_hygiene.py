"""Colocated tests for `remote_branch_hygiene`.

Coverage:
  classify_remote_branches:
    - integrated-by-cherry: branch tip content patch-equiv on origin/dev → integrated
    - integrated-by-subject: squash-merge keeps subject → integrated via subject match
    - unique: branch has commits not cherry-equiv and subject not on dev → unique
    - protected-excluded: dev/main/prod are classified 'protected'
    - verdict field: always one of integrated|unique|protected

  delete_integrated_engineer_remote:
    - dry_run=True (default): returns 'would-delete', never runs git push --delete
    - protected guard: dev/main/prod refused regardless
    - unique guard: unique branches refused until integrated
    - salvage-log gate: when salvage_log_required=True and no log entry → skipped
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.remote_branch_hygiene import (  # noqa: E402
    classify_remote_branches,
    delete_integrated_engineer_remote,
    _PROTECTED_BRANCHES,
)


# ── Helpers for building a minimal temp git repo with a fake remote ──────────

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True,
    )


def _setup_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a local repo + a bare 'origin' with dev branch.

    Returns (repo, bare_remote).
    """
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "--initial-branch=dev")
    _git(bare, "config", "user.email", "test@test.com")
    _git(bare, "config", "user.name", "Test")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=dev")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "remote", "add", "origin", str(bare))

    # Initial commit on dev.
    (repo / "readme.txt").write_text("initial")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    _git(repo, "push", "origin", "dev")

    return repo, bare


def _commit_on_branch(repo: Path, branch: str, filename: str, content: str, message: str) -> str:
    """Create a new commit on a new branch; push to origin. Returns commit SHA."""
    _git(repo, "checkout", "-b", branch)
    (repo / filename).write_text(content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "origin", branch)
    _git(repo, "checkout", "dev")
    return sha


def _cherry_pick_onto_dev(repo: Path, sha: str) -> None:
    """Cherry-pick sha onto dev + push."""
    _git(repo, "cherry-pick", sha)
    _git(repo, "push", "origin", "dev")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestClassifyRemoteBranches:
    """Tests for classify_remote_branches()."""

    def test_protected_branches_have_protected_verdict(self, tmp_path: Path):
        """dev/main/prod appear with verdict=protected."""
        repo, bare = _setup_repo_with_remote(tmp_path)
        # Push a 'main' and 'prod' branch to origin for this test.
        _git(repo, "checkout", "-b", "main")
        _git(repo, "push", "origin", "main")
        _git(repo, "checkout", "-b", "prod")
        _git(repo, "push", "origin", "prod")
        _git(repo, "checkout", "dev")

        results = classify_remote_branches(repo_root=repo)
        verdicts = {r["branch"]: r["verdict"] for r in results}

        assert verdicts.get("dev") == "protected"
        assert verdicts.get("main") == "protected"
        assert verdicts.get("prod") == "protected"

    def test_unique_branch_classified_unique(self, tmp_path: Path):
        """A branch with commits not on dev → unique."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        _commit_on_branch(repo, "feat/unique-work", "new_feature.txt", "new stuff", "add unique feature")

        results = classify_remote_branches(repo_root=repo)
        entry = next((r for r in results if r["branch"] == "feat/unique-work"), None)
        assert entry is not None
        assert entry["verdict"] == "unique"
        assert entry["unique_commits"] is not None
        assert entry["unique_commits"] > 0

    def test_integrated_by_cherry_pick(self, tmp_path: Path):
        """A branch whose content is cherry-picked onto dev → integrated."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        sha = _commit_on_branch(repo, "feat/cherry-work", "cherry.txt", "cherry content", "add cherry feature")
        _cherry_pick_onto_dev(repo, sha)

        results = classify_remote_branches(repo_root=repo)
        entry = next((r for r in results if r["branch"] == "feat/cherry-work"), None)
        assert entry is not None, f"branch not in results: {[r['branch'] for r in results]}"
        assert entry["verdict"] == "integrated", (
            f"Expected integrated but got {entry['verdict']}; "
            f"unique_commits={entry.get('unique_commits')}"
        )

    def test_integrated_by_subject_match(self, tmp_path: Path):
        """A branch whose tip subject appears in dev's log → integrated (squash-merge heuristic)."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        subject = "squash: feat x into dev"
        _commit_on_branch(repo, "feat/squash-work", "squash.txt", "squash content", subject)

        # Simulate a squash-merge by adding a commit to dev with the same subject.
        _git(repo, "checkout", "dev")
        (repo / "squash_merged.txt").write_text("squash result")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", subject)
        _git(repo, "push", "origin", "dev")

        results = classify_remote_branches(repo_root=repo)
        entry = next((r for r in results if r["branch"] == "feat/squash-work"), None)
        assert entry is not None
        assert entry["verdict"] == "integrated", (
            f"Expected integrated (subject match) but got {entry['verdict']}"
        )

    def test_result_has_required_fields(self, tmp_path: Path):
        """Every result entry has the required keys."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        _commit_on_branch(repo, "feat/fields-test", "fields.txt", "content", "fields test commit")

        results = classify_remote_branches(repo_root=repo)
        for entry in results:
            assert "branch" in entry
            assert "verdict" in entry
            assert entry["verdict"] in ("integrated", "unique", "protected")
            assert "age_days" in entry
            assert "subject" in entry
            assert "unique_commits" in entry


class TestDeleteIntegratedEngineerRemote:
    """Tests for delete_integrated_engineer_remote()."""

    def test_dry_run_default_never_deletes(self, tmp_path: Path):
        """dry_run=True (default) only reports 'would-delete', never pushes."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        sha = _commit_on_branch(repo, "feat/dry-run-test", "dryrun.txt", "content", "dry run commit")
        _cherry_pick_onto_dev(repo, sha)

        # Write a fake salvage log entry so the salvage-log gate passes.
        ledger = repo / "project-history" / "worktree-salvage.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps({"target": "feat/dry-run-test", "kind": "salvage-before-delete:branch"}) + "\n")

        result = delete_integrated_engineer_remote(
            branch="feat/dry-run-test", repo_root=repo, dry_run=True
        )
        assert result["dry_run"] is True
        assert result["action"] == "would-delete"
        assert result["ok"] is True

        # Verify branch still exists on remote.
        rc, out, _ = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "--heads", "origin", "feat/dry-run-test"],
            capture_output=True, text=True,
        ).returncode, *[None, None]
        still_there = _git(repo, "ls-remote", "--heads", "origin", "feat/dry-run-test").stdout.strip()
        assert still_there, "Branch should still exist after dry-run"

    def test_protected_branch_refused(self, tmp_path: Path):
        """dev/main/prod are always refused."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        for branch in ("dev", "main", "prod"):
            result = delete_integrated_engineer_remote(
                branch=branch, repo_root=repo, dry_run=True
            )
            assert result["ok"] is False
            assert result["action"] == "skipped"
            assert "protected" in result["reason"]

    def test_unique_branch_refused(self, tmp_path: Path):
        """A branch with unique content is refused."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        _commit_on_branch(repo, "feat/unique-refuse", "unique_r.txt", "unique", "unique commit not on dev")

        result = delete_integrated_engineer_remote(
            branch="feat/unique-refuse", repo_root=repo, dry_run=True
        )
        assert result["ok"] is False
        assert result["action"] == "skipped"

    def test_salvage_log_gate_blocks_without_entry(self, tmp_path: Path):
        """When salvage_log_required=True and no log entry for branch → skipped."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        sha = _commit_on_branch(repo, "feat/no-salvage", "ns.txt", "content", "no salvage commit")
        _cherry_pick_onto_dev(repo, sha)

        # No salvage ledger written.
        result = delete_integrated_engineer_remote(
            branch="feat/no-salvage", repo_root=repo, dry_run=True,
            salvage_log_required=True,
        )
        assert result["action"] == "skipped"
        assert "salvage" in result["reason"].lower()

    def test_salvage_log_gate_passes_with_entry(self, tmp_path: Path):
        """When salvage log has entry for branch → would-delete (dry_run)."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        sha = _commit_on_branch(repo, "feat/with-salvage", "ws.txt", "content", "with salvage commit")
        _cherry_pick_onto_dev(repo, sha)

        ledger = repo / "project-history" / "worktree-salvage.ndjson"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"target": "feat/with-salvage", "kind": "salvage-before-delete:branch"}) + "\n"
        )

        result = delete_integrated_engineer_remote(
            branch="feat/with-salvage", repo_root=repo, dry_run=True,
            salvage_log_required=True,
        )
        assert result["ok"] is True
        assert result["action"] == "would-delete"
