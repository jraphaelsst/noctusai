"""In-memory vector store for dev/tests.

Uses pure-Python cosine similarity — no numpy, no network, no Supabase.
All state is instance-local; create a fresh ``FakeVectorStore()`` per test.

Mirrors the pattern of ``FakeDriveDownloader``:
  - ``add_chunk(chunk, embedding)`` — seed fixture data.
  - ``upsert(...)`` / ``query(...)`` — satisfy the VectorStore protocol.
"""
from __future__ import annotations

import asyncio
import math

from app.integrations.vectors.types import KBChunk, KBHit


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors.  Returns 0.0 if either is zero."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class FakeVectorStore:
    """In-memory VectorStore.  No network, no credentials."""

    def __init__(self) -> None:
        # chunk_id -> (KBChunk, embedding)
        self._store: dict[str, tuple[KBChunk, list[float]]] = {}

    # ── seeding helper (tests) ────────────────────────────────────────────────

    def add_chunk(self, chunk: KBChunk, embedding: list[float]) -> None:
        """Pre-seed a chunk (equivalent to calling upsert synchronously)."""
        self._store[chunk.id] = (chunk, embedding)

    # ── VectorStore protocol ──────────────────────────────────────────────────

    async def upsert(
        self,
        chunks: list[tuple[KBChunk, list[float]]],
    ) -> int:
        """Upsert (chunk, embedding) pairs by chunk.id; return count written."""
        await asyncio.sleep(0)
        for chunk, embedding in chunks:
            self._store[chunk.id] = (chunk, embedding)
        return len(chunks)

    async def query(
        self,
        embedding: list[float],
        k: int = 5,
    ) -> list[KBHit]:
        """Return the top-k most-similar chunks by cosine similarity."""
        await asyncio.sleep(0)
        scored: list[KBHit] = []
        for chunk, stored_emb in self._store.values():
            score = _cosine(embedding, stored_emb)
            scored.append(KBHit(chunk=chunk, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]

    # ── introspection (tests) ─────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._store)

    def stored_ids(self) -> set[str]:
        """Return the set of chunk ids currently in the store."""
        return set(self._store)


__all__ = ["FakeVectorStore"]
