"""Regression tests for unified_query — cross-cache semantic search."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import unified_query as uq  # noqa: E402


class TestValidation:
    def test_empty_query_rejected(self):
        r = uq.query("")
        assert r["ok"] is False
        assert "empty" in r["error"].lower()

    def test_invalid_source_rejected(self):
        r = uq.query("anything", sources=["not-a-cache"])
        assert r["ok"] is False
        assert "unknown sources" in r["error"]


class TestNormalize:
    def test_kb_score_clamped(self):
        assert uq._normalize_score(0.5, "kb-embeddings") == 0.5
        assert uq._normalize_score(1.5, "kb-embeddings") == 1.0
        assert uq._normalize_score(-0.2, "kb-embeddings") == 0.0


class TestMergeAndRank:
    def test_empty_caches_returns_empty_hits(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: [])
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("anything")
        assert r["ok"] is True
        assert r["hits"] == []

    def test_merges_and_ranks_by_normalized_score(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: [
            {"path": "CONTEXT/foo.md", "chunk_idx": 0, "chunk_text": "...", "score": 0.85},
        ])
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [
            {"path": "mcp/x.py", "symbol_name": "f", "kind": "function", "score": 0.92},
        ])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": [
            {"entry": {"target": "some-target", "status": "s1-emergent"},
             "score": 0.50, "key_overlap": True},
        ]})
        r = uq.query("anything")
        assert r["ok"] is True
        assert len(r["hits"]) == 3
        # Sorted desc by normalized score.
        scores = [h["score"] for h in r["hits"]]
        assert scores == sorted(scores, reverse=True)

    def test_source_filter(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: [
            {"path": "x.md", "chunk_idx": 0, "chunk_text": "...", "score": 0.9}])
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [
            {"path": "y.py", "symbol_name": "g", "kind": "function", "score": 0.9}])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("anything", sources=["kb-embeddings"])
        assert r["ok"] is True
        for h in r["hits"]:
            assert h["source"] == "kb-embeddings"

    def test_top_k_caps_result(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        many_kb = [{"path": f"a{i}.md", "chunk_idx": 0, "chunk_text": "...",
                    "score": 0.5 + i*0.01} for i in range(10)]
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: many_kb)
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("anything", top_k=3, per_source_k=10)
        assert len(r["hits"]) == 3

    def test_min_score_filter(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: [
            {"path": "a.md", "chunk_idx": 0, "chunk_text": "...", "score": 0.3},
            {"path": "b.md", "chunk_idx": 0, "chunk_text": "...", "score": 0.8}])
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("anything", min_score=0.5)
        for h in r["hits"]:
            assert h["score"] >= 0.5

    def test_dedupes_identical_summaries(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr
        # Same kb path returned twice from the same cache should dedupe.
        monkeypatch.setattr(kbe, "search", lambda *a, **kw: [
            {"path": "dup.md", "chunk_idx": 0, "chunk_text": "...", "score": 0.8},
            {"path": "dup.md", "chunk_idx": 0, "chunk_text": "...", "score": 0.7}])
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("anything")
        summaries = [h["summary"] for h in r["hits"]]
        assert len(summaries) == len(set(summaries))


class TestGracefulDegrade:
    def test_source_error_doesnt_crash(self, monkeypatch):
        from tools.noctus.dev import kb_embeddings as kbe
        from tools.noctus.dev import code_embeddings as ce
        from tools.noctus.dev import kb_recurrence_radar as krr

        def _boom(*a, **kw):
            raise RuntimeError("synthetic")

        monkeypatch.setattr(kbe, "search", _boom)
        monkeypatch.setattr(ce, "search", lambda *a, **kw: [])
        monkeypatch.setattr(krr, "consult", lambda **kw: {"ok": True, "hits": []})
        r = uq.query("anything")
        assert r["ok"] is True  # other sources still return
        assert any("kb-embeddings" in w for w in r["warnings"])
