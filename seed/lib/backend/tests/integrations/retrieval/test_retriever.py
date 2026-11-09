"""Retriever + store isolation (Fake) - org A never sees org B."""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.retrieval import (
    FakeEmbedder,
    InMemoryRetrievalStore,
    RetrievalError,
    Retriever,
)

KB = """# Clientes

Cadastrar cliente novo: abra o menu Clientes e toque em Novo cliente.

# Financeiro

Gerar cobranca do mes: abra Financeiro e toque em Gerar cobranca.
"""
ORG_A = "aaaaaaaa-0000-0000-0000-000000000001"
ORG_B = "bbbbbbbb-0000-0000-0000-000000000002"


@pytest.fixture
def parts():
    store, emb = InMemoryRetrievalStore(), FakeEmbedder()
    return store, emb, Retriever(store, emb, max_chars=200, overlap=20)


@pytest.mark.asyncio
async def test_search_returns_the_relevant_chunk_first(parts):
    _, _, r = parts
    await r.index_text("ns", KB)
    hits = await r.search("ns", "como cadastrar cliente novo", min_score=0.05)
    assert hits and hits[0].heading == "Clientes"
    assert hits == sorted(hits, key=lambda h: h.score, reverse=True)


@pytest.mark.asyncio
async def test_score_threshold_filters_and_k_caps(parts):
    _, _, r = parts
    await r.index_text("ns", KB)
    assert await r.search("ns", "zzz qqq completamente alheio", min_score=0.3) == []
    assert len(await r.search("ns", "cliente cobranca mes", k=1, min_score=0.0)) == 1


@pytest.mark.asyncio
async def test_blank_query_is_empty_without_embedding(parts):
    _, emb, r = parts
    await r.index_text("ns", KB)
    before = emb.calls
    assert await r.search("ns", "   ") == []
    assert emb.calls == before


@pytest.mark.asyncio
async def test_reindex_of_identical_text_spends_no_embedding(parts):
    _, emb, r = parts
    first = await r.index_text("ns", KB)
    calls = emb.calls
    second = await r.index_text("ns", KB)
    assert (first.skipped, second.skipped) == (False, True)
    assert emb.calls == calls


@pytest.mark.asyncio
async def test_changed_text_reindexes_and_replaces(parts):
    _, _, r = parts
    await r.index_text("ns", KB)
    await r.index_text("ns", "# Novo\n\nconteudo totalmente novo sobre relatorios")
    assert await r.search("ns", "cadastrar cliente", min_score=0.2) == []
    assert (await r.search("ns", "relatorios", min_score=0.2))[0].heading == "Novo"


@pytest.mark.asyncio
async def test_embedding_model_change_forces_reindex():
    store = InMemoryRetrievalStore()
    await Retriever(store, FakeEmbedder(model_id="m1")).index_text("ns", KB)
    res = await Retriever(store, FakeEmbedder(model_id="m2")).index_text("ns", KB)
    assert res.skipped is False


@pytest.mark.asyncio
async def test_empty_corpus_is_refused_loudly(parts):
    _, _, r = parts
    with pytest.raises(RetrievalError):
        await r.index_text("ns", "   ")


@pytest.mark.asyncio
async def test_org_a_never_sees_org_b(parts):
    _, _, r = parts
    await r.index_text("ns", "# Segredo\n\nplano secreto da org A alfa", org_id=ORG_A)
    await r.index_text("ns", "# Outro\n\nplano da org B beta", org_id=ORG_B)
    a = await r.search("ns", "plano secreto alfa", org_id=ORG_A, min_score=0.0)
    b = await r.search("ns", "plano secreto alfa", org_id=ORG_B, min_score=0.0)
    assert all("alfa" in h.content for h in a) and a
    assert all("alfa" not in h.content for h in b)


@pytest.mark.asyncio
async def test_org_scope_never_leaks_into_platform_scope_nor_back(parts):
    _, _, r = parts
    await r.index_text("ns", "# P\n\nconteudo da plataforma gama")
    await r.index_text("ns", "# O\n\nconteudo privado da org delta", org_id=ORG_A)
    plat = await r.search("ns", "conteudo privado delta", min_score=0.0)
    org = await r.search("ns", "conteudo da plataforma gama", org_id=ORG_A, min_score=0.0)
    assert all("delta" not in h.content for h in plat)
    assert all("gama" not in h.content for h in org)


@pytest.mark.asyncio
async def test_namespaces_are_isolated(parts):
    _, _, r = parts
    await r.index_text("one", "# A\n\nassunto exclusivo um")
    assert await r.search("two", "assunto exclusivo um", min_score=0.0) == []


@pytest.mark.asyncio
async def test_purge_org_erases_only_that_org(parts):
    _, _, r = parts
    await r.index_text("ns", "# A\n\nconteudo da org A", org_id=ORG_A)
    await r.index_text("ns", "# B\n\nconteudo da org B", org_id=ORG_B)
    assert await r.purge_org(ORG_A) >= 1
    assert await r.search("ns", "conteudo org", org_id=ORG_A, min_score=0.0) == []
    assert await r.search("ns", "conteudo org", org_id=ORG_B, min_score=0.0)
