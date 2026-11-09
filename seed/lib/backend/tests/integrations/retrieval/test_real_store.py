"""SupabaseRetrievalStore: RPC names/params, vector width guard, error typing."""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.retrieval import (
    EMBEDDING_DIMENSIONS,
    Chunk,
    EmbeddedChunk,
    RetrievalError,
    SupabaseRetrievalStore,
    make_retrieval_store,
)

VEC = [0.5] * EMBEDDING_DIMENSIONS


class _Rpc:
    def __init__(self, data, boom=False):
        self.data, self.boom = data, boom

    def execute(self):
        if self.boom:
            raise ConnectionError("net")
        return type("R", (), {"data": self.data})()


class _Client:
    def __init__(self, data=None, boom=False):
        self.calls, self._data, self._boom = [], data, boom

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _Rpc(self._data, self._boom)


def test_search_maps_rows_and_scopes_the_call():
    c = _Client([{"chunk_position": 2, "heading": "H", "content": "C", "score": 0.9}])
    hits = SupabaseRetrievalStore(lambda: c).search(
        namespace="ns", org_id="org", embedding=VEC, k=3, min_score=0.4
    )
    name, params = c.calls[0]
    assert name == "retrieval_match_chunks"
    assert params["p_org_id"] == "org" and params["p_namespace"] == "ns"
    assert params["p_query"].startswith("[") and (params["p_k"], params["p_min_score"]) == (3, 0.4)
    assert (hits[0].position, hits[0].score) == (2, 0.9)


def test_replace_corpus_sends_one_atomic_rpc():
    c = _Client(1)
    ch = EmbeddedChunk(Chunk("H", "body", 0, "h"), VEC)
    assert SupabaseRetrievalStore(lambda: c).replace_corpus(
        namespace="ns", org_id=None, source_hash="s", chunks=[ch]
    ) == 1
    assert [n for n, _ in c.calls] == ["retrieval_replace_corpus"]
    assert c.calls[0][1]["p_org_id"] is None and c.calls[0][1]["p_chunks"][0]["chunk_position"] == 0


def test_wrong_vector_width_is_refused_before_any_rpc():
    c = _Client([])
    with pytest.raises(RetrievalError, match="width"):
        SupabaseRetrievalStore(lambda: c).search(
            namespace="ns", org_id=None, embedding=[0.1, 0.2], k=1, min_score=0.0
        )
    assert c.calls == []


def test_cache_lookup_none_when_no_rows_and_purge_returns_count():
    s = SupabaseRetrievalStore(lambda: _Client([]))
    assert s.cache_lookup(namespace="n", org_id=None, prompt_version="v", embedding=VEC, min_score=0.9) is None
    assert SupabaseRetrievalStore(lambda: _Client(7)).purge_org(org_id="o") == 7


def test_transport_failure_is_typed_with_cause_chained():
    with pytest.raises(RetrievalError) as ei:
        SupabaseRetrievalStore(lambda: _Client(boom=True)).corpus_hash(namespace="n", org_id=None)
    assert isinstance(ei.value.__cause__, ConnectionError)


def test_factory_requires_a_client_factory():
    with pytest.raises(ValueError):
        make_retrieval_store(None)
