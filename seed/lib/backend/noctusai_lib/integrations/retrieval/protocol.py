"""Protocols of the retrieval organ.

`RetrievalStore` is SYNCHRONOUS (the PostgREST client is); `Retriever` /
`SemanticCache` run it off the event loop. Every method is scoped by
(`namespace`, `org_id`) and that scope is EXACT: `org_id=None` is the
platform scope (e.g. a product's own help knowledge), never "all orgs".
There is no method that reads across orgs.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from .types import CacheHit, EmbeddedChunk, ScoredChunk


@runtime_checkable
class Embedder(Protocol):
    async def embed_one(self, text: str, *, org_id: Optional[str] = None) -> list[float]: ...

    async def embed_many(
        self, texts: Sequence[str], *, org_id: Optional[str] = None
    ) -> list[list[float]]: ...

    @property
    def model_id(self) -> str:
        """Identity of the embedding space; part of the corpus source hash so
        a model change forces a re-index instead of mixing spaces."""


@runtime_checkable
class RetrievalStore(Protocol):
    def corpus_hash(self, *, namespace: str, org_id: Optional[str]) -> Optional[str]:
        """The `source_hash` the stored corpus was indexed from (None = empty)."""

    def replace_corpus(
        self,
        *,
        namespace: str,
        org_id: Optional[str],
        source_hash: str,
        chunks: Sequence[EmbeddedChunk],
    ) -> int:
        """Atomically replace the (namespace, org) corpus. Returns rows stored."""

    def search(
        self,
        *,
        namespace: str,
        org_id: Optional[str],
        embedding: Sequence[float],
        k: int,
        min_score: float,
    ) -> list[ScoredChunk]:
        """Top-k by cosine similarity, `score >= min_score`, best first."""

    def cache_lookup(
        self,
        *,
        namespace: str,
        org_id: Optional[str],
        prompt_version: str,
        embedding: Sequence[float],
        min_score: float,
    ) -> Optional[CacheHit]: ...

    def cache_put(
        self,
        *,
        namespace: str,
        org_id: Optional[str],
        prompt_version: str,
        question_hash: str,
        embedding: Sequence[float],
        answer: str,
        ttl_seconds: int,
    ) -> None: ...

    def purge_org(self, *, org_id: str) -> int:
        """LGPD erasure: delete every chunk and cache row of one org."""
