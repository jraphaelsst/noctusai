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

import types

import pytest

from noctusai_lib.integrations.llm import (
    InMemoryUsageSink,
    LLMConfig,
    configure_llm,
)
from noctusai_lib.integrations.llm import client as _llm_client
from noctusai_lib.integrations.llm.exceptions import LLMAPIError
from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider


def _reset_llm_config() -> None:
    """Uninstall the config this file installed, so it cannot leak into a
    sibling test file that expects none."""
    _llm_client._active_config = None


class _FakeEmbedding:
    def __init__(self, values): self.values = values


class _FakeResponse:
    def __init__(self, vectors, usage=None):
        self.embeddings = [_FakeEmbedding(v) for v in vectors]
        # The vendor's own token count rides on the RESPONSE, which is where
        # the provider reads it from. `None` models a vendor reply that
        # carries no accounting at all.
        self.usage_metadata = usage


class _FakeModels:
    def __init__(self, vectors):
        self._vectors = vectors
        self.seen = {}
        self.usage_metadata = None
    async def embed_content(self, *, model, contents, config=None):
        self.seen = {"model": model, "contents": contents, "config": config}
        return _FakeResponse(self._vectors, self.usage_metadata)


class _FakeClient:
    def __init__(self, vectors): self.aio = types.SimpleNamespace(models=_FakeModels(vectors))


@pytest.fixture
def sink():
    """A REAL `InMemoryUsageSink`, installed through `configure_llm`.

    🔴 THIS REPLACES A `monkeypatch.setitem(sys.modules, ...)` THAT STUBBED
    OUT `noctusai_lib.integrations.llm.usage` FOR THIS WHOLE FILE. That is a
    self-monkeypatch of our own module (CLAUDE.md §1), and it bought nothing:
    `record_usage` already returns early when no config is installed and never
    raises. What it DID buy was a hole — it silenced the accounting call in
    the same slice that got the accounting wrong, so no test in this file
    could observe that the embed paths were reporting zero tokens. The keeper
    missed it because `check_no_self_monkeypatch` matches `setattr`, not
    `setitem` on `sys.modules`.

    Installing the sanctioned seam instead means the accounting is now
    ASSERTED rather than suppressed — see `TestUsageAccounting`.
    """
    s = InMemoryUsageSink()
    # `key_provider` is required by the dataclass but never consulted here:
    # these tests hand the provider its `api_key=` directly and stub the
    # client, so nothing ever resolves a key.
    configure_llm(LLMConfig(key_provider=lambda _p, _o=None: None, usage_sink=s))
    yield s
    _reset_llm_config()


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


class TestUsageAccounting:
    """The accounting the old stub made unobservable.

    🔴 WHY THIS MATTERS MORE THAN IT LOOKS: the reason an operator switches to
    Gemini is that the OpenAI account ran out of credit — so Gemini is the
    vendor carrying the load exactly when `enforce_budget` most needs to see
    it. `record_usage` computes cost as `prompt_tokens or 0`, so passing None
    lands every row at 0.00 and the spend guardrail goes blind on the one
    provider still spending.
    """

    @pytest.mark.asyncio
    async def test_single_embed_reports_the_vendor_token_count(self, sink):
        p, c = _provider([[0.0] * 1536])
        c.aio.models.usage_metadata = types.SimpleNamespace(total_token_count=42)
        await p.generate_embedding("x", model="gemini-embedding-001", api_key="k")

        assert len(sink.events) == 1
        evento = sink.events[0]
        assert evento.provider == "gemini"
        assert evento.operation == "embedding"
        assert evento.total_tokens == 42
        # The field cost is computed from — None here is the silent-zero bug.
        assert evento.prompt_tokens == 42

    @pytest.mark.asyncio
    async def test_batch_embed_reports_the_vendor_token_count(self, sink):
        p, c = _provider([[0.0] * 1536, [0.0] * 1536])
        c.aio.models.usage_metadata = types.SimpleNamespace(total_token_count=99)
        await p.generate_embeddings_batch(
            ["a", "b"], model="gemini-embedding-001", api_key="k"
        )

        assert len(sink.events) == 1
        assert sink.events[0].total_tokens == 99
        assert sink.events[0].prompt_tokens == 99

    @pytest.mark.asyncio
    async def test_a_vendor_that_reports_nothing_is_recorded_as_unknown(self, sink):
        """No `usage_metadata` must still record the CALL — a missing count is
        not a missing request, and dropping the row would hide the call from
        the ledger entirely."""
        p, _ = _provider([[0.0] * 1536])
        await p.generate_embedding("x", model="gemini-embedding-001", api_key="k")

        assert len(sink.events) == 1
        assert sink.events[0].total_tokens is None
