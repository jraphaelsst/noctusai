"""``app.studio.evals``'s cost-control seam (contract §L): the small
composing usage sink :class:`~app.studio.evals._CapturingUsageSink` +
:func:`~app.studio.evals._call_with_usage` that recovers a
``noctusai_lib`` ``chat_completion`` call's cost, since that function only
ever returns text (its usage goes to a sink the caller never otherwise
sees). ``noctusai_lib.integrations.llm.chat_completion`` is patched here —
an EXTERNAL boundary (seed-owned shared library, exactly like patching the
``anthropic`` SDK client elsewhere in this product), never this product's
own code.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.studio import evals as evals_module
from app.studio.evals import (
    Criterion,
    JudgeError,
    LlmJudge,
    TurnCost,
    _call_with_usage,
    _CapturingUsageSink,
    combine_cost,
)
from noctusai_lib.integrations.llm import LLMConfig, configure_llm, get_llm_config
from noctusai_lib.integrations.llm.client import get_llm_config as _get_llm_config_raw
from noctusai_lib.integrations.llm.usage import UsageEvent

ORG = uuid4()


@pytest.fixture(autouse=True)
def _reset_usage_capture_state():
    """The capture sink is installed once, process-wide (contract §L
    docstring) — reset both halves of that state around every test so
    tests never see each other's installed sink.

    Also self-contained against test ORDER: some other test in the full
    suite calls `shutdown_llm()` (process-wide, `_active_config = None`)
    at app-lifespan teardown — if that ran before this module's tests,
    `get_llm_config()` would raise even though `app.main` configured it
    at import time. Installing a minimal config here when that happens
    keeps this file's tests correct regardless of suite order, without
    papering over the (pre-existing, unrelated) global-state leak."""
    try:
        _get_llm_config_raw()
    except RuntimeError:
        configure_llm(LLMConfig(key_provider=lambda *_a, **_k: "test-key"))
    config = get_llm_config()
    saved_sink = config.usage_sink
    saved_installed = evals_module._installed_usage_sink
    evals_module._installed_usage_sink = None
    config.usage_sink = None
    yield
    evals_module._installed_usage_sink = saved_installed
    config.usage_sink = saved_sink


def _event(**overrides) -> UsageEvent:
    defaults = dict(
        provider="anthropic", model="claude-sonnet-5", operation="chat",
        prompt_tokens=120, completion_tokens=40, total_tokens=160,
        cost_estimate_usd=0.0123,
    )
    defaults.update(overrides)
    return UsageEvent(**defaults)


class TestCallWithUsage:
    @pytest.mark.asyncio
    async def test_happy_path_recovers_cost_from_the_recorded_event(self):
        async def call():
            # `_call_with_usage` installs the sink BEFORE awaiting `call()`
            # (inside its lock), so `get_llm_config().usage_sink` here is
            # already the capture sink.
            await get_llm_config().usage_sink.record(_event())
            return "resposta"

        text, cost = await _call_with_usage(
            call, provider="anthropic", model="claude-sonnet-5", org_id=ORG,
        )
        assert text == "resposta"
        assert cost == TurnCost(custo_usd=0.0123, tokens_entrada=120, tokens_saida=40, tokens_cache_leitura=None)

    @pytest.mark.asyncio
    async def test_no_event_recorded_logs_and_returns_empty_cost(self):
        async def call():
            return "sem uso"

        text, cost = await _call_with_usage(call, provider="anthropic", model="claude-sonnet-5", org_id=ORG)
        assert text == "sem uso"
        assert cost == TurnCost()

    @pytest.mark.asyncio
    async def test_events_for_a_different_model_are_ignored(self):
        async def call():
            await get_llm_config().usage_sink.record(_event(model="gpt-4o-mini"))
            return "x"

        _text, cost = await _call_with_usage(call, provider="anthropic", model="claude-sonnet-5", org_id=ORG)
        assert cost == TurnCost()  # the foreign-model event never matched

    @pytest.mark.asyncio
    async def test_a_real_production_sink_still_receives_every_event(self):
        received: list[UsageEvent] = []

        class _RealSink:
            async def record(self, event):
                received.append(event)

        get_llm_config().usage_sink = _RealSink()
        event = _event()

        async def call():
            await get_llm_config().usage_sink.record(event)
            return "x"

        await _call_with_usage(call, provider="anthropic", model="claude-sonnet-5", org_id=ORG)
        assert received == [event]  # composed, never replaced

    @pytest.mark.asyncio
    async def test_the_buffer_never_grows_across_calls(self):
        async def call():
            await get_llm_config().usage_sink.record(_event())
            return "x"

        await _call_with_usage(call, provider="anthropic", model="claude-sonnet-5", org_id=ORG)
        sink = evals_module._installed_usage_sink
        assert isinstance(sink, _CapturingUsageSink)
        assert sink.events == []  # drained after the first call
        await _call_with_usage(call, provider="anthropic", model="claude-sonnet-5", org_id=ORG)
        assert sink.events == []


class TestLlmJudgeCostCapture:
    @pytest.mark.asyncio
    async def test_judge_attaches_the_captured_cost_to_its_verdict(self):
        raw = '{"veredito": [{"n": 1, "ok": true, "motivo": "m"}], "notas": "ok"}'

        async def fake_chat_completion(*_a, **kw):
            await get_llm_config().usage_sink.record(_event())
            return raw

        with patch("noctusai_lib.integrations.llm.chat_completion", new=AsyncMock(side_effect=fake_chat_completion)):
            judge = LlmJudge()
            verdict = await judge.judge(
                org_id=ORG, entrada="e", contexto=None, criterios=[Criterion("deve", "x")],
                rubrica=None, saida="resposta do agente",
            )
        assert verdict.custo.custo_usd == pytest.approx(0.0123)
        assert verdict.custo.tokens_entrada == 120

    @pytest.mark.asyncio
    async def test_judge_call_failure_still_raises_judge_error(self):
        with patch(
            "noctusai_lib.integrations.llm.chat_completion",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            judge = LlmJudge()
            with pytest.raises(JudgeError):
                await judge.judge(
                    org_id=ORG, entrada="e", contexto=None, criterios=[Criterion("deve", "x")],
                    rubrica=None, saida="resposta",
                )


class TestCombineCost:
    def test_both_legs_present_sums_every_field(self):
        a = TurnCost(custo_usd=0.01, tokens_entrada=10, tokens_saida=5, tokens_cache_leitura=2)
        b = TurnCost(custo_usd=0.02, tokens_entrada=7, tokens_saida=3, tokens_cache_leitura=None)
        assert combine_cost(a, b) == TurnCost(custo_usd=0.03, tokens_entrada=17, tokens_saida=8, tokens_cache_leitura=2)

    def test_both_legs_absent_stays_null_never_a_silent_zero(self):
        assert combine_cost(TurnCost(), TurnCost()) == TurnCost()

    def test_one_leg_present_the_other_absent_gives_a_partial_total(self):
        a = TurnCost(custo_usd=0.05)
        b = TurnCost()
        assert combine_cost(a, b).custo_usd == pytest.approx(0.05)
