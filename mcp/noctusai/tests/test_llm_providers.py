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
