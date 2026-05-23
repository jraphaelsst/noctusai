"""Shared data types for the vector / knowledge-base seam.

On absorption these map onto whatever the seed uses for its KB types.
Keep field names stable — callers reference them by name.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KBChunk:
    """A single piece of knowledge stored in the vector store.

    Attributes
    ----------
    id:
        Stable unique identifier (deterministic from document_id + chunk index,
        e.g. ``"<doc_id>-<n>"``).
    document_id:
        The source document path (relative to the methodology directory) or a
        logical document name — used for grouping and deduplication.
    content:
        Plain-text content of this chunk (heading + body, markdown stripped on
        query but kept here for display).
    module:
        Module name / folder this chunk came from (e.g. ``"modulo-1"``).
    confidence:
        Extraction confidence (0.0–1.0).  Raw ingest sets this to 1.0; a
        future re-ranking step may lower it.
    """

    id: str
    document_id: str
    content: str
    module: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"KBChunk.confidence must be in [0, 1], got {self.confidence!r}"
            )


@dataclass
class KBHit:
    """A ranked result from a vector-store query.

    Attributes
    ----------
    chunk:
        The matching :class:`KBChunk`.
    score:
        Cosine similarity in [0, 1] (higher = more similar).
    """

    chunk: KBChunk
    score: float


__all__ = ["KBChunk", "KBHit"]
