"""The `claude_sdk` runtime records each SDK turn in the central ledger (it bypasses the seed LLM client)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip("claude_agent_sdk")  # the SDK ships in the CI image, not every dev venv

import noctusai_lib.integrations.llm.client as _llm_client
from noctusai_lib.integrations.llm import InMemoryUsageSink, LLMConfig, configure_llm

from app.runtime.claude_runtime import _meter_sdk_result
from app.runtime.types import AgentSpec, TurnContext

ORG = uuid4()


@pytest.fixture
def sink():
    s = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=s))
    yield s
    _llm_client._active_config = None


def _spec():
    return AgentSpec(key="bia", model="claude-sonnet-4-5", effort="medium", prompt_append="S", skills=(), tools=(),
                     max_turns=5, prompt_mode="custom", toolset="studio", provider="anthropic", runtime="claude_sdk")


def _ctx(**kw):
    return TurnContext(org_id=ORG, conversation_id=uuid4(), requested_by=uuid4(), instance_id="t",
                       sdk_session_id=None, **kw)


def _msg(usage, cost=0.01, is_error=False):
    return SimpleNamespace(usage=usage, total_cost_usd=cost, is_error=is_error)


@pytest.mark.asyncio
async def test_turn_recorded_once_with_agent_conversation_and_catalog_price(sink):
    ctx = _ctx()
    await _meter_sdk_result(_spec(), ctx, _msg({"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50}))
    assert len(sink.events) == 1
    e = sink.events[0]
    assert (e.agent_key, e.conversation_id, e.product, e.org_id) == ("bia", str(ctx.conversation_id), "agents", str(ORG))
    assert (e.prompt_tokens, e.completion_tokens, e.cache_read_input_tokens) == (100, 20, 50)
    assert e.provider == "anthropic" and e.extra["runtime"] == "claude_sdk" and e.extra["sdk_total_cost_usd"] == 0.01


@pytest.mark.asyncio
async def test_unmeasured_tokens_stay_null_not_zero(sink):
    await _meter_sdk_result(_spec(), _ctx(ephemeral=True), _msg({}, cost=None))
    e = sink.events[0]
    assert e.prompt_tokens is None and e.completion_tokens is None and e.total_tokens is None
    assert e.extra["tokens_unmeasured"] is True and "sdk_total_cost_usd" not in e.extra
    assert e.conversation_id is None  # ephemeral turn


@pytest.mark.asyncio
async def test_sdk_error_result_is_status_error(sink):
    await _meter_sdk_result(_spec(), _ctx(), _msg({"input_tokens": 1, "output_tokens": 1}, is_error=True))
    assert sink.events[0].status == "error"
