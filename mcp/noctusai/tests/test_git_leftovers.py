"""Regression tests for `check_git_leftovers` — the drift-fix-on-contact git-shape gate.

KB § PATTERNS/drift-fix-on-contact.md. The keeper scans for the recurring drift
class (untracked at repo root depth 1, worktree uncommitted state) that the
existing keepers (`check_branch_orphan` / `check_dispatcher_staleness` /
`check_archive_staleness`) did not catch between commit gates.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_git_leftovers  # noqa: E402


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@noc.test")
    _git(root, "config", "user.name", "test")
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "init")


class TestGitLeftovers:
    def test_clean_tree_passes(self, tmp_path):
        _init_repo(tmp_path)
        assert check_git_leftovers(repo_root=tmp_path) == []

    def test_untracked_at_root_flagged(self, tmp_path):
        _init_repo(tmp_path)
        (tmp_path / "decision.md").write_text("scratch\n", encoding="utf-8")
        issues = check_git_leftovers(repo_root=tmp_path)
        assert any(i["file"] == "decision.md" for i in issues)
        assert any(i["symbol"] == "untracked-at-root" for i in issues)

    def test_untracked_in_subdir_not_flagged(self, tmp_path):
        # Untracked files at depth ≥2 are out of scope (own keeper class).
        _init_repo(tmp_path)
        (tmp_path / "products").mkdir()
        (tmp_path / "products" / "scratch.txt").write_text("x\n", encoding="utf-8")
        issues = check_git_leftovers(repo_root=tmp_path)
        # Only the depth-1 `products/` directory itself would be reported; but
        # `products/scratch.txt` (depth-2) must NOT be in the list.
        assert all(i["file"] != "products/scratch.txt" for i in issues)

    def test_gitignored_not_flagged(self, tmp_path):
        _init_repo(tmp_path)
        (tmp_path / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
        _git(tmp_path, "add", ".gitignore")
        _git(tmp_path, "commit", "-q", "-m", "gitignore")
        (tmp_path / "ignored.md").write_text("x\n", encoding="utf-8")
        issues = check_git_leftovers(repo_root=tmp_path)
        # `ignored.md` is in .gitignore → `git status --porcelain` doesn't list
        # it → the keeper doesn't flag it. The clean leg.
        assert all(i["file"] != "ignored.md" for i in issues)

    def test_non_git_context_silently_skipped(self, tmp_path):
        # No .git → silent skip (test/vendored contexts).
        assert check_git_leftovers(repo_root=tmp_path) == []

    def test_severity_high_on_drift(self, tmp_path):
        _init_repo(tmp_path)
        (tmp_path / "notes.md").write_text("x\n", encoding="utf-8")
        issues = check_git_leftovers(repo_root=tmp_path)
        assert any(i["severity"] == "high" for i in issues)
