"""Retrieval organ (RAG): chunking + embeddings (via the seed's shared
`generate_embedding`) + a per-org pgvector store + top-k search with a score
threshold + a semantic cache that honours the LGPD opt-out.

Protocol + Fake + Real + factory. Tables/RPCs: core `public.retrieval_*`
(migration 115), service-role only. KB § PATTERNS/backend/retrieval-organ.md.

    from noctusai_lib.integrations.retrieval import (
        configure_retrieval_store, make_retrieval_store, make_retriever,
    )
    configure_retrieval_store(make_retrieval_store(get_core_client))   # once, at startup
    r = make_retriever()
    await r.index_text("help_chat:my-product", knowledge_md)
    hits = await r.search("help_chat:my-product", "como cadastro um cliente?")
"""
from __future__ import annotations

from .chunking import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP, chunk_markdown, content_hash
from .embedder import LLMEmbedder
from .factory import (
    configure_retrieval_store,
    get_retrieval_store,
    make_retriever,
    make_retrieval_store,
    make_semantic_cache,
)
from .fake import FakeEmbedder, InMemoryRetrievalStore, cosine
from .protocol import Embedder, RetrievalStore
from .real import SupabaseRetrievalStore
from .semantic_cache import DEFAULT_CACHE_MIN_SCORE, SemanticCache, question_hash
from .service import DEFAULT_K, DEFAULT_MIN_SCORE, Retriever
from .types import (
    EMBEDDING_DIMENSIONS,
    CacheHit,
    CacheLookup,
    Chunk,
    EmbeddedChunk,
    IndexResult,
    RetrievalError,
    RetrievalNotConfigured,
    ScoredChunk,
)

__all__ = [
    "CacheHit", "CacheLookup", "Chunk", "DEFAULT_CACHE_MIN_SCORE", "DEFAULT_K", "DEFAULT_MAX_CHARS",
    "DEFAULT_MIN_SCORE", "DEFAULT_OVERLAP", "EMBEDDING_DIMENSIONS", "EmbeddedChunk", "Embedder",
    "FakeEmbedder", "InMemoryRetrievalStore", "IndexResult", "LLMEmbedder", "RetrievalError",
    "RetrievalNotConfigured", "RetrievalStore", "Retriever", "ScoredChunk", "SemanticCache",
    "SupabaseRetrievalStore", "chunk_markdown", "configure_retrieval_store", "content_hash", "cosine",
    "get_retrieval_store", "make_retrieval_store", "make_retriever", "make_semantic_cache", "question_hash",
]
