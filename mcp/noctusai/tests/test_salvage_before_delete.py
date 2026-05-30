"""Colocated tests for `salvage_before_delete`.

Coverage:
  kind='branch' dry_run=True  — reports preservation plan, no files written
  kind='branch' dry_run=False — writes salvage ledger entry
  kind='worktree'             — reports worktree recovery pointer
  kind='project'              — reports absorption obligations
  unknown kind                — returns ok=False with explanation
  no real origin branch deleted in ANY test (mocked or temp repos)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.salvage_before_delete import salvage_before_delete  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True,
    )


def _setup_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Minimal git repo with an 'origin' bare remote and a dev branch."""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "--initial-branch=dev")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=dev")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "remote", "add", "origin", str(bare))

    (repo / "readme.txt").write_text("initial")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial commit")
    _git(repo, "push", "origin", "dev")
    return repo, bare


def _make_branch_with_unique_commit(repo: Path, branch: str) -> str:
    """Create a branch + unique commit + push. Return SHA."""
    _git(repo, "checkout", "-b", branch)
    (repo / f"{branch.replace('/', '_')}.txt").write_text("unique content")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", f"unique commit on {branch}")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "origin", branch)
    _git(repo, "checkout", "dev")
    return sha


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSalvageBeforeDeleteBranchDryRun:
    def test_dry_run_reports_without_writing_ledger(self, tmp_path: Path):
        """dry_run=True reports preservation plan; no ledger entry written."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        _make_branch_with_unique_commit(repo, "feat/dry-branch")

        result = salvage_before_delete(
            target="feat/dry-branch", kind="branch", repo_root=repo, dry_run=True
        )

        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["ledger_entry_written"] is False
        assert len(result["preserved"]) > 0  # at least a recovery pointer

        # Ledger should NOT exist yet.
        ledger = repo / "project-history" / "worktree-salvage.ndjson"
        assert not ledger.exists(), "Ledger must NOT be written in dry_run=True"

    def test_dry_run_branch_not_found_produces_warning(self, tmp_path: Path):
        """Salvage of a nonexistent branch → ok=True with warning."""
        repo, _ = _setup_repo_with_remote(tmp_path)

        result = salvage_before_delete(
            target="feat/nonexistent", kind="branch", repo_root=repo, dry_run=True
        )

        assert result["ok"] is True
        assert len(result["warnings"]) > 0


class TestSalvageBeforeDeleteBranchLive:
    def test_live_run_writes_ledger(self, tmp_path: Path):
        """dry_run=False writes a salvage ledger entry."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        _make_branch_with_unique_commit(repo, "feat/live-branch")

        result = salvage_before_delete(
            target="feat/live-branch", kind="branch", repo_root=repo, dry_run=False
        )

        assert result["ok"] is True
        assert result["ledger_entry_written"] is True

        ledger = repo / "project-history" / "worktree-salvage.ndjson"
        assert ledger.exists(), "Ledger MUST exist after dry_run=False"
        entries = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        assert any(e.get("target") == "feat/live-branch" for e in entries), (
            f"No ledger entry for 'feat/live-branch'; entries: {entries}"
        )

    def test_live_run_integrated_branch_skips_patch(self, tmp_path: Path):
        """If branch content is on dev (cherry-equiv), no patch file written."""
        repo, _ = _setup_repo_with_remote(tmp_path)
        # Create branch + cherry-pick it onto dev = integrated.
        _git(repo, "checkout", "-b", "feat/integrated-live")
        (repo / "integrated.txt").write_text("integrated content")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "integrated commit")
        sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "push", "origin", "feat/integrated-live")
        _git(repo, "checkout", "dev")
        _git(repo, "cherry-pick", sha)
        _git(repo, "push", "origin", "dev")

        result = salvage_before_delete(
            target="feat/integrated-live", kind="branch", repo_root=repo, dry_run=False
        )

        assert result["ok"] is True
        # patch_files should be empty (content already on dev).
        assert result.get("patch_files", []) == [], (
            "Integrated branch should not generate patch files"
        )


class TestSalvageBeforeDeleteWorktree:
    def test_worktree_kind_returns_recovery_pointer(self, tmp_path: Path):
        """kind='worktree' for a real worktree path returns ok + recovery pointer."""
        repo, _ = _setup_repo_with_remote(tmp_path)

        # Create the new branch WHILE on dev, then add a worktree for it.
        # (Can't use `git worktree add` for the currently-checked-out branch.)
        wt_dir = repo / ".claude" / "worktrees" / "test-wt"
        _git(repo, "branch", "feat/wt-branch")
        _git(repo, "worktree", "add", str(wt_dir), "feat/wt-branch")

        result = salvage_before_delete(
            target="test-wt", kind="worktree", repo_root=repo, dry_run=True
        )

        assert result["ok"] is True
        assert any("recovery-pointer" in p for p in result["preserved"])

    def test_worktree_missing_slug_produces_warning(self, tmp_path: Path):
        """kind='worktree' for nonexistent slug → ok=True, warning."""
        repo, _ = _setup_repo_with_remote(tmp_path)

        result = salvage_before_delete(
            target="nonexistent-wt", kind="worktree", repo_root=repo, dry_run=True
        )

        assert result["ok"] is True
        assert len(result["warnings"]) > 0


class TestSalvageBeforeDeleteProject:
    def test_project_with_findings_md_surfaces_absorption(self, tmp_path: Path):
        """kind='project' with a findings.md → absorption-obligation in preserved."""
        repo, _ = _setup_repo_with_remote(tmp_path)

        # Create a fake project dir.
        proj_dir = repo / "projects" / "my-project"
        proj_dir.mkdir(parents=True)
        (proj_dir / "findings.md").write_text("## Findings\nsome important learning")

        result = salvage_before_delete(
            target="projects/my-project", kind="project", repo_root=repo, dry_run=True
        )

        assert result["ok"] is True
        absorption_msgs = [p for p in result["preserved"] if "absorption-obligation" in p]
        assert len(absorption_msgs) > 0, (
            f"Expected absorption-obligation in preserved; got: {result['preserved']}"
        )


class TestSalvageBeforeDeleteUnknownKind:
    def test_unknown_kind_returns_error(self, tmp_path: Path):
        repo, _ = _setup_repo_with_remote(tmp_path)

        result = salvage_before_delete(
            target="whatever", kind="invalid_kind", repo_root=repo, dry_run=True
        )

        assert result["ok"] is False
        assert len(result["warnings"]) > 0
        assert "unknown kind" in result["warnings"][0]
