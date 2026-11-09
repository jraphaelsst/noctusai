"""Value types + errors of the retrieval organ (no IO)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

#: Width of every stored vector. The pgvector columns are `vector(1536)`
#: (OpenAI `text-embedding-3-small`, the seed's default embedding model).
#: Changing it is a migration + a full re-index, never a config edit: cosine
#: across two embedding spaces is noise.
EMBEDDING_DIMENSIONS = 1536


class RetrievalError(RuntimeError):
    """The retrieval store/embedder could not do its job (network, bad
    vector width, RPC refusal). Callers decide the fallback and MUST log it."""


class RetrievalNotConfigured(RetrievalError, IntegrationNotConfigured):
    """No store configured (`configure_retrieval_store` never called)."""


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage. `position` is the 0-based order in the source."""

    heading: str
    content: str
    position: int
    content_hash: str

    @property
    def embed_text(self) -> str:
        """What is embedded: the heading path gives a short chunk its topic."""
        return f"{self.heading}\n{self.content}" if self.heading else self.content


@dataclass(frozen=True)
class EmbeddedChunk:
    chunk: Chunk
    embedding: list[float] = field(repr=False)


@dataclass(frozen=True)
class ScoredChunk:
    """A search hit. `score` is cosine similarity in [-1, 1] (1 = identical)."""

    heading: str
    content: str
    position: int
    score: float


@dataclass(frozen=True)
class CacheHit:
    answer: str
    score: float


@dataclass(frozen=True)
class IndexResult:
    chunk_count: int
    #: True when the stored corpus already matched the source hash and nothing
    #: was embedded (no provider spend).
    skipped: bool
    source_hash: str


@dataclass(frozen=True)
class CacheLookup:
    """Outcome of `SemanticCache.lookup`. `embedding` is kept so a following
    `put` on a miss does not pay for the same embedding twice. `bypassed` is
    True when the caller opted out (`cache=False`, LGPD) — nothing was read,
    embedded or stored."""

    hit: Optional[CacheHit]
    embedding: Optional[list[float]] = field(default=None, repr=False)
    bypassed: bool = False
