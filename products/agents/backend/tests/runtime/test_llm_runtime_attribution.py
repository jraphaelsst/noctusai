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
    _ = [e async for e in _rt(spy).run_turn(_spec("nosnolimiar"), _ctx(conv=conv), "ola", broker=None)]
    attr = spy.seen[0]
    assert (attr.agent_key, attr.conversation_id, attr.product, attr.org_id) == ("nosnolimiar", str(conv), "agents", str(ORG))


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


def _pick_responses():
    return [ChatToolsResponse(tool_calls=(ToolCall("c", "pick", {"a": 1}),), finish_reason="tool_calls",
                              usage=LLMUsage(1, 1, 0, 0, 0.0))]


@pytest.mark.asyncio
async def test_structured_extract_purpose_routes_the_model_of_the_same_provider_and_is_attributed():
    spy = _Spy(tool_responses=_pick_responses() * 3)
    rt = _rt(spy)
    tool = ToolSpec("pick", "pick")
    await rt.structured_extract(provider="anthropic", model="version-model", org_id=ORG, system="s", user="u",
                                tool=tool, purpose="summarize")
    assert spy.calls[-1]["model"] == "claude-haiku-5-5"   # the light tier of the SAME provider
    assert spy.seen[-1].purpose == "summarize"
    await rt.structured_extract(provider="anthropic", model="version-model", org_id=ORG, system="s", user="u",
                                tool=tool, purpose="extract")
    assert spy.calls[-1]["model"] == "claude-sonnet-5"
    # No purpose = the version's model, exactly as before.
    await rt.structured_extract(provider="anthropic", model="version-model", org_id=ORG, system="s", user="u",
                                tool=tool)
    assert spy.calls[-1]["model"] == "version-model"


@pytest.mark.asyncio
async def test_structured_extract_purpose_without_a_routable_model_keeps_the_version_model():
    spy = _Spy(tool_responses=_pick_responses())
    await _rt(spy).structured_extract(provider="some-vendor", model="version-model", org_id=ORG, system="s",
                                      user="u", tool=ToolSpec("pick", "pick"), purpose="summarize")
    assert spy.calls[-1]["model"] == "version-model"


@pytest.mark.asyncio
async def test_run_turn_never_routes_julias_main_model():
    spy = _Spy(tool_responses=_ok())
    _ = [e async for e in _rt(spy).run_turn(_spec("julia"), _ctx(), "ola", broker=None)]
    assert spy.calls[-1]["model"] == "gpt-5.6-terra"
    assert spy.seen[-1].purpose is None


@pytest.mark.asyncio
async def test_a_turn_is_one_trace_with_a_span_per_tool_call():
    from noctusai_lib.integrations.llm import InMemorySpanSink, configure_span_sink
    from noctusai_lib.integrations.llm.tracing import current_trace_ids
    from app.runtime.llm_runtime import LlmToolset

    sink = InMemorySpanSink()
    configure_span_sink(sink)
    try:
        tool = ToolSpec("buscar", "buscar")
        spy = _Spy(tool_responses=[
            ChatToolsResponse(tool_calls=(ToolCall("c1", "buscar", {}),), finish_reason="tool_calls",
                              usage=LLMUsage(1, 1, 0, 0, 0.0)),
            ChatToolsResponse(text="pronto", usage=LLMUsage(1, 1, 0, 0, 0.0)),
        ])
        from noctusai_lib.integrations.llm import ToolResult

        toolset = LlmToolset(tools=(tool,), handler=lambda call: ToolResult(call.call_id, "{}"))
        rt = LlmToolRuntime(
            messages=FakeMessageStore(), key_resolver=lambda p, o: "sk", limiter=LlmTurnLimiter(2),
            provider_impl=spy, tools_factory=lambda spec, ctx: toolset,
        )
        _ = [e async for e in rt.run_turn(_spec("julia"), _ctx(), "ola", broker=None)]
    finally:
        configure_span_sink(None)
    by = {s.name: s for s in sink.spans}
    assert set(by) == {"agents.turn", "buscar"}
    assert by["buscar"].kind == "tool" and by["buscar"].parent_span_id == by["agents.turn"].span_id
    assert by["buscar"].trace_id == by["agents.turn"].trace_id and by["agents.turn"].parent_span_id is None
    assert by["agents.turn"].agent_key == "julia" and by["agents.turn"].product == "agents"
    assert current_trace_ids() is None  # nothing leaks after the turn


@pytest.mark.asyncio
async def test_unverifiable_budget_and_spend_refusals_become_a_retryable_capacity_error():
    from noctusai_lib.integrations.llm import LLMBudgetUnverifiable, SpendCeilingExceeded, SpendCeilingUnverifiable

    from app.runtime.errors import LlmCapacityError
    from app.runtime.llm_runtime import _map_error, make_budget_guard

    async def monthly(_org):
        raise LLMBudgetUnverifiable(str(ORG), "db down")

    with pytest.raises(LlmCapacityError):
        await make_budget_guard(monthly=monthly)(ORG)
    for exc in (SpendCeilingExceeded("agents", str(ORG), 5.0, 0.0, 1.0), SpendCeilingUnverifiable("agents", str(ORG), "x"),
                LLMBudgetUnverifiable(str(ORG), "x")):
        assert isinstance(_map_error(exc, "openai"), LlmCapacityError)
