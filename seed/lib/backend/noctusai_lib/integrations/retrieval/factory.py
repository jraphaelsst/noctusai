"""Factory + process-wide configuration (house shape, cf. prompt_registry)."""
from __future__ import annotations

from typing import Any, Callable, Optional

from .embedder import LLMEmbedder
from .protocol import Embedder, RetrievalStore
from .real import SupabaseRetrievalStore
from .semantic_cache import SemanticCache
from .service import Retriever
from .types import RetrievalNotConfigured

_store: Optional[RetrievalStore] = None


def make_retrieval_store(core_client_factory: Callable[[], Any]) -> RetrievalStore:
    """The Real store over a service-role `public`-schema client factory
    (`DatabaseModule.get_core_client`). No implicit Fake: tests construct
    `InMemoryRetrievalStore` and `configure_retrieval_store` it."""
    if core_client_factory is None:
        raise ValueError("make_retrieval_store needs a service-role core client factory")
    return SupabaseRetrievalStore(core_client_factory)


def configure_retrieval_store(store: Optional[RetrievalStore]) -> None:
    global _store
    _store = store


def get_retrieval_store() -> RetrievalStore:
    if _store is None:
        raise RetrievalNotConfigured(
            "no retrieval store configured: call configure_retrieval_store(make_retrieval_store(get_core_client))"
        )
    return _store


def make_retriever(store: Optional[RetrievalStore] = None, embedder: Optional[Embedder] = None, **kw: Any) -> Retriever:
    return Retriever(store or get_retrieval_store(), embedder or LLMEmbedder(), **kw)


def make_semantic_cache(
    store: Optional[RetrievalStore] = None, embedder: Optional[Embedder] = None, **kw: Any
) -> SemanticCache:
    return SemanticCache(store or get_retrieval_store(), embedder or LLMEmbedder(), **kw)
