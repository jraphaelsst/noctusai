"""Tests for `worktree_path` threading through `refresh_all_caches.py`.

MCP stdio is a fixed-CWD process bound to the primary tree at startup. The
structural cache refresh entry points (keeper-patterns / agent-context /
auto-improvement / noc-graph) already had — or now have — an explicit
`worktree_path` param on their own `refresh()`; this file pins that the
ORCHESTRATOR (`refresh_all` / `detect_stale_caches` / `settle_structural_caches`)
actually threads it down rather than silently defaulting every sub-cache back
to the primary. KB § PATTERNS/common/cache-auto-freshness.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.noctus.dev.refresh_all_caches as rac  # noqa: E402


def _fake_worktree(tmp_path: Path) -> Path:
    """`resolve_caller_root` only checks EXISTENCE of `.git` + the marker
    file — no real git init needed."""
    wt = tmp_path / "wt"
    wt.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: /nowhere\n")
    (wt / ".noctusai-workspace").write_text("test\n")
    return wt


class TestResolveEffectiveRoot:
    def test_no_worktree_path_returns_repo_root_unchanged(self, tmp_path):
        assert rac._resolve_effective_root(tmp_path, None) == tmp_path

    def test_worktree_path_takes_precedence_over_repo_root(self, tmp_path):
        wt = _fake_worktree(tmp_path)
        other = tmp_path / "unrelated"
        other.mkdir()
        assert rac._resolve_effective_root(other, str(wt)) == wt

    def test_worktree_path_rejects_non_worktree_dir(self, tmp_path):
        bogus = tmp_path / "not-a-worktree"
        bogus.mkdir()
        with pytest.raises(ValueError):
            rac._resolve_effective_root(None, str(bogus))


class TestRefreshAllThreadsWorktreePath:
    """Each of the 4 STRUCTURAL sub-cache refreshes must receive the SAME
    `worktree_path` passed to `refresh_all` — the embedding caches (kb/code)
    are explicitly out of scope and stay unaffected."""

    def test_keeper_patterns_agent_context_auto_improvement_noc_graph_receive_it(
        self, monkeypatch,
    ):
        seen: dict[str, dict] = {}

        def _mk(name):
            def _refresh(**kw):
                seen[name] = kw
                return {"ok": True, "status": "in-sync", "rows_written": 0}
            return _refresh

        import tools.noctus.dev.keeper_pattern_cache as kpc
        import tools.noctus.dev.agent_context_cache as acc
        import tools.noctus.dev.auto_improvement as ai
        import tools.noctus.dev.noc_graph_cache as ng

        monkeypatch.setattr(kpc, "refresh", _mk("keeper-patterns"))
        monkeypatch.setattr(acc, "refresh", _mk("agent-context"))
        monkeypatch.setattr(ai, "refresh", _mk("auto-improvement"))
        monkeypatch.setattr(ng, "refresh", _mk("noc-graph"))

        result = rac.refresh_all(
            only=["keeper-patterns", "agent-context", "auto-improvement", "noc-graph"],
            worktree_path="/fake/wt",
        )
        assert result["ok"] is True
        for name in ("keeper-patterns", "agent-context", "auto-improvement", "noc-graph"):
            assert seen[name].get("worktree_path") == "/fake/wt", (
                f"{name}.refresh() did not receive worktree_path: {seen[name]!r}")

    def test_omitted_worktree_path_defaults_to_none_for_every_sub_cache(
        self, monkeypatch,
    ):
        seen: dict[str, dict] = {}

        def _mk(name):
            def _refresh(**kw):
                seen[name] = kw
                return {"ok": True, "status": "in-sync", "rows_written": 0}
            return _refresh

        import tools.noctus.dev.keeper_pattern_cache as kpc
        import tools.noctus.dev.agent_context_cache as acc
        import tools.noctus.dev.auto_improvement as ai
        import tools.noctus.dev.noc_graph_cache as ng

        monkeypatch.setattr(kpc, "refresh", _mk("keeper-patterns"))
        monkeypatch.setattr(acc, "refresh", _mk("agent-context"))
        monkeypatch.setattr(ai, "refresh", _mk("auto-improvement"))
        monkeypatch.setattr(ng, "refresh", _mk("noc-graph"))

        rac.refresh_all(
            only=["keeper-patterns", "agent-context", "auto-improvement", "noc-graph"],
        )
        for name in ("keeper-patterns", "agent-context", "auto-improvement", "noc-graph"):
            assert seen[name].get("worktree_path") is None


class TestSettleStructuralCachesThreadsWorktreePath:
    def test_worktree_path_flows_to_detect_and_refresh(self, tmp_path, monkeypatch):
        wt = _fake_worktree(tmp_path)
        detect_calls = []
        refresh_calls = []

        monkeypatch.setattr(
            rac, "detect_stale_caches",
            lambda root=None: detect_calls.append(root) or ["noc-graph"],
        )
        monkeypatch.setattr(
            rac, "refresh_all",
            lambda **kw: refresh_calls.append(kw) or {"ok": True, "failures": []},
        )

        result = rac.settle_structural_caches(worktree_path=str(wt))
        assert result["ok"] is True
        assert result["healed"] == ["noc-graph"]
        # detect_stale_caches got the RESOLVED worktree root, not the raw string.
        assert detect_calls == [wt]
        assert refresh_calls == [{"only": ["noc-graph"], "worktree_path": str(wt)}]

    def test_no_worktree_path_keeps_the_pre_existing_call_shape(self, monkeypatch):
        """Regression guard: omitting `worktree_path` must not inject a
        `worktree_path=None` kwarg into `refresh_all` — the existing
        `test_settle_structural_caches.py` mocks assert on the EXACT kwarg
        dict and would break under a silently-added always-present key."""
        refresh_calls = []
        monkeypatch.setattr(rac, "detect_stale_caches", lambda root=None: ["noc-graph"])
        monkeypatch.setattr(
            rac, "refresh_all",
            lambda **kw: refresh_calls.append(kw) or {"ok": True, "failures": []},
        )
        rac.settle_structural_caches()
        assert refresh_calls == [{"only": ["noc-graph"]}]
