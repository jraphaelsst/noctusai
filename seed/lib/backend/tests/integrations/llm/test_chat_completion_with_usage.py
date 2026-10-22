"""`chat_completion_with_usage`: text + the call's own priced usage, via the scoped collector (no global sink)."""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.llm import (
    InMemoryUsageSink,
    LLMConfig,
    chat_completion_with_usage,
    configure_llm,
    register,
)
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.providers import FakeProvider


@pytest.fixture
def world():
    fakes: dict[str, FakeProvider] = {}

    def install(fake: FakeProvider, name: str = "fake-usage") -> None:
        fakes[name] = fake
        register(name, lambda: fake)

    sink = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=sink))
    yield install, sink
    _reset_for_testing()


@pytest.mark.asyncio
async def test_returns_text_and_priced_usage_and_still_feeds_the_sink(world):
    install, sink = world
    install(FakeProvider(chat_responses=["oi"], chat_usage=[(1_000_000, 100_000)], usage_provider="anthropic"))
    out = await chat_completion_with_usage(
        [{"role": "user", "content": "x"}], provider="fake-usage", model="claude-opus-5", cache=False)
    assert out.text == "oi"
    assert out.usage is not None and out.usage.events == 1
    assert (out.usage.prompt_tokens, out.usage.completion_tokens) == (1_000_000, 100_000)
    assert out.usage.cost_usd == pytest.approx(5.0 + 2.5)  # opus: 5/1M in, 25/1M out
    assert len(sink.events) == 1  # the configured sink saw the same event


@pytest.mark.asyncio
async def test_no_event_is_unmeasured_not_zero(world):
    install, _ = world
    install(FakeProvider(chat_responses=["oi"]))  # not scripted -> records nothing
    out = await chat_completion_with_usage([{"role": "user", "content": "x"}], provider="fake-usage", model="m")
    assert out.text == "oi" and out.usage is None


@pytest.mark.asyncio
async def test_concurrent_calls_never_see_each_others_events(world):
    install, _ = world
    install(FakeProvider(chat_responses=["a", "b"], chat_usage=[(10, 1), (20, 2)], usage_provider="anthropic"))

    async def call():
        return await chat_completion_with_usage(
            [{"role": "user", "content": "x"}], provider="fake-usage", model="claude-opus-5", cache=False)

    a, b = await asyncio.gather(call(), call())
    assert a.usage.events == 1 and b.usage.events == 1
    assert sorted((a.usage.prompt_tokens, b.usage.prompt_tokens)) == [10, 20]
