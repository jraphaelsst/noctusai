"""Phase 2 provider tests.

Covers:
  - Provider registry populated after `noctusai_lib.llm` import
  - AnthropicProvider / GeminiProvider guard behavior (flag on/off)
  - AnthropicProvider / GeminiProvider canned-response shapes
  - FakeProvider scripted responses + call log + defaults
  - OpenAIProvider structural (constructor, client cache, close())
    — full async HTTP flows are covered by integration-tier tests in Phase 6/7

No monkeypatching of `noctusai_lib.llm.*` — every test constructs real
instances and exercises them directly.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from noctusai_lib.testing.conftest_helpers import restore_real_llm_providers

_LIB = Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


# ── Registry / auto-registration ────────────────────────────────

class TestAutoRegistration:
    def test_importing_llm_registers_three_providers(self):
        """Importing `noctusai_lib.llm` side-effects registration of OpenAI,
        Anthropic, and Gemini via their provider modules."""
        import noctusai_lib.integrations.llm  # noqa: F401
        from noctusai_lib.integrations.llm import list_providers

        registered = set(list_providers())
        assert {"openai", "anthropic", "gemini"}.issubset(registered)

    def test_fake_provider_is_not_registered(self):
        """FakeProvider is for tests only — must not leak into the registry."""
        import noctusai_lib.integrations.llm  # noqa: F401
        from noctusai_lib.integrations.llm import list_providers

        assert "fake" not in list_providers()


# ── AnthropicProvider (real — Phase 13) ─────────────────────────

class TestAnthropicReal:
    """After Phase 13 the Anthropic provider calls the real SDK. These tests
    verify the contract without hitting the network — they assert on:
      - missing-key → LLMNotConfigured
      - embeddings/transcription → ProviderNotImplemented (Anthropic does not
        offer those APIs)
      - message splitting helper `_split_system_and_messages`
    """

    def test_missing_key_raises_not_configured(self):
        from noctusai_lib.integrations.llm import LLMNotConfigured
        from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider

        p = AnthropicProvider()
        with pytest.raises(LLMNotConfigured):
            asyncio.run(p.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-sonnet-4-6",
                api_key="",
            ))

    def test_embedding_not_supported(self):
        from noctusai_lib.integrations.llm import ProviderNotImplemented
        from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider

        p = AnthropicProvider()
        with pytest.raises(ProviderNotImplemented):
            asyncio.run(p.generate_embedding(text="x", model="m", api_key="k"))

    def test_transcribe_not_supported(self):
        from noctusai_lib.integrations.llm import ProviderNotImplemented
        from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider

        p = AnthropicProvider()
        with pytest.raises(ProviderNotImplemented):
            asyncio.run(p.transcribe_audio(audio=b"", model="m", api_key="k"))

    def test_split_system_and_messages_separates_system(self):
        from noctusai_lib.integrations.llm.providers.anthropic_provider import _split_system_and_messages

        system, rest = _split_system_and_messages([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ])
        assert system == "You are helpful."
        assert len(rest) == 2
        assert rest[0]["role"] == "user"

    def test_split_concatenates_multiple_system_messages(self):
        from noctusai_lib.integrations.llm.providers.anthropic_provider import _split_system_and_messages

        system, rest = _split_system_and_messages([
            {"role": "system", "content": "Rule 1"},
            {"role": "system", "content": "Rule 2"},
            {"role": "user", "content": "Hi"},
        ])
        assert "Rule 1" in system and "Rule 2" in system
        assert len(rest) == 1


# ── GeminiProvider (real — Phase 14) ────────────────────────────

class TestGeminiReal:
    """Phase 14 — real google-generativeai wiring. Network-free checks."""

    def test_missing_key_raises_not_configured(self):
        from noctusai_lib.integrations.llm import LLMNotConfigured
        from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider

        p = GeminiProvider()
        with pytest.raises(LLMNotConfigured):
            asyncio.run(p.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="gemini-1.5-pro",
                api_key="",
            ))

    def test_translate_messages_renames_assistant_to_model(self):
        from noctusai_lib.integrations.llm.providers.gemini_provider import _translate_messages

        system, rest = _translate_messages([
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])
        assert system == "sys"
        assert rest[0].role == "user"
        assert rest[1].role == "model"

    def test_analyze_image_rejects_url_input(self):
        """Gemini SDK doesn't fetch URLs; the provider must surface that
        contract with a clear error rather than silently succeeding."""
        from noctusai_lib.integrations.llm import LLMAPIError
        from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider

        p = GeminiProvider()
        with pytest.raises(LLMAPIError):
            asyncio.run(p.analyze_image(
                image="https://example.com/x.jpg",
                prompt="p",
                model="gemini-1.5-pro",
                api_key="k",
            ))


# ── FakeProvider ────────────────────────────────────────────────

class TestFakeProvider:
    def test_scripted_chat_responses_consumed_in_order(self):
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider(chat_responses=["first", "second"])
        r1 = asyncio.run(
            fake.chat_completion(messages=[], model="gpt-4o", api_key="k")
        )
        r2 = asyncio.run(
            fake.chat_completion(messages=[], model="gpt-4o", api_key="k")
        )
        r3 = asyncio.run(
            fake.chat_completion(messages=[], model="gpt-4o", api_key="k")
        )
        assert r1 == "first"
        assert r2 == "second"
        assert "FAKE" in r3  # default after script exhausted

    def test_call_log_records_args(self):
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider()
        asyncio.run(
            fake.chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
                api_key="sk-test",
                temperature=0.3,
            )
        )
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "chat_completion"
        assert call["model"] == "gpt-4o-mini"
        assert call["api_key"] == "sk-test"
        assert call["temperature"] == 0.3

    def test_embedding_default_shape_matches_openai_small(self):
        """Default embedding (no script) is 1536-dim — matches
        text-embedding-3-small so tests that don't script embeddings still
        get shape-correct responses for downstream code expecting OpenAI's
        default size."""
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider()
        vec = asyncio.run(
            fake.generate_embedding(
                text="x", model="text-embedding-3-small", api_key="k"
            )
        )
        assert len(vec) == 1536

    def test_scripted_embedding(self):
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider(embedding_responses=[[0.1, 0.2, 0.3]])
        vec = asyncio.run(
            fake.generate_embedding(text="x", model="m", api_key="k")
        )
        assert vec == [0.1, 0.2, 0.3]

    def test_batch_embedding_is_one_recorded_call_for_many_texts(self):
        """The batching contract at the fake-provider level — mirrors the
        real OpenAIProvider's ONE `/embeddings` call per batch shape (KB §
        PATTERNS/common/vectorize-embed-cache-framework.md, the 2026-08
        retry-storm fix)."""
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider()
        texts = [f"chunk-{i}" for i in range(50)]
        vecs = asyncio.run(
            fake.generate_embeddings_batch(texts, model="text-embedding-3-small", api_key="k")
        )
        assert len(vecs) == 50
        assert all(len(v) == 1536 for v in vecs)
        batch_calls = [c for c in fake.calls if c["method"] == "generate_embeddings_batch"]
        assert len(batch_calls) == 1  # ONE call recorded for all 50 texts
        assert batch_calls[0]["texts"] == texts

    def test_batch_embedding_consumes_scripted_responses_in_order(self):
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider(embedding_responses=[[1.0], [2.0], [3.0]])
        vecs = asyncio.run(
            fake.generate_embeddings_batch(["a", "b"], model="m", api_key="k")
        )
        assert vecs == [[1.0], [2.0]]
        # Third scripted response still available for the next call.
        vec3 = asyncio.run(fake.generate_embedding(text="c", model="m", api_key="k"))
        assert vec3 == [3.0]

    def test_transcription_and_vision_scripted(self):
        from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider

        fake = FakeProvider(
            transcription_responses=["scripted text"],
            vision_responses=["scripted image analysis"],
        )
        t = asyncio.run(
            fake.transcribe_audio(audio=b"x", model="whisper-1", api_key="k")
        )
        v = asyncio.run(
            fake.analyze_image(image=b"y", prompt="describe", model="m", api_key="k")
        )
        assert t == "scripted text"
        assert v == "scripted image analysis"


# ── OpenAIProvider (structural) ─────────────────────────────────

class TestOpenAIProviderStructure:
    def test_no_client_without_api_key(self):
        from noctusai_lib.integrations.llm import LLMNotConfigured
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        p = OpenAIProvider()
        with pytest.raises(LLMNotConfigured):
            p._client_for("")  # empty key triggers the guard

    def test_client_cache_per_key(self):
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        p = OpenAIProvider()
        c1 = p._client_for("sk-a")
        c2 = p._client_for("sk-a")
        c3 = p._client_for("sk-b")
        assert c1 is c2, "same key must return the same cached client"
        assert c1 is not c3, "different keys must get different clients"

    def test_close_clears_cache(self):
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        p = OpenAIProvider()
        p._client_for("sk-a")
        p._client_for("sk-b")
        assert len(p._clients) == 2
        asyncio.run(p.close())
        assert len(p._clients) == 0

    def test_name_is_openai(self):
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        assert OpenAIProvider.name == "openai"


# ── OpenAIProvider.generate_embeddings_batch — the 2026-08 retry-storm fix ──
#
# Root cause: `generate_embedding` sends `input=<one string>` — one chunk,
# one HTTP request. A 508-chunk refresh loop calling it per-chunk fired 508
# independently-paced-and-retried requests (507 retries observed — ~1 per
# chunk — even though OpenAI itself was healthy the whole time: a single
# direct embed call always succeeded). `generate_embeddings_batch` sends
# `input=<array>` — the SAME endpoint accepts many texts in ONE request.
# These tests mock the `AsyncOpenAI` client directly (no network) and assert
# the request SHAPE: one `embeddings.create` call, `input` is the whole list,
# one rate-limit token consumed (not one per text), response re-ordered by
# `index` rather than trusted positionally.

class _FakeEmbeddingDatum:
    def __init__(self, index: int, embedding: list[float]) -> None:
        self.index = index
        self.embedding = embedding


class _FakeUsage:
    def __init__(self, prompt_tokens: int, total_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.total_tokens = total_tokens


class _FakeEmbeddingsResponse:
    def __init__(self, data: list, usage) -> None:
        self.data = data
        self.usage = usage


class TestOpenAIProviderBatchEmbedding:
    def _provider_with_mock_client(self, monkeypatch, response):
        """An OpenAIProvider whose `_client_for` returns a stub client with a
        mocked `embeddings.create` — no network, no real API key needed."""
        from unittest.mock import AsyncMock, MagicMock
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        mock_client = MagicMock()
        mock_client.embeddings.create = AsyncMock(return_value=response)
        monkeypatch.setattr(provider, "_client_for", lambda api_key: mock_client)

        # Pacing/backoff aren't the thing under test here — no-op them so the
        # request-SHAPE assertions aren't entangled with real sleep/jitter.
        from noctusai_lib.integrations import rate_limit
        acquire_calls = {"n": 0}

        async def _fake_acquire(bucket, tokens=1.0):
            acquire_calls["n"] += 1
            return 0.0

        monkeypatch.setattr(rate_limit, "acquire_async", _fake_acquire)
        return provider, mock_client, acquire_calls

    def test_one_request_for_many_texts(self, monkeypatch):
        response = _FakeEmbeddingsResponse(
            data=[
                _FakeEmbeddingDatum(0, [0.1, 0.2]),
                _FakeEmbeddingDatum(1, [0.3, 0.4]),
                _FakeEmbeddingDatum(2, [0.5, 0.6]),
            ],
            usage=_FakeUsage(prompt_tokens=30, total_tokens=30),
        )
        provider, mock_client, acquire_calls = self._provider_with_mock_client(
            monkeypatch, response
        )
        texts = ["alpha", "beta", "gamma"]
        vecs = asyncio.run(
            provider.generate_embeddings_batch(texts, model="text-embedding-3-small", api_key="sk-x")
        )
        assert mock_client.embeddings.create.await_count == 1  # ONE HTTP request
        call_kwargs = mock_client.embeddings.create.await_args.kwargs
        assert call_kwargs["input"] == texts  # the WHOLE list, one request
        assert call_kwargs["model"] == "text-embedding-3-small"
        assert vecs == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        assert acquire_calls["n"] == 1  # one pacing token for the whole batch

    def test_response_reordered_by_index_not_trusted_positionally(self, monkeypatch):
        """Defends against a provider (or a future SDK version) returning
        `data` out of request order — index-based sort keeps `result[i]`
        matched to `texts[i]` regardless."""
        response = _FakeEmbeddingsResponse(
            data=[
                _FakeEmbeddingDatum(2, [9.0]),
                _FakeEmbeddingDatum(0, [7.0]),
                _FakeEmbeddingDatum(1, [8.0]),
            ],
            usage=_FakeUsage(prompt_tokens=3, total_tokens=3),
        )
        provider, _client, _acq = self._provider_with_mock_client(monkeypatch, response)
        vecs = asyncio.run(
            provider.generate_embeddings_batch(["a", "b", "c"], model="m", api_key="k")
        )
        assert vecs == [[7.0], [8.0], [9.0]]

    def test_empty_list_makes_no_request(self, monkeypatch):
        response = _FakeEmbeddingsResponse(data=[], usage=_FakeUsage(0, 0))
        provider, mock_client, acquire_calls = self._provider_with_mock_client(
            monkeypatch, response
        )
        vecs = asyncio.run(
            provider.generate_embeddings_batch([], model="m", api_key="k")
        )
        assert vecs == []
        assert mock_client.embeddings.create.await_count == 0
        assert acquire_calls["n"] == 0

    def test_openai_error_wrapped_as_llm_api_error(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        from openai import APIError
        from noctusai_lib.integrations.llm import LLMAPIError
        from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
        mock_client = MagicMock()
        boom = APIError("rate limited", request=MagicMock(), body=None)
        mock_client.embeddings.create = AsyncMock(side_effect=boom)
        monkeypatch.setattr(provider, "_client_for", lambda api_key: mock_client)
        from noctusai_lib.integrations import rate_limit
        monkeypatch.setattr(
            rate_limit, "acquire_async", AsyncMock(return_value=0.0)
        )
        with pytest.raises(LLMAPIError):
            asyncio.run(
                provider.generate_embeddings_batch(["x"], model="m", api_key="k")
            )


# ── High-level `generate_embeddings_batch` dispatcher ────────────────────────
#
# `noctusai_lib.integrations.llm.embeddings.generate_embeddings_batch` is the
# funnel every refresh loop calls. It must: (a) route to a provider's native
# `generate_embeddings_batch` when present (the batching win), and (b)
# degrade gracefully to one `generate_embedding` call per text for a provider
# that hasn't implemented batch support — same result shape either way, so
# callers never special-case by provider.
#
# Follows the SAME real-plumbing seam `test_refusal.py` established
# (`register()` a test-owned provider class + `configure_llm()` — no
# monkeypatching of our own `get_provider`/`generate_embeddings_batch` code):
# `get_provider()` instantiates the registered class with no args and caches
# it by name, so call logs live at CLASS scope (mirroring
# `_ScriptedVisionProvider._visions` there).


class _CountingBatchProvider:
    """Registered test provider WITH native batch support."""

    calls: list[list[str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    async def generate_embeddings_batch(self, texts, *, model, api_key, org_id=None, **kwargs):
        type(self).calls.append(list(texts))
        return [[float(len(t))] for t in texts]

    async def generate_embedding(self, text, *, model, api_key, org_id=None, **kwargs):
        raise AssertionError(
            "must not fall back to per-text calls when the provider has "
            "native batch support — that would silently lose the batching win"
        )

    async def close(self) -> None:  # pragma: no cover — cleanup
        return None


class _NoBatchProvider:
    """Registered test provider WITHOUT batch support — the degrade path."""

    calls: list[str] = []

    @classmethod
    def reset(cls) -> None:
        cls.calls = []

    async def generate_embedding(self, text, *, model, api_key, org_id=None, **kwargs):
        type(self).calls.append(text)
        return [float(len(text))]

    async def close(self) -> None:  # pragma: no cover — cleanup
        return None


@pytest.fixture
def counting_batch_provider():
    from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm
    from noctusai_lib.integrations.llm.config import LLMConfig
    from noctusai_lib.integrations.llm.registry import register

    _CountingBatchProvider.reset()
    register("countingbatch", _CountingBatchProvider)
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: "test-key",
            default_provider="countingbatch",
        )
    )
    yield _CountingBatchProvider
    _provider_cache.clear()
    # Clearing the CACHE is not clearing the REGISTRY: `countingbatch` stayed
    # registered process-wide and broke `test_llm_endpoints` on the seeds where
    # pytest-randomly ordered it later. See `restore_real_llm_providers`.
    restore_real_llm_providers()


@pytest.fixture
def no_batch_provider():
    from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm
    from noctusai_lib.integrations.llm.config import LLMConfig
    from noctusai_lib.integrations.llm.registry import register

    _NoBatchProvider.reset()
    register("nobatch", _NoBatchProvider)
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: "test-key",
            default_provider="nobatch",
        )
    )
    yield _NoBatchProvider
    _provider_cache.clear()
    restore_real_llm_providers()


class TestGenerateEmbeddingsBatchDispatcher:
    def test_routes_to_provider_native_batch(self, counting_batch_provider):
        from noctusai_lib.integrations.llm import generate_embeddings_batch

        texts = ["a", "b", "c"]
        vecs = asyncio.run(generate_embeddings_batch(texts))
        assert vecs == [[1.0], [1.0], [1.0]]
        assert counting_batch_provider.calls == [texts]  # ONE call, not a loop

    def test_degrades_to_per_text_loop_when_provider_lacks_batch(self, no_batch_provider):
        """A provider without `generate_embeddings_batch` still gets a
        correct, order-preserving result — just via one `generate_embedding`
        call per text instead of one batch call."""
        from noctusai_lib.integrations.llm import generate_embeddings_batch

        vecs = asyncio.run(generate_embeddings_batch(["a", "bb", "ccc"]))
        assert vecs == [[1.0], [2.0], [3.0]]
        assert no_batch_provider.calls == ["a", "bb", "ccc"]  # order preserved, one call each

    def test_empty_list_short_circuits(self, counting_batch_provider):
        from noctusai_lib.integrations.llm import generate_embeddings_batch

        vecs = asyncio.run(generate_embeddings_batch([]))
        assert vecs == []
        assert counting_batch_provider.calls == []  # no provider call made at all
