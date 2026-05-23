"""VectorStore protocol — the absorption-stable contract for vector stores.

On absorption: swap the import to `noctusai_lib.integrations.vectors` (or
whatever the seed stabilises the KB seam under). Callers stay unchanged.
"""
from __future__ import annotations

from typing import Protocol

from app.integrations.vectors.types import KBChunk, KBHit


class VectorStore(Protocol):
    """Auth-agnostic, async vector-store contract.

    Both the in-memory fake and the Supabase real adapter implement this
    interface via structural subtyping (no explicit ``implements``).
    """

    async def upsert(
        self,
        chunks: list[tuple[KBChunk, list[float]]],
    ) -> int:
        """Insert or update (by chunk.id) the given (chunk, embedding) pairs.

        Parameters
        ----------
        chunks:
            Sequence of ``(KBChunk, embedding)`` pairs.  If a chunk with the
            same ``id`` already exists it is overwritten.

        Returns
        -------
        int
            Number of rows actually written (may differ from ``len(chunks)``
            when some rows are no-ops in the real adapter).
        """
        ...

    async def query(
        self,
        embedding: list[float],
        k: int = 5,
    ) -> list[KBHit]:
        """Return the top-*k* most-similar chunks for *embedding*.

        Parameters
        ----------
        embedding:
            Query vector (must match the dimensionality stored).
        k:
            Maximum number of results to return.

        Returns
        -------
        list[KBHit]
            Ranked from most to least similar.  Length ≤ *k*.
        """
        ...


__all__ = ["VectorStore"]
