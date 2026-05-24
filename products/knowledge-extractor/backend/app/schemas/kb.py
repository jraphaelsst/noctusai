"""Knowledge-base search wire schemas (pgvector semantic search)."""
from __future__ import annotations

from pydantic import BaseModel


class KBResult(BaseModel):
    document_id: str
    module: str | None
    text: str
    score: float


class KBSearchResponse(BaseModel):
    query: str
    configured: bool
    results: list[KBResult]
