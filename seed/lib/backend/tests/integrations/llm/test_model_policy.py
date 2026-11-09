"""Purpose-based model routing (`model_policy.py`)."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm import InMemoryUsageSink, LLMConfig, chat_completion, configure_llm, register
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.model_policy import PURPOSES, TIERS, resolve_model, tier_for
from noctusai_lib.integrations.llm.models import MODELS
from noctusai_lib.integrations.llm.providers import FakeProvider


def test_every_tier_candidate_is_a_priced_non_stub_chat_row_of_the_catalog():
    catalog = {(m.provider, m.id): m for m in MODELS if m.kind == "chat"}
    for provider, tiers in TIERS.items():
        for tier, ids in tiers.items():
            assert ids, (provider, tier)
            for model_id in ids:
                row = catalog.get((provider, model_id))
                assert row is not None and not row.stub, (provider, tier, model_id)
                assert row.cost_per_1m_input_tokens is not None and row.cost_per_1m_output_tokens is not None


def test_standard_and_heavy_align_with_the_measured_document_routing():
    from noctusai_lib.integrations.documents.roteamento_modelos import TABELA

    assert TIERS["anthropic"]["standard"][0] == TABELA["padrao_global"]["primario"]
    assert TIERS["anthropic"]["heavy"][0] == TABELA["padrao_global"]["fallback"]


def test_light_is_never_dearer_than_standard_than_heavy():
    cost = {(m.provider, m.id): m.cost_per_1m_output_tokens for m in MODELS if m.kind == "chat"}
    for provider, t in TIERS.items():
        assert cost[(provider, t["light"][0])] <= cost[(provider, t["standard"][0])] <= cost[(provider, t["heavy"][0])]


def test_chat_and_omitted_mean_no_routing():
    assert resolve_model("anthropic", None) is None
    assert resolve_model("anthropic", "chat") is None
    assert tier_for(None) is None


def test_unknown_purpose_is_a_loud_error_not_a_silent_default():
    with pytest.raises(ValueError):
        resolve_model("anthropic", "summarise")


def test_unknown_provider_resolves_to_none_never_to_another_vendor():
    assert resolve_model("some-new-vendor", "classify") is None


def test_operator_disabled_model_is_skipped_for_the_next_candidate(monkeypatch):
    import noctusai_lib.integrations.llm.models as models

    real = models.models_for
    monkeypatch.setattr(models, "models_for", lambda p, k=None: [m for m in real(p, k) if m.id != "claude-haiku-5-5"])
    assert resolve_model("anthropic", "classify") == "claude-haiku-4-5"


@pytest.fixture
def world():
    fake = FakeProvider(chat_responses=["a", "b", "c"])
    register("anthropic-policy-fake", lambda: fake)
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=InMemoryUsageSink(),
                            default_chat_model="gpt-4o-mini"))
    yield fake
    _reset_for_testing()


@pytest.mark.asyncio
async def test_omitted_purpose_keeps_todays_model(world):
    await chat_completion([{"role": "user", "content": "x"}], provider="anthropic-policy-fake", cache=False)
    assert world.calls[-1]["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_explicit_model_always_wins_over_purpose(world):
    await chat_completion([{"role": "user", "content": "x"}], provider="anthropic-policy-fake", model="pinned",
                          purpose="reason", cache=False)
    assert world.calls[-1]["model"] == "pinned"


@pytest.mark.asyncio
async def test_purpose_on_a_provider_without_a_tier_keeps_the_default_and_never_fails_over(world):
    await chat_completion([{"role": "user", "content": "x"}], provider="anthropic-policy-fake", purpose="classify",
                          cache=False)
    assert world.calls[-1]["model"] == "gpt-4o-mini"  # custom provider name -> no routable row -> default stands


@pytest.mark.asyncio
async def test_purpose_routes_the_model_of_the_same_provider(monkeypatch):
    from noctusai_lib.integrations.llm import model_policy

    fake = FakeProvider(chat_responses=["a"], chat_usage=[(10, 1)], usage_provider="anthropic")
    register("fake-routed", lambda: fake)
    sink = InMemoryUsageSink()
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=sink))
    monkeypatch.setitem(model_policy.TIERS, "fake-routed", {"light": ("claude-haiku-5-5",)})
    monkeypatch.setattr("noctusai_lib.integrations.llm.models.models_for",
                        lambda p, k=None: [m for m in MODELS if m.provider == "anthropic" and (k is None or m.kind == k)])
    try:
        await chat_completion([{"role": "user", "content": "x"}], provider="fake-routed", purpose="classify",
                              cache=False)
    finally:
        _reset_for_testing()
    assert fake.calls[-1]["model"] == "claude-haiku-5-5"
    assert sink.events[-1].purpose == "classify"  # the usage row carries the purpose


def test_purposes_are_the_documented_five():
    assert PURPOSES == ("classify", "extract", "summarize", "reason", "chat")
