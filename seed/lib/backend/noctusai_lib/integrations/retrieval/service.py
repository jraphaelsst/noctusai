"""`Retriever`: index a text corpus, search it. Async facade over a sync store."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from .chunking import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP, chunk_markdown
from .protocol import Embedder, RetrievalStore
from .types import EmbeddedChunk, IndexResult, RetrievalError, ScoredChunk

logger = logging.getLogger(__name__)

DEFAULT_K = 4
#: Cosine floor for a chunk to count as relevant. 0.3 suits OpenAI
#: `text-embedding-3-small` on short pt-BR passages (unrelated text sits
#: ~0.1-0.2). Callers with a measured corpus override it.
DEFAULT_MIN_SCORE = 0.3


class Retriever:
    def __init__(
        self,
        store: RetrievalStore,
        embedder: Embedder,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._max_chars = max_chars
        self._overlap = overlap

    def source_hash(self, text: str) -> str:
        """Identity of (text, chunking params, embedding space): any change
        re-indexes, an identical re-index is a no-op (no provider spend)."""
        h = hashlib.sha256()
        for part in (self._embedder.model_id, str(self._max_chars), str(self._overlap), text):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    async def index_text(
        self, namespace: str, text: str, *, org_id: Optional[str] = None
    ) -> IndexResult:
        chunks = chunk_markdown(text, max_chars=self._max_chars, overlap=self._overlap)
        if not chunks:
            raise RetrievalError(f"retrieval: refusing to index an empty corpus (namespace={namespace})")
        source_hash = self.source_hash(text)
        current = await asyncio.to_thread(self._store.corpus_hash, namespace=namespace, org_id=org_id)
        if current == source_hash:
            return IndexResult(len(chunks), True, source_hash)
        vectors = await self._embedder.embed_many([c.embed_text for c in chunks], org_id=org_id)
        if len(vectors) != len(chunks):
            raise RetrievalError(f"retrieval: embedder returned {len(vectors)} vectors for {len(chunks)} chunks")
        stored = await asyncio.to_thread(
            self._store.replace_corpus,
            namespace=namespace, org_id=org_id, source_hash=source_hash,
            chunks=[EmbeddedChunk(c, v) for c, v in zip(chunks, vectors)],
        )
        logger.info("retrieval: indexed namespace=%s org=%s chunks=%d", namespace, org_id, stored)
        return IndexResult(stored, False, source_hash)

    async def search(
        self,
        namespace: str,
        query: str,
        *,
        org_id: Optional[str] = None,
        k: int = DEFAULT_K,
        min_score: float = DEFAULT_MIN_SCORE,
        meter_org_id: Optional[str] = None,
    ) -> list[ScoredChunk]:
        """`org_id` is the SCOPE searched (None = platform corpus). `meter_org_id`
        only attributes the embedding spend (defaults to `org_id`) — it never
        widens what is read."""
        if not (query or "").strip():
            return []
        embedding = await self._embedder.embed_one(query, org_id=meter_org_id or org_id)
        return await asyncio.to_thread(
            self._store.search,
            namespace=namespace, org_id=org_id, embedding=embedding, k=k, min_score=min_score,
        )

    async def purge_org(self, org_id: str) -> int:
        return await asyncio.to_thread(self._store.purge_org, org_id=org_id)
