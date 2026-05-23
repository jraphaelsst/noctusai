"""Tests for the vector/KB seam (integrations/vectors/).

Strategy: FakeVectorStore only — no network, no Supabase, no OpenAI.

Covers:
  - KBChunk + KBHit dataclasses.
  - FakeVectorStore.upsert returns correct count; len() reflects state.
  - FakeVectorStore.query returns results ranked by cosine similarity.
  - FakeVectorStore.query respects k limit.
  - Upsert is idempotent (duplicate id overwrites, count stays correct).
  - make_vector_store(use_fake=True) returns FakeVectorStore.
  - make_vector_store() without credentials raises VectorStoreNotConfigured.
  - Cosine similarity: identical vectors → 1.0; orthogonal → 0.0; zero vector → 0.0.
"""
from __future__ import annotations

import math
import pytest

from app.integrations.vectors.fake import FakeVectorStore
from app.integrations.vectors.factory import VectorStoreNotConfigured, make_vector_store
from app.integrations.vectors.types import KBChunk, KBHit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit(dims: int, hot: int) -> list[float]:
    """One-hot unit vector of length *dims* with a 1 at index *hot*."""
    v = [0.0] * dims
    v[hot] = 1.0
    return v


def _make_chunk(cid: str, module: str = "test-module") -> KBChunk:
    return KBChunk(
        id=cid,
        document_id=f"doc-{cid}",
        content=f"Content of chunk {cid}",
        module=module,
    )


# ---------------------------------------------------------------------------
# KBChunk dataclass
# ---------------------------------------------------------------------------

class TestKBChunk:
    def test_defaults(self) -> None:
        c = KBChunk(id="x", document_id="d", content="text", module="m")
        assert c.confidence == 1.0

    def test_confidence_bounds(self) -> None:
        # valid extremes
        KBChunk(id="a", document_id="d", content="t", module="m", confidence=0.0)
        KBChunk(id="b", document_id="d", content="t", module="m", confidence=1.0)

    def test_confidence_invalid(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            KBChunk(id="c", document_id="d", content="t", module="m", confidence=1.1)


# ---------------------------------------------------------------------------
# FakeVectorStore — upsert
# ---------------------------------------------------------------------------

class TestFakeVectorStoreUpsert:
    @pytest.mark.asyncio
    async def test_upsert_returns_count(self) -> None:
        store = FakeVectorStore()
        chunks = [(_make_chunk("c1"), _unit(4, 0)), (_make_chunk("c2"), _unit(4, 1))]
        written = await store.upsert(chunks)
        assert written == 2

    @pytest.mark.asyncio
    async def test_upsert_persists(self) -> None:
        store = FakeVectorStore()
        await store.upsert([(_make_chunk("c1"), _unit(4, 0))])
        assert len(store) == 1
        assert "c1" in store.stored_ids()

    @pytest.mark.asyncio
    async def test_upsert_empty(self) -> None:
        store = FakeVectorStore()
        written = await store.upsert([])
        assert written == 0
        assert len(store) == 0

    @pytest.mark.asyncio
    async def test_upsert_idempotent(self) -> None:
        """Same id upserted twice should not grow the store."""
        store = FakeVectorStore()
        chunk = _make_chunk("c1")
        await store.upsert([(chunk, _unit(4, 0))])
        await store.upsert([(chunk, _unit(4, 1))])  # same id, new embedding
        assert len(store) == 1
        # The new embedding should be reflected in subsequent queries
        hits = await store.query(_unit(4, 1), k=1)
        assert len(hits) == 1
        assert math.isclose(hits[0].score, 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# FakeVectorStore — query
# ---------------------------------------------------------------------------

class TestFakeVectorStoreQuery:
    @pytest.mark.asyncio
    async def test_query_empty_store(self) -> None:
        store = FakeVectorStore()
        hits = await store.query(_unit(4, 0), k=5)
        assert hits == []

    @pytest.mark.asyncio
    async def test_query_returns_kbhit(self) -> None:
        store = FakeVectorStore()
        chunk = _make_chunk("c1")
        await store.upsert([(chunk, _unit(4, 0))])
        hits = await store.query(_unit(4, 0), k=5)
        assert len(hits) == 1
        assert isinstance(hits[0], KBHit)
        assert hits[0].chunk is chunk or hits[0].chunk.id == "c1"

    @pytest.mark.asyncio
    async def test_query_ranked_by_similarity(self) -> None:
        """Best-matching chunk should be first."""
        store = FakeVectorStore()
        # c_exact: identical to query → similarity = 1.0
        c_exact = _make_chunk("exact")
        # c_ortho: orthogonal → similarity = 0.0
        c_ortho = _make_chunk("ortho")
        await store.upsert([
            (c_exact, _unit(4, 0)),
            (c_ortho, _unit(4, 1)),
        ])
        hits = await store.query(_unit(4, 0), k=5)
        assert hits[0].chunk.id == "exact"
        assert math.isclose(hits[0].score, 1.0, abs_tol=1e-9)
        assert math.isclose(hits[1].score, 0.0, abs_tol=1e-9)

    @pytest.mark.asyncio
    async def test_query_respects_k(self) -> None:
        store = FakeVectorStore()
        for i in range(10):
            chunk = _make_chunk(f"c{i}")
            emb = [float(i == j) for j in range(10)]  # one-hot 10-dim
            await store.upsert([(chunk, emb)])
        hits = await store.query([1.0] + [0.0] * 9, k=3)
        assert len(hits) <= 3

    @pytest.mark.asyncio
    async def test_query_zero_vector(self) -> None:
        """Zero query vector should return 0.0 similarity for all chunks."""
        store = FakeVectorStore()
        await store.upsert([(_make_chunk("c1"), _unit(4, 0))])
        zero = [0.0, 0.0, 0.0, 0.0]
        hits = await store.query(zero, k=5)
        assert math.isclose(hits[0].score, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Cosine similarity edge cases (via _cosine helper)
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical(self) -> None:
        from app.integrations.vectors.fake import _cosine
        v = [1.0, 0.0, 1.0]
        assert math.isclose(_cosine(v, v), 1.0, abs_tol=1e-9)

    def test_orthogonal(self) -> None:
        from app.integrations.vectors.fake import _cosine
        assert math.isclose(_cosine([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)

    def test_zero_vector(self) -> None:
        from app.integrations.vectors.fake import _cosine
        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_use_fake_returns_fake(self) -> None:
        store = make_vector_store(use_fake=True)
        assert isinstance(store, FakeVectorStore)

    def test_no_credentials_raises(self) -> None:
        """Production path without credentials must raise loudly, not silently degrade."""
        with pytest.raises(VectorStoreNotConfigured):
            make_vector_store(url="", service_role_key="")
