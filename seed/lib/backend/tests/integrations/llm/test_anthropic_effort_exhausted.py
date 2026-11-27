"""`effort` reaches Anthropic as `output_config.effort`; a reply that spent max_tokens thinking (no text) raises, never ''."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm.exceptions import LLMOutputExhausted
from noctusai_lib.integrations.llm.providers.anthropic_provider import AnthropicProvider


class _Usage:
    input_tokens = 40922
    output_tokens = 16000
    cache_read_input_tokens = None
    cache_creation_input_tokens = None


class _Thinking:  # a thinking block: no `.text`
    type = "thinking"


class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _Messages:
    def __init__(self, msg):
        self.msg = msg
        self.sent: dict = {}

    async def create(self, **kwargs):
        self.sent = kwargs
        return self.msg


class _Client:
    def __init__(self, msg):
        self.messages = _Messages(msg)


def _provider(msg):
    client = _Client(msg)
    p = AnthropicProvider()
    p._clients["k"] = client
    return p, client


@pytest.mark.asyncio
async def test_thinking_only_at_max_tokens_raises_with_token_counts():
    p, _ = _provider(_Msg([_Thinking()], "max_tokens"))
    with pytest.raises(LLMOutputExhausted) as ei:
        await p.chat_completion([{"role": "user", "content": "x"}], model="m", api_key="k", max_tokens=16000)
    assert ei.value.prompt_tokens == 40922 and ei.value.completion_tokens == 16000


@pytest.mark.asyncio
async def test_cut_off_text_is_still_returned_not_raised():
    p, _ = _provider(_Msg([_Text('{"a": "x')], "max_tokens"))
    assert await p.chat_completion([{"role": "user", "content": "x"}], model="m", api_key="k") == '{"a": "x'


@pytest.mark.asyncio
async def test_effort_is_forwarded_as_output_config():
    p, client = _provider(_Msg([_Text("ok")], "end_turn"))
    await p.chat_completion([{"role": "user", "content": "x"}], model="m", api_key="k", effort="medium")
    assert client.messages.sent["extra_body"] == {"output_config": {"effort": "medium"}}


@pytest.mark.asyncio
async def test_no_effort_sends_no_output_config():
    p, client = _provider(_Msg([_Text("ok")], "end_turn"))
    await p.chat_completion([{"role": "user", "content": "x"}], model="m", api_key="k")
    assert "extra_body" not in client.messages.sent
