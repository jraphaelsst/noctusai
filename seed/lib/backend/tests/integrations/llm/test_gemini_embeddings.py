"""Gemini embeddings — the width contract and the batch alignment.

Both behaviours were ADDED here (the provider previously passed no config and
had no batch method at all), and both fail silently if wrong:

  * no `output_dimensionality` → `gemini-embedding-001` returns 3072, which
    no `vector(1536)` column in this platform can store. The error surfaces at
    an INSERT, naming a column and nothing about the provider that caused it.
  * a short batch response → every embedding after the gap is stored against
    the WRONG item. Nothing raises; the matches just quietly get worse.
"""
from __future__ import annotations

import sys
import types

import pytest

from noctusai_lib.integrations.llm.exceptions import LLMAPIError
from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider


class _FakeEmbedding:
    def __init__(self, values): self.values = values


class _FakeResponse:
    def __init__(self, vectors): self.embeddings = [_FakeEmbedding(v) for v in vectors]


class _FakeModels:
    def __init__(self, vectors): self._vectors = vectors; self.seen = {}
    async def embed_content(self, *, model, contents, config=None):
        self.seen = {"model": model, "contents": contents, "config": config}
        return _FakeResponse(self._vectors)


class _FakeClient:
    def __init__(self, vectors): self.aio = types.SimpleNamespace(models=_FakeModels(vectors))


@pytest.fixture(autouse=True)
def _no_usage_sink(monkeypatch):
    """`record_usage` is imported inside the methods; stub the module it comes
    from so these stay pure unit tests with no accounting side-effects."""
    mod = types.ModuleType("noctusai_lib.integrations.llm.usage")
    async def _noop(**kw): return None
    mod.record_usage = _noop
    monkeypatch.setitem(sys.modules, "noctusai_lib.integrations.llm.usage", mod)


def _provider(vectors):
    p = GeminiProvider()
    client = _FakeClient(vectors)
    p._get_client = lambda _key: client  # type: ignore[method-assign]
    return p, client


class TestOutputDimensionality:
    @pytest.mark.asyncio
    async def test_no_width_requested_sends_no_config(self):
        """Callers that do not care must not have a width forced on them."""
        p, c = _provider([[0.0] * 3072])
        await p.generate_embedding("x", model="m", api_key="k")
        assert c.aio.models.seen["config"] is None

    @pytest.mark.asyncio
    async def test_requested_width_reaches_the_api(self):
        p, c = _provider([[0.0] * 1536])
        await p.generate_embedding(
            "x", model="m", api_key="k", output_dimensionality=1536)
        cfg = c.aio.models.seen["config"]
        assert cfg is not None
        assert cfg.output_dimensionality == 1536


class TestBatch:
    @pytest.mark.asyncio
    async def test_one_request_for_the_whole_list(self):
        """Without this method the shared helper degrades to one HTTP call per
        text — 226 requests for this corpus instead of a handful."""
        p, c = _provider([[1.0] * 1536, [2.0] * 1536, [3.0] * 1536])
        out = await p.generate_embeddings_batch(
            ["a", "b", "c"], model="m", api_key="k", output_dimensionality=1536)
        assert c.aio.models.seen["contents"] == ["a", "b", "c"]
        assert len(out) == 3

    @pytest.mark.asyncio
    async def test_order_is_preserved(self):
        p, _ = _provider([[1.0], [2.0], [3.0]])
        out = await p.generate_embeddings_batch(["a", "b", "c"], model="m", api_key="k")
        assert [v[0] for v in out] == [1.0, 2.0, 3.0]

    @pytest.mark.asyncio
    async def test_a_short_response_is_refused_not_misaligned(self):
        """🔴 The alignment guard. Two vectors for three texts would store
        text[2]'s meaning against item[1] with nothing raised."""
        p, _ = _provider([[1.0], [2.0]])
        with pytest.raises(LLMAPIError, match="desalinhar"):
            await p.generate_embeddings_batch(["a", "b", "c"], model="m", api_key="k")

    @pytest.mark.asyncio
    async def test_empty_list_makes_no_call(self):
        p, c = _provider([])
        assert await p.generate_embeddings_batch([], model="m", api_key="k") == []
        assert c.aio.models.seen == {}
