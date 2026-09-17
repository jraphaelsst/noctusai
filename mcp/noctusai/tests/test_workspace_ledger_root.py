"""Regression tests for `workspace.get_ledger_root()` — the fifth confirmed
incident of the ledger-into-worktree data-loss family (2026-09-17).

Sibling of `test_workspace_cross_tree.py` (which covers
`get_workspace_context`'s worktree-boundary STOP behavior). This resolver
does the OPPOSITE: it UNWRAPS the worktree boundary so repo-global
append-only ledgers (project-history/*.ndjson) always land in the PRIMARY
checkout, never a worktree that can be torn down.

KB § PATTERNS/common/claim-vs-evidence-shared-state.md.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import workspace  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("NOCTUSAI_HOME", raising=False)


class TestIdentityOutsideWorktree:
    def test_identity_with_marker(self, tmp_path):
        """Outside a worktree, get_ledger_root() matches get_noctusai_home()."""
        (tmp_path / ".noctusai-workspace").write_text(
            "workspace_kind=primary\nworkspace_name=noctusai\n", encoding="utf-8"
        )
        assert workspace.get_ledger_root(tmp_path) == tmp_path.resolve()
        assert workspace.get_ledger_root(tmp_path) == workspace.get_noctusai_home(tmp_path)

    def test_identity_without_marker_falls_back_like_noctusai_home(self, tmp_path):
        """No marker, no worktree boundary → same file-relative fallback as
        get_noctusai_home() (back-compat for CI / ad-hoc scripts / tmp dirs)."""
        assert workspace.get_ledger_root(tmp_path) == workspace.get_noctusai_home(tmp_path)


class TestUnwrapsWorktreeBoundary:
    def test_cwd_at_worktree_root_unwraps_to_primary(self, tmp_path):
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        wt.mkdir(parents=True)
        assert workspace.get_ledger_root(wt) == primary.resolve()

    def test_cwd_nested_inside_worktree_unwraps_to_primary(self, tmp_path):
        """Handles nesting: a call from deep inside the worktree's own tree
        (e.g. mcp/noctusai/) still unwraps all the way to the primary root —
        the exact shape session_end_sweep / auto_improvement / etc. hit when
        the MCP server boots with cwd inside an engineer's worktree."""
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        deep = wt / "mcp" / "noctusai" / "tools" / "noctus" / "dev"
        deep.mkdir(parents=True)
        assert workspace.get_ledger_root(deep) == primary.resolve()

    def test_this_is_the_opposite_of_get_noctusai_home(self, tmp_path):
        """The whole point: get_noctusai_home() STOPS at the worktree
        (correct for code-editing tools); get_ledger_root() UNWRAPS past it
        (correct for repo-global ledgers). They must differ here."""
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        wt.mkdir(parents=True)
        assert workspace.get_noctusai_home(wt) == wt.resolve()
        assert workspace.get_ledger_root(wt) == primary.resolve()
        assert workspace.get_ledger_root(wt) != workspace.get_noctusai_home(wt)

    def test_missing_primary_directory_still_resolves_structurally(self, tmp_path):
        """get_ledger_root() is a pure path-structure unwrap — it does not
        require the unwrapped primary to physically exist / carry a marker.
        A worktree can be created (git worktree add) before any caller reads
        the primary again; the resolver must not raise."""
        primary = tmp_path / "does-not-exist-yet"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        wt.mkdir(parents=True)
        # Remove the primary's OWN direct marker/content so only the
        # structural .claude/worktrees/<slug> shape remains — the resolver
        # must still unwrap on structure alone.
        result = workspace.get_ledger_root(wt)
        assert result == primary.resolve()
        # No exception raised even though `primary` carries no
        # `.noctusai-workspace` marker of its own.


class TestEnvOverride:
    def test_noctusai_home_env_wins_over_worktree_unwrap(self, tmp_path, monkeypatch):
        explicit = tmp_path / "explicit-home"
        explicit.mkdir()
        monkeypatch.setenv("NOCTUSAI_HOME", str(explicit))
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        wt.mkdir(parents=True)
        assert workspace.get_ledger_root(wt) == explicit.resolve()

    def test_invalid_env_falls_through_to_worktree_unwrap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUSAI_HOME", str(tmp_path / "does-not-exist"))
        primary = tmp_path / "noctusai"
        wt = primary / ".claude" / "worktrees" / "my-slice"
        wt.mkdir(parents=True)
        assert workspace.get_ledger_root(wt) == primary.resolve()


def test_get_ledger_root_exported():
    assert "get_ledger_root" in workspace.__all__
