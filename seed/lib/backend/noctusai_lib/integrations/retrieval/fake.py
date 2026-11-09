"""In-memory Fake of the retrieval organ (tests + local dev).

Mirrors the Real store's isolation contract exactly: every row lives under an
exact (namespace, org_id) key, `org_id=None` is its own scope, and nothing
reads across keys.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Callable, Optional, Sequence

from .types import EMBEDDING_DIMENSIONS, CacheHit, EmbeddedChunk, ScoredChunk

_Key = tuple[str, Optional[str]]
_TOKEN = re.compile(r"\w+", re.UNICODE)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"vector width mismatch: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder: texts sharing words have a
    higher cosine. Counts calls so tests can prove "no embedding spent"."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS, model_id: str = "fake-hash-1") -> None:
        self._dim = dimensions
        self._model_id = model_id
        self.calls = 0
        self.texts_embedded = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest()[:8], 16)
            v[h % self._dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed_one(self, text: str, *, org_id: Optional[str] = None) -> list[float]:
        self.calls += 1
        self.texts_embedded += 1
        return self._vec(text)

    async def embed_many(self, texts: Sequence[str], *, org_id: Optional[str] = None) -> list[list[float]]:
        self.calls += 1
        self.texts_embedded += len(texts)
        return [self._vec(t) for t in texts]


class InMemoryRetrievalStore:
    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._corpora: dict[_Key, tuple[str, list[tuple[EmbeddedChunk]]]] = {}
        self._cache: dict[_Key, list[dict]] = {}

    def corpus_hash(self, *, namespace: str, org_id: Optional[str]) -> Optional[str]:
        entry = self._corpora.get((namespace, org_id))
        return entry[0] if entry else None

    def replace_corpus(self, *, namespace, org_id, source_hash, chunks) -> int:
        self._corpora[(namespace, org_id)] = (source_hash, [(c,) for c in chunks])
        return len(chunks)

    def search(self, *, namespace, org_id, embedding, k, min_score) -> list[ScoredChunk]:
        entry = self._corpora.get((namespace, org_id))
        if not entry:
            return []
        scored = [
            ScoredChunk(c.chunk.heading, c.chunk.content, c.chunk.position, cosine(embedding, c.embedding))
            for (c,) in entry[1]
        ]
        scored = [s for s in scored if s.score >= min_score]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:k]

    def cache_lookup(self, *, namespace, org_id, prompt_version, embedding, min_score) -> Optional[CacheHit]:
        now = self._clock()
        best: Optional[CacheHit] = None
        for row in self._cache.get((namespace, org_id), []):
            if row["prompt_version"] != prompt_version or row["expires_at"] <= now:
                continue
            score = cosine(embedding, row["embedding"])
            if score >= min_score and (best is None or score > best.score):
                best = CacheHit(row["answer"], score)
        return best

    def cache_put(self, *, namespace, org_id, prompt_version, question_hash, embedding, answer, ttl_seconds) -> None:
        rows = self._cache.setdefault((namespace, org_id), [])
        rows[:] = [
            r for r in rows
            if not (r["prompt_version"] == prompt_version and r["question_hash"] == question_hash)
            and r["expires_at"] > self._clock()
        ]
        rows.append({
            "prompt_version": prompt_version, "question_hash": question_hash,
            "embedding": list(embedding), "answer": answer,
            "expires_at": self._clock() + ttl_seconds,
        })

    def purge_org(self, *, org_id: str) -> int:
        n = 0
        for key in [k for k in self._corpora if k[1] == org_id]:
            n += len(self._corpora.pop(key)[1])
        for key in [k for k in self._cache if k[1] == org_id]:
            n += len(self._cache.pop(key))
        return n
