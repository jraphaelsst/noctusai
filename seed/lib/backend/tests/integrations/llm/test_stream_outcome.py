"""`chat_completion_stream(..., outcome=StreamOutcome())` — every provider
reports whether its stream was cut off at `max_tokens`, from the vendor's own
stop signal, and never forwards `outcome` to the vendor SDK.

Without this a truncated stream ends exactly like a finished one (2026-10-01:
the IgIg help chat cut a walkthrough mid-section and still reported `done`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import types as genai_types

from noctusai_lib.integrations.llm import StreamOutcome
from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider
from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider
from noctusai_lib.integrations.llm.providers.gemini_provider import GeminiProvider
from noctusai_lib.integrations.llm.providers.openai_provider import OpenAIProvider

MSGS = [{"role": "user", "content": "oi"}]


async def _drain(agen) -> list[str]:
    return [c async for c in agen]


# --- Anthropic -------------------------------------------------------------


class _AnthropicStream:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            yield "parte"
        return gen()

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop_reason, usage=None)


class _AnthropicMessages:
    def __init__(self, stop_reason):
        self.stop_reason = stop_reason
        self.sent: dict = {}

    def stream(self, **kwargs):
        self.sent = kwargs
        return _AnthropicStream(self.stop_reason)


def _anthropic(stop_reason):
    provider = AnthropicProvider()
    client = SimpleNamespace(messages=_AnthropicMessages(stop_reason))
    provider._clients["k"] = client  # the provider's own per-key client pool
    return provider, client


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason, truncated", [("max_tokens", True), ("end_turn", False)])
async def test_anthropic_fills_outcome_from_stop_reason(stop_reason, truncated):
    provider, client = _anthropic(stop_reason)
    outcome = StreamOutcome()

    chunks = await _drain(provider.chat_completion_stream(MSGS, model="m", api_key="k", outcome=outcome))

    assert chunks == ["parte"]
    assert outcome.truncated is truncated
    assert outcome.stop_reason == stop_reason
    assert "outcome" not in client.messages.sent, "outcome must never reach the vendor SDK"


# --- OpenAI ----------------------------------------------------------------


def _openai_chunk(content=None, finish_reason=None, usage=None):
    choices = [] if content is None and finish_reason is None else [
        SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=finish_reason)
    ]
    return SimpleNamespace(choices=choices, model="m", usage=usage)


class _OpenAICompletions:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason
        self.sent: dict = {}

    async def create(self, **kwargs):
        self.sent = kwargs

        async def gen():
            yield _openai_chunk("parte")
            yield _openai_chunk(None, self.finish_reason)
            yield _openai_chunk()  # the trailing usage-only chunk (no choices)
        return gen()


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason, truncated", [("length", True), ("stop", False)])
async def test_openai_fills_outcome_from_finish_reason(finish_reason, truncated):
    provider = OpenAIProvider()
    completions = _OpenAICompletions(finish_reason)
    provider._clients["k"] = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    outcome = StreamOutcome()

    chunks = await _drain(provider.chat_completion_stream(MSGS, model="m", api_key="k", outcome=outcome))

    assert chunks == ["parte"]
    assert outcome.truncated is truncated
    assert outcome.stop_reason == finish_reason
    assert "outcome" not in completions.sent


# --- Gemini ----------------------------------------------------------------


class _GeminiModels:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason
        self.sent: dict = {}

    async def generate_content_stream(self, **kwargs):
        self.sent = kwargs

        async def gen():
            yield SimpleNamespace(text="parte", candidates=[], usage_metadata=None)
            yield SimpleNamespace(
                text=None,
                candidates=[SimpleNamespace(finish_reason=self.finish_reason)],
                usage_metadata=None,
            )
        return gen()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish_reason, truncated",
    [(genai_types.FinishReason.MAX_TOKENS, True), (genai_types.FinishReason.STOP, False)],
)
async def test_gemini_fills_outcome_from_finish_reason(finish_reason, truncated):
    provider = GeminiProvider()
    models = _GeminiModels(finish_reason)
    provider._clients["k"] = SimpleNamespace(aio=SimpleNamespace(models=models))
    outcome = StreamOutcome()

    chunks = await _drain(provider.chat_completion_stream(MSGS, model="m", api_key="k", outcome=outcome))

    assert chunks == ["parte"]
    assert outcome.truncated is truncated
    assert outcome.stop_reason == finish_reason.value
    assert "outcome" not in models.sent


# --- Fake + the "unknown" default -------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_scripts_truncation_by_round():
    provider = FakeProvider(stream_responses=[["a"], ["b"]], stream_truncated=[True])
    first, second = StreamOutcome(), StreamOutcome()

    await _drain(provider.chat_completion_stream(MSGS, model="m", api_key="k", outcome=first))
    await _drain(provider.chat_completion_stream(MSGS, model="m", api_key="k", outcome=second))

    assert (first.truncated, first.stop_reason) == (True, "max_tokens")
    assert (second.truncated, second.stop_reason) == (False, "end_turn")


def test_unfilled_outcome_is_unknown_not_complete():
    assert StreamOutcome().truncated is None
