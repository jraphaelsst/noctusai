"""Semantic cache: a *similar* question hits, not only a byte-identical one
(the exact-match Redis cache in `integrations/llm/cache.py` stays the layer
for deterministic prompts; this one is for FAQ-style single-shot answers).

Isolation + LGPD, by construction:
  * a hit only ever comes from the SAME (namespace, org_id) AND `prompt_version`
    (bump the version when the system prompt/knowledge changes);
  * `cache=False` is the LGPD opt-out and is total: nothing is embedded, read
    or stored (same gate as `llm.cache`, `cache=False` on every call that
    carries free personal text);
  * only a hash of the question is stored, never its text;
  * cache-layer failure is a MISS, logged at WARNING (a cache must never break
    the answer), never swallowed silently.
Do not cache multi-turn answers that depend on earlier turns: the key is the
question alone.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from .protocol import Embedder, RetrievalStore
from .types import CacheLookup

logger = logging.getLogger(__name__)

#: High on purpose: a wrong cache hit is a confident wrong answer.
DEFAULT_CACHE_MIN_SCORE = 0.93
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def question_hash(question: str) -> str:
    return hashlib.sha256(" ".join(question.lower().split()).encode("utf-8")).hexdigest()


class SemanticCache:
    def __init__(
        self,
        store: RetrievalStore,
        embedder: Embedder,
        *,
        min_score: float = DEFAULT_CACHE_MIN_SCORE,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._min_score = min_score
        self._ttl = ttl_seconds

    async def lookup(
        self,
        namespace: str,
        question: str,
        *,
        prompt_version: str,
        org_id: Optional[str] = None,
        cache: bool = True,
    ) -> CacheLookup:
        if not cache or not (question or "").strip():
            return CacheLookup(hit=None, bypassed=not cache)
        try:
            embedding = await self._embedder.embed_one(question, org_id=org_id)
        except Exception as exc:  # noqa: BLE001 - a cache miss, logged
            logger.warning("retrieval.cache: embed failed namespace=%s (%s) - treating as miss", namespace, type(exc).__name__)
            return CacheLookup(hit=None)
        try:
            hit = await asyncio.to_thread(
                self._store.cache_lookup, namespace=namespace, org_id=org_id,
                prompt_version=prompt_version, embedding=embedding, min_score=self._min_score,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrieval.cache: lookup failed namespace=%s (%s) - treating as miss", namespace, type(exc).__name__)
            return CacheLookup(hit=None, embedding=embedding)
        return CacheLookup(hit=hit, embedding=embedding)

    async def put(
        self,
        namespace: str,
        question: str,
        answer: str,
        *,
        prompt_version: str,
        org_id: Optional[str] = None,
        cache: bool = True,
        embedding: Optional[list[float]] = None,
    ) -> bool:
        """Store an answer. Returns False when opted out, empty, or the
        store failed (logged)."""
        if not cache or not (question or "").strip() or not (answer or "").strip():
            return False
        try:
            if embedding is None:
                embedding = await self._embedder.embed_one(question, org_id=org_id)
            await asyncio.to_thread(
                self._store.cache_put, namespace=namespace, org_id=org_id,
                prompt_version=prompt_version, question_hash=question_hash(question),
                embedding=embedding, answer=answer, ttl_seconds=self._ttl,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrieval.cache: put failed namespace=%s (%s)", namespace, type(exc).__name__)
            return False
