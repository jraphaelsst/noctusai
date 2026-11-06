"""The Anthropic provider does not send `temperature`.

The `anthropic` SDK 1.x removed `temperature`/`top_p`/`top_k` from
`messages.create()` / `.stream()` (passing one is a `TypeError`), and current
models reject them at the API. The provider keeps accepting `temperature` so
callers don't change; it just doesn't forward it.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider


class _Block:
    text = "ok"


class _Message:
    content = [_Block()]
    usage = None


class _Stream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            yield "ok"
        return gen()

    async def get_final_message(self):
        return _Message()


class _Messages:
    def __init__(self):
        self.sent: dict = {}

    async def create(self, **kwargs):
        self.sent = kwargs
        return _Message()

    def stream(self, **kwargs):
        self.sent = kwargs
        return _Stream()


class _Client:
    def __init__(self):
        self.messages = _Messages()


def _provider() -> tuple[AnthropicProvider, _Client]:
    client = _Client()
    provider = AnthropicProvider()
    provider._clients["k"] = client  # the provider's own per-key client pool
    return provider, client


@pytest.mark.asyncio
async def test_chat_completion_does_not_send_temperature():
    provider, client = _provider()
    out = await provider.chat_completion(
        [{"role": "user", "content": "hi"}], model="m", api_key="k", temperature=0.0
    )
    assert out == "ok"
    assert "temperature" not in client.messages.sent


@pytest.mark.asyncio
async def test_chat_completion_stream_does_not_send_temperature():
    provider, client = _provider()
    chunks = [
        c
        async for c in provider.chat_completion_stream(
            [{"role": "user", "content": "hi"}], model="m", api_key="k", temperature=0.0
        )
    ]
    assert chunks == ["ok"]
    assert "temperature" not in client.messages.sent


def test_tool_request_forwards_temperature_only_when_it_differs_from_the_api_default():
    """The tool-calling path (channel turns) may ask for a lower temperature; the default sends nothing at all."""
    from noctusai_lib.integrations.llm.providers.anthropic_provider import build_anthropic_request

    assert "temperature" not in build_anthropic_request([], [], model="m")
    assert "temperature" not in build_anthropic_request([], [], model="m", temperature=1.0)
    assert build_anthropic_request([], [], model="m", temperature=0.3)["temperature"] == 0.3
    assert build_anthropic_request([], [], model="m", temperature=-2)["temperature"] == 0.0
