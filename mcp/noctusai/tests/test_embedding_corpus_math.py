"""Unit tests for the canonical cosine + top_k_similar helpers in _embedding_corpus.

These are the authoritative math tests for the N=7 consolidation of cosine
similarity across the platform. All consumer modules now delegate to
``_embedding_corpus.cosine`` and ``_embedding_corpus.top_k_similar`` — if
these pass, the consumers' math is correct by construction.

KB § PATTERNS/common/vectorize-embed-cache-framework.md
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev._embedding_corpus import cosine, top_k_similar  # noqa: E402


# ── cosine ────────────────────────────────────────────────────────────────────


class TestCosine:
    """Canonical cosine similarity tests — drives consumer correctness."""

    def test_identical_vectors_score_one(self):
        v = [1.0, 0.0, 0.0]
        assert cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_score_minus_one(self):
        assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_guard_returns_zero(self):
        """Either vector being all-zero → 0.0 (not NaN / division error)."""
        assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert cosine([1.0, 1.0], [0.0, 0.0]) == 0.0
        assert cosine([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_empty_vectors_return_zero(self):
        """Empty lists handled gracefully — zip short-circuits, na/nb stay 0."""
        assert cosine([], []) == 0.0

    def test_positive_partial_similarity(self):
        """45-degree angle → cos(45°) ≈ 0.707."""
        v1 = [1.0, 0.0]
        v2 = [1.0, 1.0]
        expected = 1.0 / math.sqrt(2)
        assert cosine(v1, v2) == pytest.approx(expected, abs=1e-9)

    def test_high_dimensional_unit_vector(self):
        """1536-D unit vector along axis 0 vs unit vector along axis 1 → 0."""
        dim = 1536
        a = [1.0] + [0.0] * (dim - 1)
        b = [0.0, 1.0] + [0.0] * (dim - 2)
        assert cosine(a, b) == pytest.approx(0.0)

    def test_symmetry(self):
        """cosine(a, b) == cosine(b, a)."""
        a = [0.3, 0.5, -0.2]
        b = [0.1, 0.8, 0.4]
        assert cosine(a, b) == pytest.approx(cosine(b, a))

    def test_returns_float(self):
        assert isinstance(cosine([1.0], [1.0]), float)


# ── top_k_similar ─────────────────────────────────────────────────────────────


class TestTopKSimilar:
    """Ranking helper tests."""

    def _make_candidates(self, vecs_and_items):
        """Helper: zip (vec, item) list into the expected iterable shape."""
        return list(vecs_and_items)

    def test_ranking_order_highest_first(self):
        """Results must be sorted by score descending."""
        q = [1.0, 0.0]
        candidates = [
            ([0.0, 1.0], "orthogonal"),       # score ≈ 0.0
            ([1.0, 0.0], "identical"),         # score = 1.0
            ([1.0, 1.0], "partial"),           # score ≈ 0.707
        ]
        results = top_k_similar(q, candidates, k=3)
        scores = [s for s, _ in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0][1] == "identical"
        assert results[1][1] == "partial"
        assert results[2][1] == "orthogonal"

    def test_k_limit_respected(self):
        """At most k results are returned even with more candidates."""
        q = [1.0, 0.0]
        candidates = [([1.0, float(i)] , f"item-{i}") for i in range(10)]
        results = top_k_similar(q, candidates, k=3)
        assert len(results) <= 3

    def test_min_score_filters_out_low_scores(self):
        """Pairs below min_score are excluded."""
        q = [1.0, 0.0]
        candidates = [
            ([0.0, 1.0], "orthogonal"),  # score ≈ 0.0 → below 0.5
            ([1.0, 0.0], "identical"),   # score = 1.0 → kept
        ]
        results = top_k_similar(q, candidates, k=5, min_score=0.5)
        items = [item for _, item in results]
        assert "identical" in items
        assert "orthogonal" not in items

    def test_empty_candidates_returns_empty(self):
        results = top_k_similar([1.0, 0.0], [], k=5)
        assert results == []

    def test_zero_query_vector_all_zero_scores(self):
        """Zero query → cosine returns 0 for all → all filtered by default min_score=0."""
        q = [0.0, 0.0]
        candidates = [([1.0, 0.0], "a"), ([0.0, 1.0], "b")]
        # min_score=0.0 → score >= 0.0 → both included (score == 0.0 exactly)
        results = top_k_similar(q, candidates, k=5, min_score=0.0)
        assert len(results) == 2
        assert all(s == 0.0 for s, _ in results)

    def test_items_passed_through_opaque(self):
        """The item payload is returned as-is (dict, string, int, etc.)."""
        q = [1.0, 0.0]
        payload = {"nested": {"data": [1, 2, 3]}, "score": None}
        candidates = [([1.0, 0.0], payload)]
        results = top_k_similar(q, candidates, k=1)
        assert results[0][1] is payload

    def test_returns_tuples_of_float_and_item(self):
        q = [1.0, 0.0]
        results = top_k_similar(q, [([1.0, 0.0], "x")], k=1)
        score, item = results[0]
        assert isinstance(score, float)
        assert item == "x"

    def test_default_min_score_is_zero(self):
        """Negative scores (obtuse angle) are excluded by the default min_score=0."""
        q = [1.0, 0.0]
        candidates = [
            ([-1.0, 0.0], "opposite"),  # score = -1.0 → below default 0.0
            ([1.0, 0.0], "identical"),  # score = 1.0 → included
        ]
        results = top_k_similar(q, candidates, k=5)
        items = [item for _, item in results]
        assert "identical" in items
        assert "opposite" not in items


# ── Consumer alias integrity ──────────────────────────────────────────────────


class TestConsumerAliasIntegrity:
    """Verify all six consumer modules alias cosine to the canonical _ec.cosine."""

    def _import_module(self, module_path: str):
        """Import a tools.noctus.dev module from the mcp package."""
        import importlib
        return importlib.import_module(f"tools.noctus.dev.{module_path}")

    def test_codification_radar_alias(self):
        mod = self._import_module("codification_radar")
        assert mod._cosine is cosine, \
            "codification_radar._cosine must alias _embedding_corpus.cosine"

    def test_doc_to_code_drift_alias(self):
        mod = self._import_module("doc_to_code_drift")
        assert mod._cosine is cosine, \
            "doc_to_code_drift._cosine must alias _embedding_corpus.cosine"

    def test_brief_similarity_radar_alias(self):
        mod = self._import_module("brief_similarity_radar")
        assert mod._cosine is cosine, \
            "brief_similarity_radar._cosine must alias _embedding_corpus.cosine"

    def test_kb_recurrence_radar_alias(self):
        mod = self._import_module("kb_recurrence_radar")
        assert mod._cosine is cosine, \
            "kb_recurrence_radar._cosine must alias _embedding_corpus.cosine"

    def test_product_centroid_drift_alias(self):
        mod = self._import_module("product_centroid_drift")
        assert mod._cosine is cosine, \
            "product_centroid_drift._cosine must alias _embedding_corpus.cosine"

    def test_engineer_brief_compose_alias(self):
        mod = self._import_module("engineer_brief_compose")
        assert mod._cosine is cosine, \
            "engineer_brief_compose._cosine must alias _embedding_corpus.cosine"
