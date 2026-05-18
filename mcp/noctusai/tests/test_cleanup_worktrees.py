"""Tests for the noctus.dev.cleanup_stale_worktrees tool.

Behaviour parity with scripts/cleanup-stale-worktrees.sh: merged-branch
worktrees are stale; unmerged are active (kept); uncommitted work routes to
`dirty` (force does NOT override); dry-run unless force=True.

Builds real git repos + real `git worktree add` so the merge/ancestry/
patch-id/dirty predicates exercise the real git plumbing (no monkey-patch
of our own code — the no-workarounds rule).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.cleanup_worktrees import cleanup_stale_worktrees


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True,
        capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with `main`, an `origin/main` ref, and a .claude/worktrees dir.

    `origin/main` is faked as a local ref so the tool's base-resolution
    (`origin/main` then fallback `main`) resolves deterministically.
    """
    r = tmp_path / "noc"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    (r / "f").write_text("base\n")
    _git(r, "add", "f")
    _git(r, "commit", "-qm", "base")
    # Fake origin/main pointing at current main tip.
    _git(r, "update-ref", "refs/remotes/origin/main", "HEAD")
    (r / ".claude" / "worktrees").mkdir(parents=True)
    return r


def _add_worktree(repo: Path, name: str, branch: str) -> Path:
    wt = repo / ".claude" / "worktrees" / name
    _git(repo, "worktree", "add", "-q", "-b", branch, str(wt))
    return wt


class TestDryRunDefault:
    def test_no_worktree_dir_status_nothing(self, tmp_path):
        r = tmp_path / "empty"
        r.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(r), check=True)
        result = cleanup_stale_worktrees(repo_root=r)
        assert result["status"] == "nothing"
        assert result["stale"] == []
        assert result["dry_run"] is True

    def test_merged_worktree_is_stale_but_dry_run_keeps_it(self, repo):
        # Branch with NO new commits beyond main → merge-base ancestor → merged.
        wt = _add_worktree(repo, "agent-merged", "wt-merged")
        result = cleanup_stale_worktrees(repo_root=repo)  # force defaults False
        assert str(wt) in result["stale"]
        assert result["dry_run"] is True
        assert result["status"] == "dry_run"
        assert result["removed"] == 0
        assert wt.exists(), "dry-run must NOT remove the worktree"


class TestMergePredicate:
    def test_unmerged_branch_is_active_kept(self, repo):
        wt = _add_worktree(repo, "agent-wip", "wt-wip")
        # Add an unmerged commit on the worktree's branch.
        (wt / "g").write_text("new\n")
        _git(wt, "add", "g")
        _git(wt, "commit", "-qm", "feat: unmerged work")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(wt) in result["active"]
        assert str(wt) not in result["stale"]
        assert wt.exists(), "unmerged WIP worktree must be kept"

    def test_cherry_picked_branch_detected_as_merged(self, repo):
        wt = _add_worktree(repo, "agent-cp", "wt-cp")
        (wt / "h").write_text("cp\n")
        _git(wt, "add", "h")
        _git(wt, "commit", "-qm", "feat: work to be cherry-picked")
        # Cherry-pick that commit onto main (new SHA, same patch-id), then
        # bump the fake origin/main ref.
        sha = _git(wt, "rev-parse", "HEAD").strip()
        _git(repo, "cherry-pick", sha)
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        result = cleanup_stale_worktrees(repo_root=repo)
        assert str(wt) in result["stale"], (
            "cherry-picked-to-main branch must classify as stale (patch-id)"
        )


class TestSafetyGates:
    def test_dirty_worktree_routes_to_dirty_not_stale(self, repo):
        wt = _add_worktree(repo, "agent-dirty", "wt-dirty")
        # Branch is merged (no new commits) BUT has uncommitted work.
        (wt / "uncommitted.txt").write_text("dirty\n")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        dirty_paths = [d["path"] for d in result["dirty"]]
        assert str(wt) in dirty_paths
        assert str(wt) not in result["stale"]
        assert wt.exists(), "force must NOT remove a dirty merged worktree"

    def test_force_removes_clean_merged_worktree(self, repo):
        wt = _add_worktree(repo, "agent-clean", "wt-clean")
        assert wt.exists()
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert result["status"] == "removed"
        assert result["removed"] >= 1
        assert not wt.exists(), "force=True must remove a clean merged worktree"

    def test_main_repo_never_classified(self, repo):
        _add_worktree(repo, "agent-clean2", "wt-clean2")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(repo) not in result["stale"]
        assert str(repo) not in result["active"]
        assert str(repo) == result["main"]

    def test_non_agent_sibling_dir_never_stale(self, repo):
        # A non-agent dir under worktrees/ must be ignored entirely.
        sibling = repo / ".claude" / "worktrees" / "sibling-workspace"
        sibling.mkdir()
        (sibling / "x").write_text("y")
        result = cleanup_stale_worktrees(repo_root=repo, force=True)
        assert str(sibling) not in result["stale"]


class TestOrphanDetection:
    def test_orphan_agent_dir_classified_stale(self, repo):
        # On-disk agent-* dir that git doesn't know about → orphan → stale.
        orphan = repo / ".claude" / "worktrees" / "agent-orphan"
        orphan.mkdir()
        (orphan / "leftover").write_text("junk")
        result = cleanup_stale_worktrees(repo_root=repo)
        assert str(orphan) in result["stale"]


class TestMcpRegistration:
    def test_register_callable(self):
        from tools.noctus.dev.cleanup_worktrees import register
        assert callable(register)

    def test_register_wires_tool_onto_a_server(self):
        """The module's own register() wires the tool. (Global build_server()
        wiring lands when the architect adds cleanup_worktrees to
        tools/noctus/dev/__init__.py per the integration recipe.)"""
        from mcp.server.fastmcp import FastMCP

        from tools.noctus.dev.cleanup_worktrees import register
        s = FastMCP(name="t")
        register(s)
        assert "noctus.dev.cleanup_stale_worktrees" in s._tool_manager._tools
