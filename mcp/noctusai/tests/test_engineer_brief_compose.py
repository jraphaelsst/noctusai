"""Tests for noctus.dev.engineer_brief_compose.

Every cache source is an injectable parameter of ``compose_brief`` /
``_recent_misses`` — the tests pass fakes; nothing patches this module
(``check_no_self_monkeypatch``).

Acceptance gates:
  - Brief dict shape (all six keys present).
  - Brief text contains required sections.
  - Graceful-degrade when caches raise ImportError or return empties.
  - Agent is auto-routed when not supplied; honoured when supplied.
  - _cosine and _centroid helpers produce correct values.
  - "Your recent misses" block: rendered, absent when empty, deduped +
    bounded, and every swallowed failure reported in ``degraded``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.engineer_brief_compose import (
    _centroid,
    _cosine,
    _query_auto_improvement,
    _recent_misses,
    compose_brief,
)


# ── Unit helpers ─────────────────────────────────────────────────────────────
class TestCosine:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_safe(self):
        # Should not raise; returns 0.0 when either vector is zero.
        assert _cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


class TestCentroid:
    def test_single_vector(self):
        v = [1.0, 2.0, 3.0]
        assert _centroid([v]) == pytest.approx(v)

    def test_two_vectors(self):
        result = _centroid([[1.0, 0.0], [0.0, 1.0]])
        assert result == pytest.approx([0.5, 0.5])

    def test_empty_returns_empty(self):
        assert _centroid([]) == []


# ── Integration: compose_brief ────────────────────────────────────────────────
_STUB_FILES = [
    "mcp/noctusai/tools/noctus/dev/engineer_brief_compose.py",
    "mcp/noctusai/cli.py",
]
_STUB_DESC = "Add engineer_brief_compose MCP tool with cache enrichment"


def _no_embed(text: str) -> dict:
    return {"ok": False, "error": "provider offline (test)"}


def _empty_query(**kw: Any) -> list[dict]:
    return []


def _empty_kb(description: str, top_k: int = 3) -> list[dict]:
    return []


def _no_rows() -> list[dict]:
    return []


def _compose(**over: Any) -> dict:
    """compose_brief with every cache source injected as an empty fake."""
    kw: dict[str, Any] = dict(
        target_files=_STUB_FILES,
        description=_STUB_DESC,
        embed_text=_no_embed,
        ai_query=_empty_query,
        kb_search=_empty_kb,
        pick_agent=lambda vec: "backend-engineer",
        score_rows=_no_rows,
    )
    kw.update(over)
    return compose_brief(**kw)


class TestComposeBriefShape:
    """Verify the output dict has the right shape in all cache states."""

    def test_returns_eight_keys(self):
        result = _compose()
        assert set(result.keys()) == {
            "brief", "suggested_agent", "auto_improvement_context",
            "kb_references", "recent_misses", "open_findings", "source_warnings", "degraded",
        }

    def test_brief_contains_required_sections(self):
        brief = _compose()["brief"]
        assert "## Engineer Brief" in brief
        assert "### Goal" in brief
        assert "### Reference" in brief
        assert "### Scope" in brief
        assert "### Acceptance" in brief
        assert "Leg 1" in brief
        assert "Leg 2" in brief

    def test_scope_contains_target_files(self):
        brief = _compose()["brief"]
        for tf in _STUB_FILES:
            assert tf in brief

    def test_agent_in_brief_footer(self):
        assert "backend-engineer" in _compose()["brief"]


class TestGracefulDegrade:
    """When caches are unavailable the tool degrades — and says so."""

    def test_empty_kb_references_when_search_raises(self):
        def _boom(description: str, top_k: int = 3) -> list[dict]:
            raise RuntimeError("kb cache missing")

        result = _compose(kb_search=_boom)
        assert result["kb_references"] == []
        assert "KB embeddings cache empty" in result["brief"]
        assert any(d.startswith("kb-embeddings: RuntimeError") for d in result["degraded"])

    def test_empty_ai_context_on_no_ledger(self):
        assert _compose()["auto_improvement_context"] == []

    def test_unreachable_embedding_is_reported(self):
        result = _compose()
        assert "embedding: provider offline (test)" in result["degraded"]

    def test_fallback_agent_when_no_embedding(self):
        """Empty embedding + live _pick_agent ⇒ fallback agent, reason reported."""
        result = _compose(pick_agent=None)
        assert result["suggested_agent"] == "backend-engineer"
        assert any(d.startswith("agent-routing: no query embedding") for d in result["degraded"])

    def test_no_exception_when_all_caches_absent(self):
        """No ImportError should bubble up — all cache queries are guarded;
        compose_brief always returns a brief + a valid agent slug.

        The SPECIFIC routing winner is semantic-corpus-dependent (it shifts as
        owned-KB centroids evolve) and is NOT what this test guards — the
        forced-fallback agent (backend-engineer) is asserted deterministically
        by ``test_fallback_agent_when_no_embedding``. Pinning a live winner here
        made the test brittle (it flipped when an architect-owned KB doc grew).
        """
        result = compose_brief(target_files=_STUB_FILES, description=_STUB_DESC)
        assert "brief" in result
        assert isinstance(result["suggested_agent"], str) and result["suggested_agent"]
        assert isinstance(result["degraded"], list)


class TestAgentRouting:
    def test_pinned_agent_honoured(self):
        """When `agent` is provided it is used verbatim without picking."""
        def _never(vec: list[float]) -> str:
            raise AssertionError("pick_agent must not run when agent is pinned")

        result = _compose(agent="frontend-engineer", pick_agent=_never)
        assert result["suggested_agent"] == "frontend-engineer"
        assert "frontend-engineer" in result["brief"]

    def test_auto_route_receives_the_query_vector(self):
        """The picker seam gets the embedding of the description."""
        query_vec = [1.0, 0.0, 0.0]
        seen: list[list[float]] = []

        def _pick(vec: list[float]) -> str:
            seen.append(vec)
            return "backend-engineer"

        result = _compose(
            embed_text=lambda t: {"ok": True, "vector": query_vec},
            pick_agent=_pick,
        )
        assert result["suggested_agent"] == "backend-engineer"
        assert seen == [query_vec]

    def test_pick_agent_cosine_logic_directly(self):
        """Directly exercise _pick_agent's cosine selection without live cache deps.

        Injects a stub for the internal _load_all_chunk_vectors + agent_context
        functions by replacing them inside the engineer_brief_compose module
        namespace (no cross-module import needed — the guards in _pick_agent
        use try/import, so we stub at the function level via a sub-import mock).
        """
        from tools.noctus.dev import engineer_brief_compose as ebc

        query_vec = [1.0, 0.0, 0.0]
        fake_rows: list[Any] = [
            ("PATTERNS/backend.md", 0, "chunk", [0.9, 0.1, 0.0]),
            ("PATTERNS/frontend.md", 0, "chunk", [0.0, 0.9, 0.1]),
        ]
        fake_backend_bundle = {
            "ok": True,
            "owned_kb": [{"path": "PATTERNS/backend.md", "extract": ""}],
        }
        fake_frontend_bundle = {
            "ok": True,
            "owned_kb": [{"path": "PATTERNS/frontend.md", "extract": ""}],
        }

        def _fake_lookup(name: str) -> dict:
            return fake_backend_bundle if name == "backend-engineer" else fake_frontend_bundle

        # Build a fake module for agent_context_cache.
        fake_acc = MagicMock()
        fake_acc.list_agents.return_value = ["backend-engineer", "frontend-engineer"]
        fake_acc.lookup.side_effect = _fake_lookup

        # Build a fake module for kb_embeddings.
        fake_kbe = MagicMock()
        fake_kbe._load_all_chunk_vectors.return_value = fake_rows

        # Inject via sys.modules so that `import tools.noctus.dev.agent_context_cache`
        # inside _pick_agent resolves to our fakes.
        sys.modules["tools.noctus.dev.agent_context_cache"] = fake_acc
        sys.modules["tools.noctus.dev.kb_embeddings"] = fake_kbe
        try:
            picked = ebc._pick_agent(query_vec)
        finally:
            sys.modules.pop("tools.noctus.dev.agent_context_cache", None)
            sys.modules.pop("tools.noctus.dev.kb_embeddings", None)

        assert picked == "backend-engineer"


class TestKbReferencesRendered:
    def test_kb_hits_in_brief(self):
        kb_hits = [
            {"path": "PATTERNS/backend.md", "chunk_text": "# Backend patterns", "score": 0.92},
        ]
        result = _compose(kb_search=lambda description, top_k=3: kb_hits)
        assert result["kb_references"] == kb_hits
        assert "PATTERNS/backend.md" in result["brief"]


class TestAutoImprovementRendered:
    def test_ai_context_in_brief(self):
        entry = {
            "ts": "2026-05-26T10:00:00+00:00",
            "kind": "improvement",
            "target": "mcp/noctusai/tools/noctus/dev/engineer_brief_compose.py",
            "description": "Add vector routing for agent selection",
            "status": "s1-emergent",
        }

        def _q(**kw: Any) -> list[dict]:
            return [] if kw.get("agent") else [entry]

        result = _compose(ai_query=_q)
        assert result["auto_improvement_context"] == [entry]
        assert "Auto-improvement context" in result["brief"]
        assert "vector routing" in result["brief"]

    def test_failed_sub_queries_are_reported_not_swallowed(self):
        def _boom(**kw: Any) -> list[dict]:
            raise OSError("ndjson unreadable")

        degraded: list[str] = []
        out = _query_auto_improvement("d", ["a.py"], ai_query=_boom, degraded=degraded)
        assert out == []
        assert degraded == [
            "auto-improvement query(target='a.py'): OSError: ndjson unreadable",
            "auto-improvement query(keyword): OSError: ndjson unreadable",
            "auto-improvement query(recency): OSError: ndjson unreadable",
        ]


# ── Your recent misses (do not repeat) ────────────────────────────────────────
def _ai_row(ts: str, desc: str, kind: str = "drift", target: str = "x.py") -> dict:
    return {"ts": ts, "kind": kind, "target": target, "description": desc, "status": "s1-emergent"}


def _score_row(ts: str, agent: str, **q: float) -> dict:
    full = {k: 4.0 for k in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7")}
    full.update(q)
    return {"ts": ts, "agent": agent, "model": "m", "q": full}


class TestRecentMisses:
    def test_misses_rendered_after_reference(self):
        rows = [_ai_row("2026-11-01T00:00:00+00:00", "ran the full repo suite instead of the scoped test")]

        def _q(**kw: Any) -> list[dict]:
            return rows if kw.get("agent") == "backend-engineer" else []

        scores = [_score_row("2026-11-02T00:00:00+00:00", "backend-engineer", Q3=1.0)]
        result = _compose(ai_query=_q, score_rows=lambda: scores)
        brief = result["brief"]
        assert "### Your recent misses (do not repeat)" in brief
        block = brief.split("### Your recent misses (do not repeat)", 1)[1].split("###", 1)[0]
        assert "ran the full repo suite" in block
        assert "tests scored 1.0/4" in block
        assert brief.index("### Reference") < brief.index("### Your recent misses")
        assert brief.index("### Your recent misses") < brief.index("### Scope")
        # newest first: the rubric miss (11-02) precedes the drift (11-01).
        assert [m["source"] for m in result["recent_misses"]] == ["rubric", "auto-improvement"]

    def test_block_absent_when_no_misses(self):
        result = _compose()
        assert result["recent_misses"] == []
        assert "recent misses" not in result["brief"]

    def test_only_miss_kinds_and_own_rubric_rows(self):
        rows = [
            _ai_row("2026-11-01T00:00:00+00:00", "a drift", kind="drift"),
            _ai_row("2026-11-01T00:00:01+00:00", "a trial obs", kind="trial-obs"),
            _ai_row("2026-11-01T00:00:02+00:00", "a phase lesson", kind="phase-learning"),
        ]
        scores = [
            _score_row("2026-11-03T00:00:00+00:00", "frontend-engineer", Q1=0.0),
            _score_row("2026-11-03T00:00:00+00:00", "backend-engineer"),  # all 4.0 → no miss
        ]
        out = _recent_misses("backend-engineer", ai_query=lambda **kw: rows, score_rows=lambda: scores)
        assert [m["text"] for m in out] == ["a phase lesson", "a drift"]

    def test_dedupe_and_bound(self):
        rows = [
            _ai_row(f"2026-10-{d:02d}T00:00:00+00:00", f"miss number {d}") for d in range(1, 10)
        ] + [
            _ai_row("2026-10-20T00:00:00+00:00", "Same   Miss"),
            _ai_row("2026-10-19T00:00:00+00:00", "same miss"),
        ]
        out = _recent_misses("backend-engineer", limit=3, ai_query=lambda **kw: rows,
                             score_rows=_no_rows)
        assert [m["text"] for m in out] == ["Same   Miss", "miss number 9", "miss number 8"]

    def test_rubric_weakest_first_and_capped(self):
        scores = [_score_row("2026-11-01T00:00:00+00:00", "backend-engineer",
                             Q1=2.5, Q3=1.0, Q6=2.0)]
        out = _recent_misses("backend-engineer", ai_query=_empty_query, score_rows=lambda: scores)
        assert [m["target"] for m in out] == ["Q3 tests", "Q6 methodology"]

    def test_degradation_reported_and_other_leg_survives(self):
        def _boom(**kw: Any) -> list[dict]:
            raise RuntimeError("cache locked")

        scores = [_score_row("2026-11-01T00:00:00+00:00", "backend-engineer", Q2=1.0)]
        result = _compose(ai_query=_boom, score_rows=lambda: scores)
        assert [m["target"] for m in result["recent_misses"]] == ["Q2 design"]
        assert "recent-misses auto-improvement: RuntimeError: cache locked" in result["degraded"]

    def test_score_loader_failure_reported(self):
        def _boom() -> list[dict]:
            raise ValueError("bad ledger")

        result = _compose(score_rows=_boom)
        assert result["recent_misses"] == []
        assert "recent-misses slice-scores: ValueError: bad ledger" in result["degraded"]
        assert "recent misses" not in result["brief"]


# ── 2026-09-22: brief footer follows product-engineer §3/§4 (commit own branch) ──
# `_render_brief` is pure, so these call it directly — no patching needed.

def _rendered(**over) -> str:
    from tools.noctus.dev.engineer_brief_compose import _render_brief
    kw = dict(
        description="Add a bounded pagination helper to the seed data layer",
        target_files=["seed/lib/backend/noctusai_lib/data/paging.py"],
        agent="backend-engineer",
        kb_references=[],
        auto_improvement_context=[],
    )
    kw.update(over)
    return _render_brief(**kw)


class TestBriefFooterContract:
    def test_leg2_says_commit_own_branch_not_stage_only(self):
        brief = _rendered()
        assert "Commit your own worker branch" in brief
        assert "never push" in brief
        assert "Stage-only" not in brief and "no commit" not in brief

    def test_acceptance_is_an_explicit_todo_not_foreign_criteria(self):
        """The composer used to paste ITS OWN acceptance lines into every brief."""
        brief = _rendered()
        acceptance = brief.split("### Acceptance", 1)[1].split("---", 1)[0]
        assert "TODO(architect)" in acceptance
        assert "engineer_brief_compose" not in acceptance
        assert "--compose-brief" not in acceptance


def test_brief_carries_mandatory_before_returning_block():
    from tools.noctus.dev.engineer_brief_compose import BEFORE_RETURNING_BLOCK, _render_brief
    brief = _render_brief(description="d", target_files=["a.py"], agent="backend-engineer",
                          kb_references=[], auto_improvement_context=[])
    assert BEFORE_RETURNING_BLOCK in brief
    assert "--check-doc-staleness --doc-range origin/dev..HEAD" in brief
    assert "FULL suite" in brief


def test_product_engineer_points_at_the_single_source_block():
    text = (Path(__file__).resolve().parents[3] / ".claude/agents/product-engineer.md").read_text()
    assert "BEFORE_RETURNING_BLOCK" in text
