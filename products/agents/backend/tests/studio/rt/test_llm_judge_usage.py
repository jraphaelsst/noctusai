"""``app.studio.evals``'s cost-control seam (contract §L): the judge's cost comes from the seed's
``chat_completion_with_usage`` (scoped ``coletar_uso`` collection). The LLM is the seed's ``FakeProvider``
registered under a provider name (the DI seam) -- never a patch of our own code."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.studio.evals import Criterion, JudgeError, LlmJudge, TurnCost, combine_cost
from noctusai_lib.integrations.llm import LLMConfig, configure_llm, register
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.providers import FakeProvider

ORG = uuid4()
RAW = '{"veredito": [{"n": 1, "ok": true, "motivo": "m"}], "notas": "ok"}'


@pytest.fixture
def install_fake():
    configure_llm(LLMConfig(key_provider=lambda *_a, **_k: "test-key"))

    def _install(fake: FakeProvider) -> None:
        register("fake-judge", lambda: fake)

    yield _install
    _reset_for_testing()


async def _judge(provider: str = "fake-judge"):
    return await LlmJudge(provider=provider, model="claude-sonnet-5").judge(
        org_id=ORG, entrada="e", contexto=None, criterios=[Criterion("deve", "x")], rubrica=None, saida="resposta",
    )


class TestLlmJudgeCostCapture:
    @pytest.mark.asyncio
    async def test_judge_attaches_the_priced_usage_to_its_verdict(self, install_fake):
        install_fake(FakeProvider(chat_responses=[RAW], chat_usage=[(1_000_000, 100_000)], usage_provider="anthropic"))
        verdict = await _judge()
        assert verdict.custo.custo_usd == pytest.approx(2.0 + 1.0)  # sonnet-5: 2/1M in, 10/1M out
        assert (verdict.custo.tokens_entrada, verdict.custo.tokens_saida) == (1_000_000, 100_000)

    @pytest.mark.asyncio
    async def test_no_usage_recorded_is_an_empty_cost_not_a_zero(self, install_fake):
        install_fake(FakeProvider(chat_responses=[RAW]))
        assert (await _judge()).custo == TurnCost()

    @pytest.mark.asyncio
    async def test_judge_call_failure_still_raises_judge_error(self, install_fake):
        # provider not registered -> the seed raises; the judge maps it to its own typed error
        with pytest.raises(JudgeError):
            await _judge(provider="nao-registrado")


class TestCombineCost:
    def test_both_legs_present_sums_every_field(self):
        a = TurnCost(custo_usd=0.01, tokens_entrada=10, tokens_saida=5, tokens_cache_leitura=2)
        b = TurnCost(custo_usd=0.02, tokens_entrada=7, tokens_saida=3, tokens_cache_leitura=None)
        assert combine_cost(a, b) == TurnCost(custo_usd=0.03, tokens_entrada=17, tokens_saida=8, tokens_cache_leitura=2)

    def test_both_legs_absent_stays_null_never_a_silent_zero(self):
        assert combine_cost(TurnCost(), TurnCost()) == TurnCost()

    def test_one_leg_present_the_other_absent_gives_a_partial_total(self):
        assert combine_cost(TurnCost(custo_usd=0.05), TurnCost()).custo_usd == pytest.approx(0.05)
