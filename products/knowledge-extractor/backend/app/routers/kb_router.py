"""KB router — semantic search over the methodology knowledge base (pgvector).

Embeds the query (``generate_embedding``) then queries the vector store
(``make_vector_store`` → supabase pgvector). When KB creds are absent the search
degrades gracefully to ``configured=false`` + empty results (never a 500). The
vector store + embedder are DI seams so tests inject fakes (never live OpenAI/DB).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user_org
from app.schemas.kb import KBResult, KBSearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb", tags=["kb"])


def get_vector_store():
    """DI seam — the configured vector store, or ``None`` if KB creds are absent.

    Tests override this with a seeded ``FakeVectorStore`` (never monkeypatching).
    """
    from app.integrations.vectors import make_vector_store
    from app.integrations.vectors.factory import VectorStoreNotConfigured

    try:
        return make_vector_store()
    except VectorStoreNotConfigured:
        return None


def get_embedder():
    """DI seam — the async embedding function. Tests override with a fake."""
    from app.integrations.llm import generate_embedding

    return generate_embedding


@router.get("/search", response_model=KBSearchResponse)
async def search_kb(
    q: str = Query(..., min_length=1),
    k: int = Query(default=8, ge=1, le=50),
    auth: tuple = Depends(get_current_user_org),
    store=Depends(get_vector_store),
    embedder=Depends(get_embedder),
) -> KBSearchResponse:
    if store is None:
        return KBSearchResponse(query=q, configured=False, results=[])
    embedding = await embedder(q)
    hits = await store.query(embedding, k)
    return KBSearchResponse(
        query=q,
        configured=True,
        results=[
            KBResult(
                document_id=h.chunk.document_id,
                module=h.chunk.module,
                text=h.chunk.content,
                score=h.score,
            )
            for h in hits
        ],
    )
