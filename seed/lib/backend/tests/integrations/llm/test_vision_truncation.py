"""`analyze_image(..., return_metadata=True)` normalizes each vendor's own
truncation signal into one `VisionResult.truncated` bool.

Anthropic answers `stop_reason == "max_tokens"`, OpenAI
`finish_reason == "length"`, Gemini `FinishReason.MAX_TOKENS` — three
different vocabularies for the exact same event (a vision reply cut off
before the model finished). Every existing caller keeps getting a bare
`str` (`return_metadata` defaults to False) — see `vision_types.py`.

Same DI seam as `test_anthropic_no_temperature.py`: a fake vendor SDK
client is injected into the provider's own `_clients` cache, never a patch
of the provider/module under test.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider
from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider
from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider
from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider
from noctusai_lib.integrations.llm.vision_types import VisionResult


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class _AnthropicBlock:
    def __init__(self, text: str):
        self.text = text


class _AnthropicMessage:
    def __init__(self, text: str, stop_reason: str):
        self.content = [_AnthropicBlock(text)]
        self.stop_reason = stop_reason
        self.usage = None


class _AnthropicMessages:
    def __init__(self, message: _AnthropicMessage):
        self._message = message
        self.sent: dict = {}

    async def create(self, **kwargs):
        self.sent = kwargs
        return self._message


class _AnthropicClient:
    def __init__(self, message: _AnthropicMessage):
        self.messages = _AnthropicMessages(message)


def _anthropic_provider(message: _AnthropicMessage) -> AnthropicProvider:
    provider = AnthropicProvider()
    provider._clients["k"] = _AnthropicClient(message)
    return provider


class TestAnthropicTruncationNormalization:
    @pytest.mark.asyncio
    async def test_max_tokens_stop_reason_is_truncated(self) -> None:
        provider = _anthropic_provider(_AnthropicMessage("cortado", "max_tokens"))
        out = await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert isinstance(out, VisionResult)
        assert out.truncated is True
        assert out.stop_reason == "max_tokens"
        assert out.text == "cortado"

    @pytest.mark.asyncio
    async def test_end_turn_stop_reason_is_not_truncated(self) -> None:
        provider = _anthropic_provider(_AnthropicMessage("completo", "end_turn"))
        out = await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert out.truncated is False

    @pytest.mark.asyncio
    async def test_default_call_is_unaffected_bare_string(self) -> None:
        """`return_metadata` defaults to False — every existing caller keeps
        getting a bare string, even for a truncated reply."""
        provider = _anthropic_provider(_AnthropicMessage("cortado", "max_tokens"))
        out = await provider.analyze_image(b"img", "prompt", model="m", api_key="k")
        assert out == "cortado"
        assert isinstance(out, str) and not isinstance(out, VisionResult)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class _OpenAIResponse:
    def __init__(self, content: str, finish_reason: str):
        choice = SimpleNamespace(
            message=SimpleNamespace(content=content), finish_reason=finish_reason
        )
        self.choices = [choice]
        self.usage = None
        self.model = "gpt-4o"


class _OpenAICompletions:
    def __init__(self, response: _OpenAIResponse):
        self._response = response
        self.sent: dict = {}

    async def create(self, **kwargs):
        self.sent = kwargs
        return self._response


class _OpenAIClient:
    def __init__(self, response: _OpenAIResponse):
        self.chat = SimpleNamespace(completions=_OpenAICompletions(response))


def _openai_provider(response: _OpenAIResponse) -> OpenAIProvider:
    provider = OpenAIProvider()
    provider._clients["k"] = _OpenAIClient(response)
    return provider


class TestOpenAITruncationNormalization:
    @pytest.mark.asyncio
    async def test_length_finish_reason_is_truncated(self) -> None:
        provider = _openai_provider(_OpenAIResponse("cortado", "length"))
        out = await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert isinstance(out, VisionResult)
        assert out.truncated is True
        assert out.stop_reason == "length"

    @pytest.mark.asyncio
    async def test_stop_finish_reason_is_not_truncated(self) -> None:
        provider = _openai_provider(_OpenAIResponse("completo", "stop"))
        out = await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert out.truncated is False

    @pytest.mark.asyncio
    async def test_default_call_is_unaffected_bare_string(self) -> None:
        provider = _openai_provider(_OpenAIResponse("cortado", "length"))
        out = await provider.analyze_image(b"img", "prompt", model="m", api_key="k")
        assert out == "cortado"
        assert isinstance(out, str) and not isinstance(out, VisionResult)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


class _GeminiResponse:
    def __init__(self, text: str, finish_reason):
        self.text = text
        self.usage_metadata = None
        self.candidates = [SimpleNamespace(finish_reason=finish_reason)]


class _GeminiModels:
    def __init__(self, response: _GeminiResponse):
        self._response = response
        self.sent: dict = {}

    async def generate_content(self, **kwargs):
        self.sent = kwargs
        return self._response


class _GeminiClient:
    def __init__(self, response: _GeminiResponse):
        self.aio = SimpleNamespace(models=_GeminiModels(response))


def _gemini_provider(response: _GeminiResponse) -> GeminiProvider:
    provider = GeminiProvider()
    provider._clients["k"] = _GeminiClient(response)
    return provider


class TestGeminiTruncationNormalization:
    @pytest.mark.asyncio
    async def test_max_tokens_finish_reason_is_truncated(self) -> None:
        from google.genai import types

        provider = _gemini_provider(
            _GeminiResponse("cortado", types.FinishReason.MAX_TOKENS)
        )
        out = await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert isinstance(out, VisionResult)
        assert out.truncated is True
        assert out.stop_reason == "MAX_TOKENS"

    @pytest.mark.asyncio
    async def test_stop_finish_reason_is_not_truncated(self) -> None:
        from google.genai import types

        provider = _gemini_provider(_GeminiResponse("completo", types.FinishReason.STOP))
        out = await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert out.truncated is False

    @pytest.mark.asyncio
    async def test_default_call_is_unaffected_bare_string(self) -> None:
        from google.genai import types

        provider = _gemini_provider(
            _GeminiResponse("cortado", types.FinishReason.MAX_TOKENS)
        )
        out = await provider.analyze_image(b"img", "prompt", model="m", api_key="k")
        assert out == "cortado"
        assert isinstance(out, str) and not isinstance(out, VisionResult)

    @pytest.mark.asyncio
    async def test_max_tokens_kwarg_now_reaches_the_config(self) -> None:
        """🔴 Regression for the 2026-09-28 fix: `max_tokens` used to be
        silently dropped for Gemini (never forwarded to `generate_content`),
        so a truncation retry at a bigger cap would have been a no-op."""
        from google.genai import types

        response = _GeminiResponse("texto", types.FinishReason.STOP)
        client = _GeminiClient(response)
        provider = GeminiProvider()
        provider._clients["k"] = client

        await provider.analyze_image(
            b"img", "prompt", model="m", api_key="k", max_tokens=8192
        )

        config = client.aio.models.sent["config"]
        assert config.max_output_tokens == 8192

    @pytest.mark.asyncio
    async def test_no_max_tokens_kwarg_sends_no_config(self) -> None:
        """Existing callers that never pass `max_tokens` keep the exact
        prior request shape — no `config=` key at all."""
        from google.genai import types

        response = _GeminiResponse("texto", types.FinishReason.STOP)
        client = _GeminiClient(response)
        provider = GeminiProvider()
        provider._clients["k"] = client

        await provider.analyze_image(b"img", "prompt", model="m", api_key="k")

        assert "config" not in client.aio.models.sent


# ---------------------------------------------------------------------------
# FakeProvider — the scripted double keeps parity with the 3 real providers
# ---------------------------------------------------------------------------


class TestFakeProviderTruncationScripting:
    @pytest.mark.asyncio
    async def test_scripted_truncated_flag_is_honoured(self) -> None:
        fake = FakeProvider(
            vision_responses=["cortado"], vision_truncated=[True]
        )
        out = await fake.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert isinstance(out, VisionResult)
        assert out.truncated is True
        assert out.text == "cortado"

    @pytest.mark.asyncio
    async def test_unscripted_truncation_defaults_to_false(self) -> None:
        fake = FakeProvider(vision_responses=["completo"])
        out = await fake.analyze_image(
            b"img", "prompt", model="m", api_key="k", return_metadata=True
        )
        assert out.truncated is False

    @pytest.mark.asyncio
    async def test_default_call_is_unaffected_bare_string(self) -> None:
        fake = FakeProvider(vision_responses=["completo"])
        out = await fake.analyze_image(b"img", "prompt", model="m", api_key="k")
        assert out == "completo"
        assert isinstance(out, str) and not isinstance(out, VisionResult)
