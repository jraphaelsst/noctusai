"""Cost per agent / per session: the runtime opens `llm_usage_context` around every model call, so the
`ai_usage` row carries agent_key (+ conversation_id on a real conversation). Observed through a provider
double that reads `current_attribution()` at the moment the provider is called (nothing of ours patched)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.integrations.llm import (
    ChatToolsResponse, FakeProvider, LLMUsage, ToolCall, ToolSpec, current_attribution,
)

from app.runtime.llm_runtime import LlmToolRuntime, LlmTurnLimiter
from app.runtime.types import AgentSpec, TurnContext
from app.stores.messages import FakeMessageStore

ORG = uuid4()


class _Spy(FakeProvider):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.seen = []

    async def chat_with_tools(self, *a, **kw):
        self.seen.append(current_attribution())
        return await super().chat_with_tools(*a, **kw)


def _spec(key="julia"):
    return AgentSpec(
        key=key, model="gpt-5.6-terra", effort="medium", prompt_append="S", skills=(), tools=(),
        max_turns=5, prompt_mode="custom", toolset="studio", provider="openai", runtime="llm",
    )


def _rt(provider):
    return LlmToolRuntime(
        messages=FakeMessageStore(), key_resolver=lambda p, o: "sk", limiter=LlmTurnLimiter(2),
        provider_impl=provider,
    )


def _ctx(**kw):
    return TurnContext(org_id=ORG, conversation_id=kw.pop("conv", uuid4()), requested_by=uuid4(),
                       instance_id="t", sdk_session_id=None, **kw)


def _ok():
    return [ChatToolsResponse(text="oi", usage=LLMUsage(1, 1, 0, 0, 0.0))]


@pytest.mark.asyncio
async def test_turn_is_attributed_to_agent_and_conversation():
    spy = _Spy(tool_responses=_ok())
    conv = uuid4()
    _ = [e async for e in _rt(spy).run_turn(_spec("monica"), _ctx(conv=conv), "ola", broker=None)]
    attr = spy.seen[0]
    assert (attr.agent_key, attr.conversation_id, attr.product, attr.org_id) == ("monica", str(conv), "agents", str(ORG))


@pytest.mark.asyncio
async def test_ephemeral_turn_has_agent_but_no_conversation():
    spy = _Spy(tool_responses=_ok())
    _ = [e async for e in _rt(spy).run_turn(_spec(), _ctx(ephemeral=True), "ola", broker=None)]
    assert spy.seen[0].agent_key == "julia"
    assert spy.seen[0].conversation_id is None


@pytest.mark.asyncio
async def test_scope_does_not_leak_after_the_turn():
    spy = _Spy(tool_responses=_ok())
    _ = [e async for e in _rt(spy).run_turn(_spec(), _ctx(), "ola", broker=None)]
    assert current_attribution().agent_key is None


@pytest.mark.asyncio
async def test_structured_extract_carries_optional_agent_and_conversation():
    tool = ToolSpec("pick", "pick")
    conv = uuid4()
    spy = _Spy(tool_responses=[ChatToolsResponse(tool_calls=(ToolCall("c", "pick", {"a": 1}),), finish_reason="tool_calls",
                                                 usage=LLMUsage(1, 1, 0, 0, 0.0))] * 2)
    rt = _rt(spy)
    await rt.structured_extract(provider="openai", model="m", org_id=ORG, system="s", user="u", tool=tool,
                                agent_key="bia", conversation_id=conv)
    await rt.structured_extract(provider="openai", model="m", org_id=ORG, system="s", user="u", tool=tool)
    assert (spy.seen[0].agent_key, spy.seen[0].conversation_id) == ("bia", str(conv))
    assert (spy.seen[1].agent_key, spy.seen[1].conversation_id) == (None, None)
