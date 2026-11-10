"""Search over the embedding caches must fail LOUD when the query cannot be
embedded (OpenAI quota exhausted, auth, network) — never return `[]`, which
reads as "no memories / no KB hits" (CLAUDE.md §1 "No silent errors").

Uses the modules' own embed seams (`_ec.embed_sync`, `kbe._embed_sync`) — the
same ones the sibling embedding tests use; no guard is patched.
"""
from __future__ import annotations

import pytest

from tools.noctus.dev import _embedding_corpus as _ec
from tools.noctus.dev import code_embeddings as ce
from tools.noctus.dev import corpus_embeddings as cee
from tools.noctus.dev import kb_embeddings as kbe
from tools.noctus.dev import memory_embeddings as mee


def _quota(_text):
    raise RuntimeError("429 insufficient_quota: credit_balance_exhausted")


def _good(_text):
    return [0.1] * 1536


@pytest.fixture
def cache_files(tmp_path, monkeypatch):
    """Real (empty-initialised) cache files so the search passes the
    'cache exists' short-circuit and reaches the embedding step."""
    for mod in (mee, cee, kbe, ce):
        path = tmp_path / f"{mod.__name__.rsplit('.', 1)[-1]}.sqlite"
        path.touch()
        monkeypatch.setattr(mod, "CACHE_PATH", path)
    monkeypatch.setattr(mee._CORPUS, "cache_path", mee.CACHE_PATH, raising=False)
    monkeypatch.setattr(cee._CORPUS, "cache_path", cee.CACHE_PATH, raising=False)


def _expected(exc):
    assert exc.to_error() == {
        "ok": False,
        "error": "embedding_unavailable",
        "provider_error": "insufficient_quota",
        "fallback": "grep memory/KB/project-history",
    }


class TestEmbeddingFailureIsTyped:
    def test_memory_search_raises_typed(self, cache_files, monkeypatch):
        monkeypatch.setattr(_ec, "embed_sync", _quota)
        with pytest.raises(_ec.EmbeddingUnavailable) as ei:
            mee.search("x")
        _expected(ei.value)

    def test_corpus_search_raises_typed(self, cache_files, monkeypatch):
        monkeypatch.setattr(_ec, "embed_sync", _quota)
        with pytest.raises(_ec.EmbeddingUnavailable):
            cee.search("x")

    def test_kb_search_raises_typed(self, cache_files, monkeypatch):
        monkeypatch.setattr(kbe, "_embed_sync", _quota)
        with pytest.raises(_ec.EmbeddingUnavailable) as ei:
            kbe.search("x")
        _expected(ei.value)

    def test_code_search_raises_typed(self, cache_files, monkeypatch):
        monkeypatch.setattr(ce, "_embed_sync", _quota)
        with pytest.raises(_ec.EmbeddingUnavailable):
            ce.search("x")

    def test_empty_vector_is_unavailable(self, cache_files, monkeypatch):
        monkeypatch.setattr(_ec, "embed_sync", lambda _t: [])
        with pytest.raises(_ec.EmbeddingUnavailable):
            mee.search("x")

    def test_mcp_boundary_returns_error_dict(self, cache_files, monkeypatch):
        monkeypatch.setattr(_ec, "embed_sync", _quota)
        out = _ec.guarded_search(mee.search, "x")
        assert out["ok"] is False and out["error"] == "embedding_unavailable"


class TestHealthyEmbedEmptyResultStaysEmptyList:
    def test_memory_no_hits_is_empty_list(self, cache_files, monkeypatch):
        monkeypatch.setattr(_ec, "embed_sync", _good)
        assert _ec.guarded_search(mee.search, "x") == []

    def test_kb_no_hits_is_empty_list(self, cache_files, monkeypatch):
        monkeypatch.setattr(kbe, "_embed_sync", _good)
        assert _ec.guarded_search(kbe.search, "x") == []

    def test_missing_cache_is_empty_list_not_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(kbe, "CACHE_PATH", tmp_path / "absent.sqlite")
        assert kbe.search("x") == []
