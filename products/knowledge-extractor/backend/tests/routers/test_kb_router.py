"""Status-pinned tests for the KB search router (DI-seam'd vector store + embedder)."""
from __future__ import annotations

import asyncio

from app.integrations.vectors.fake import FakeVectorStore
from app.integrations.vectors.types import KBChunk
from app.main import app
from app.routers import kb_router


async def _fake_embed(text: str):
    return [1.0, 0.0, 0.0]


def _seeded_store() -> FakeVectorStore:
    store = FakeVectorStore()
    chunk = KBChunk(
        id="modulo-1.md-0",
        document_id="modulo-1.md",
        content="conteúdo de teste sobre pilares de conteúdo",
        module="modulo-1",
    )
    asyncio.run(store.upsert([(chunk, [1.0, 0.0, 0.0])]))
    return store


def test_kb_search_configured(client):
    app.dependency_overrides[kb_router.get_vector_store] = lambda: _seeded_store()
    app.dependency_overrides[kb_router.get_embedder] = lambda: _fake_embed
    r = client.get("/api/kb/search", params={"q": "pilares", "k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["query"] == "pilares"
    assert len(body["results"]) >= 1
    assert body["results"][0]["document_id"] == "modulo-1.md"
    assert body["results"][0]["module"] == "modulo-1"


def test_kb_search_not_configured(client):
    app.dependency_overrides[kb_router.get_vector_store] = lambda: None
    r = client.get("/api/kb/search", params={"q": "pilares"})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["results"] == []


def test_kb_search_requires_query(client):
    app.dependency_overrides[kb_router.get_vector_store] = lambda: None
    r = client.get("/api/kb/search")
    assert r.status_code == 422
