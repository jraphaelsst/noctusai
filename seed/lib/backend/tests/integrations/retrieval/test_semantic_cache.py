"""SemanticCache: similar-question hit/miss, org isolation, LGPD opt-out."""
from __future__ import annotations

import pytest
from noctusai_lib.integrations.retrieval import FakeEmbedder, InMemoryRetrievalStore, SemanticCache

ORG_A = "aaaaaaaa-0000-0000-0000-000000000001"
ORG_B = "bbbbbbbb-0000-0000-0000-000000000002"
Q = "como eu cadastro um cliente novo no sistema"


class Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def parts():
    clock = Clock()
    store, emb = InMemoryRetrievalStore(clock=clock), FakeEmbedder()
    return store, emb, SemanticCache(store, emb, min_score=0.8, ttl_seconds=100), clock


@pytest.mark.asyncio
async def test_exact_and_similar_question_hit_unrelated_misses(parts):
    _, _, c, _ = parts
    assert await c.put("ns", Q, "Abra Clientes.", prompt_version="v1")
    assert (await c.lookup("ns", Q, prompt_version="v1")).hit.answer == "Abra Clientes."
    similar = await c.lookup("ns", "como eu cadastro um cliente novo no sistema?", prompt_version="v1")
    assert similar.hit and similar.hit.score >= 0.8
    assert (await c.lookup("ns", "qual o prazo de entrega do relatorio financeiro", prompt_version="v1")).hit is None


@pytest.mark.asyncio
async def test_prompt_version_bump_invalidates(parts):
    _, _, c, _ = parts
    await c.put("ns", Q, "resp", prompt_version="v1")
    assert (await c.lookup("ns", Q, prompt_version="v2")).hit is None


@pytest.mark.asyncio
async def test_org_a_answer_is_never_served_to_org_b_or_platform(parts):
    _, _, c, _ = parts
    await c.put("ns", Q, "resposta da org A", prompt_version="v1", org_id=ORG_A)
    assert (await c.lookup("ns", Q, prompt_version="v1", org_id=ORG_A)).hit
    assert (await c.lookup("ns", Q, prompt_version="v1", org_id=ORG_B)).hit is None
    assert (await c.lookup("ns", Q, prompt_version="v1", org_id=None)).hit is None


@pytest.mark.asyncio
async def test_ttl_expiry(parts):
    _, _, c, clock = parts
    await c.put("ns", Q, "resp", prompt_version="v1")
    clock.t += 101
    assert (await c.lookup("ns", Q, prompt_version="v1")).hit is None


@pytest.mark.asyncio
async def test_lgpd_opt_out_reads_nothing_embeds_nothing_stores_nothing(parts):
    store, emb, c, _ = parts
    lk = await c.lookup("ns", Q, prompt_version="v1", cache=False)
    assert lk.bypassed and lk.hit is None and lk.embedding is None
    assert await c.put("ns", Q, "dado clinico", prompt_version="v1", cache=False) is False
    assert emb.calls == 0
    assert store._cache == {}  # noqa: SLF001 - proving nothing was written
    await c.put("ns", Q, "resp", prompt_version="v1")
    assert (await c.lookup("ns", Q, prompt_version="v1", cache=False)).hit is None


@pytest.mark.asyncio
async def test_put_reuses_the_lookup_embedding(parts):
    _, emb, c, _ = parts
    lk = await c.lookup("ns", Q, prompt_version="v1")
    calls = emb.calls
    await c.put("ns", Q, "resp", prompt_version="v1", embedding=lk.embedding)
    assert emb.calls == calls


@pytest.mark.asyncio
async def test_same_question_replaces_instead_of_accumulating(parts):
    store, _, c, _ = parts
    await c.put("ns", Q, "velha", prompt_version="v1")
    await c.put("ns", Q, "nova", prompt_version="v1")
    assert len(store._cache[("ns", None)]) == 1  # noqa: SLF001
    assert (await c.lookup("ns", Q, prompt_version="v1")).hit.answer == "nova"


@pytest.mark.asyncio
async def test_store_failure_is_a_logged_miss_never_an_exception(parts, caplog):
    store, _, c, _ = parts

    def boom(**_):
        raise RuntimeError("db down")

    store.cache_lookup = boom  # a failing DEPENDENCY double, not our own guard
    with caplog.at_level("WARNING"):
        lk = await c.lookup("ns", Q, prompt_version="v1")
    assert lk.hit is None
    assert "lookup failed" in caplog.text
