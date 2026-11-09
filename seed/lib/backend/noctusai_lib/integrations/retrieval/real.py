"""Supabase/pgvector store (Real). Service-role client over the `public`
schema (`DatabaseModule.get_core_client`); every call is one RPC = one
transaction (`public.retrieval_*`, core migration 115). The tables are tier
`service`: no browser grant, so org isolation here is enforced by the
(namespace, org_id) predicate INSIDE each function, not by RLS."""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from .types import EMBEDDING_DIMENSIONS, CacheHit, EmbeddedChunk, RetrievalError, ScoredChunk


def _vec(embedding: Sequence[float]) -> str:
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise RetrievalError(
            f"retrieval: embedding width {len(embedding)} != {EMBEDDING_DIMENSIONS} "
            "(the pgvector columns are fixed-width; a different model needs a migration + re-index)"
        )
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class SupabaseRetrievalStore:
    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._client_factory = core_client_factory

    def _rpc(self, name: str, params: dict) -> Any:
        try:
            return self._client_factory().rpc(name, params).execute().data
        except RetrievalError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised typed, with the cause chained
            raise RetrievalError(f"retrieval: rpc {name} failed ({type(exc).__name__})") from exc

    def corpus_hash(self, *, namespace: str, org_id: Optional[str]) -> Optional[str]:
        return self._rpc("retrieval_corpus_hash", {"p_namespace": namespace, "p_org_id": org_id}) or None

    def replace_corpus(self, *, namespace, org_id, source_hash, chunks: Sequence[EmbeddedChunk]) -> int:
        payload = [
            {
                "chunk_position": c.chunk.position, "heading": c.chunk.heading, "content": c.chunk.content,
                "content_hash": c.chunk.content_hash, "embedding": _vec(c.embedding),
            }
            for c in chunks
        ]
        n = self._rpc("retrieval_replace_corpus", {
            "p_namespace": namespace, "p_org_id": org_id, "p_source_hash": source_hash, "p_chunks": payload,
        })
        return int(n or 0)

    def search(self, *, namespace, org_id, embedding, k, min_score) -> list[ScoredChunk]:
        rows = self._rpc("retrieval_match_chunks", {
            "p_namespace": namespace, "p_org_id": org_id, "p_query": _vec(embedding),
            "p_k": k, "p_min_score": min_score,
        }) or []
        return [ScoredChunk(r["heading"], r["content"], int(r["chunk_position"]), float(r["score"])) for r in rows]

    def cache_lookup(self, *, namespace, org_id, prompt_version, embedding, min_score) -> Optional[CacheHit]:
        rows = self._rpc("retrieval_cache_lookup", {
            "p_namespace": namespace, "p_org_id": org_id, "p_prompt_version": prompt_version,
            "p_query": _vec(embedding), "p_min_score": min_score,
        }) or []
        return CacheHit(rows[0]["answer"], float(rows[0]["score"])) if rows else None

    def cache_put(self, *, namespace, org_id, prompt_version, question_hash, embedding, answer, ttl_seconds) -> None:
        self._rpc("retrieval_cache_put", {
            "p_namespace": namespace, "p_org_id": org_id, "p_prompt_version": prompt_version,
            "p_question_hash": question_hash, "p_embedding": _vec(embedding),
            "p_answer": answer, "p_ttl_seconds": ttl_seconds,
        })

    def purge_org(self, *, org_id: str) -> int:
        return int(self._rpc("retrieval_purge_org", {"p_org_id": org_id}) or 0)
