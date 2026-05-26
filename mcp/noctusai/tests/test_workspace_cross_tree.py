"""Regression tests for the workspace REPO_ROOT cross-tree drift fix
(2026-05-26 N=3 codification).

Covers (1) NOCTUSAI_HOME env override, (2) worktree-boundary auto-detect,
(3) the previously-broken scenario (cli.py from worktree must resolve to
the worktree, not PRIMARY).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import workspace  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("NOCTUSAI_HOME", raising=False)


class TestEnvOverride:
    def test_noctusai_home_env_takes_priority(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUSAI_HOME", str(tmp_path))
        ctx = workspace.get_workspace_context()
        assert ctx.root == tmp_path.resolve()
        assert ctx.noctusai_home == tmp_path.resolve()
        assert ctx.extra.get("resolved_via") == "NOCTUSAI_HOME"

    def test_invalid_env_falls_through(self, tmp_path, monkeypatch):
        # Env var points to non-existent dir → fall through to marker walk.
        monkeypatch.setenv("NOCTUSAI_HOME", str(tmp_path / "does-not-exist"))
        ctx = workspace.get_workspace_context(tmp_path)
        # Without a marker the fallback noc root is returned (file-relative
        # to workspace.py). Either way, NOT the bogus env path.
        assert ctx.root != (tmp_path / "does-not-exist").resolve()


class TestWorktreeBoundaryDetection:
    def test_cwd_inside_worktree_resolves_to_worktree(self, tmp_path):
        # Simulate the noc shape: <primary>/.claude/worktrees/<slug>/<subdir>
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        (wt / "mcp" / "noctusai").mkdir(parents=True)
        # No marker file → boundary detection still triggers from cwd inside.
        ctx = workspace.get_workspace_context(wt / "mcp" / "noctusai")
        assert ctx.root == wt.resolve()
        assert ctx.noctusai_home == wt.resolve()
        assert ctx.extra.get("resolved_via") == "worktree-boundary"

    def test_cwd_at_worktree_root_resolves_to_worktree(self, tmp_path):
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        wt.mkdir(parents=True)
        ctx = workspace.get_workspace_context(wt)
        assert ctx.root == wt.resolve()
        assert ctx.extra.get("resolved_via") == "worktree-boundary"

    def test_cwd_in_primary_not_under_worktrees_falls_through(self, tmp_path):
        # cwd in primary's regular subdir → marker walk (no worktree boundary).
        primary = tmp_path / "noctusai"
        (primary / "mcp" / "noctusai").mkdir(parents=True)
        (primary / workspace.MARKER_FILENAME).write_text(
            "workspace_kind=primary\nworkspace_name=noctusai\n",
            encoding="utf-8",
        )
        ctx = workspace.get_workspace_context(primary / "mcp" / "noctusai")
        # NOT worktree-boundary; either marker walk or fallback.
        assert ctx.extra.get("resolved_via") != "worktree-boundary"
        assert ctx.root == primary.resolve()


class TestRegressionAgainstPriorDrifts:
    """Direct reproductions of the N=3 drift recurrences."""

    def test_phase_a_scenario_worktree_resolves_to_worktree(self, tmp_path):
        # Phase A: cli.py from worktree saw PRIMARY's stale agent files.
        # Fix: cwd-inside-worktree returns worktree as both root + home.
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "agent-context-architecture"
        wt.mkdir(parents=True)
        ctx = workspace.get_workspace_context(wt)
        assert "worktrees" in str(ctx.noctusai_home), (
            "Phase A regression: noctusai_home should be the worktree, "
            f"got {ctx.noctusai_home}"
        )

    def test_phase_b_scenario_keeper_sees_worktree_state(self, tmp_path):
        # Phase B: check_contextualize_alignment ran from worktree but used
        # cached REPO_ROOT=PRIMARY → reported missing pointers that DID
        # exist in the worktree.
        # Fix: REPO_ROOT (via get_workspace_context) resolves to worktree.
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "salvage-phase-b"
        wt.mkdir(parents=True)
        ctx = workspace.get_workspace_context(wt)
        # The keeper would now scan wt/CONTEXTUALIZE.md, not primary/CONTEXTUALIZE.md.
        assert ctx.noctusai_home == wt.resolve()
