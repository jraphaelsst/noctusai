"""Phase 15 — Token-accounting tests.

Providers emit a `UsageEvent` to the active `UsageSink` after every
successful call. These tests verify the contract + cost estimation.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "seed" / "backend" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import noctusai_lib.llm  # noqa: E402,F401


def _install_with_sink(sink, *, chat=None, embeddings=None):
    """Install a FakeProvider as 'openai' with an active usage sink."""
    from noctusai_lib.llm import FakeProvider, LLMConfig
    from noctusai_lib.llm.client import _reset_for_testing, configure_llm
    from noctusai_lib.llm.registry import register

    _reset_for_testing()
    fake = FakeProvider(chat_responses=chat, embedding_responses=embeddings)

    class _FakeClass:
        def __new__(cls):
            return fake

    register("openai", _FakeClass)  # type: ignore[arg-type]
    configure_llm(LLMConfig(
        key_provider=lambda p, org_id=None: "sk-test",
        default_provider="openai",
        usage_sink=sink,
    ))
    return fake


def _restore_real_providers():
    import importlib

    from noctusai_lib.llm.registry import _reset_for_testing as _reset_reg

    _reset_reg()
    for mod in (
        "noctusai_lib.llm.providers.openai_provider",
        "noctusai_lib.llm.providers.anthropic_provider",
        "noctusai_lib.llm.providers.gemini_provider",
    ):
        importlib.import_module(mod)
        importlib.reload(sys.modules[mod])


# ── UsageEvent + InMemoryUsageSink ──────────────────────────────

class TestInMemorySink:
    def test_records_events(self):
        from noctusai_lib.llm import InMemoryUsageSink, UsageEvent

        async def run():
            sink = InMemoryUsageSink()
            await sink.record(UsageEvent(
                provider="openai", model="gpt-4o-mini", operation="chat",
                prompt_tokens=100, completion_tokens=50, total_tokens=150,
                cost_estimate_usd=0.00004,
            ))
            assert len(sink.events) == 1
            assert sink.events[0].provider == "openai"
            assert sink.events[0].total_tokens == 150

        asyncio.run(run())

    def test_aggregate_groups_by_triple(self):
        from noctusai_lib.llm import InMemoryUsageSink, UsageEvent

        async def run():
            sink = InMemoryUsageSink()
            for _ in range(3):
                await sink.record(UsageEvent(
                    provider="openai", model="gpt-4o-mini", operation="chat",
                    org_id="org-a", prompt_tokens=100, completion_tokens=50,
                    total_tokens=150, cost_estimate_usd=0.00004,
                ))
            await sink.record(UsageEvent(
                provider="openai", model="gpt-4o-mini", operation="chat",
                org_id="org-b", prompt_tokens=200, completion_tokens=100,
                total_tokens=300, cost_estimate_usd=0.00008,
            ))
            agg = sink.aggregate()
            assert len(agg) == 2
            key_a = ("org-a", "openai", "gpt-4o-mini")
            assert agg[key_a]["calls"] == 3
            assert agg[key_a]["total_tokens"] == 450
            key_b = ("org-b", "openai", "gpt-4o-mini")
            assert agg[key_b]["calls"] == 1
            assert agg[key_b]["total_tokens"] == 300

        asyncio.run(run())


# ── estimate_cost_usd — catalog-driven ──────────────────────────

class TestCostEstimation:
    def test_known_model_computes_cost(self):
        from noctusai_lib.llm import estimate_cost_usd

        # gpt-4o-mini in the catalog: 0.15 in, 0.60 out per 1M
        # 1000 prompt + 500 completion → 0.00015 + 0.00030 = 0.00045
        cost = estimate_cost_usd(
            provider="openai", model="gpt-4o-mini",
            prompt_tokens=1000, completion_tokens=500,
        )
        assert abs(cost - 0.00045) < 1e-9

    def test_unknown_model_returns_zero(self):
        from noctusai_lib.llm import estimate_cost_usd

        cost = estimate_cost_usd(
            provider="openai", model="does-not-exist",
            prompt_tokens=1000, completion_tokens=500,
        )
        assert cost == 0.0

    def test_missing_tokens_returns_zero(self):
        from noctusai_lib.llm import estimate_cost_usd

        cost = estimate_cost_usd(
            provider="openai", model="gpt-4o",
            prompt_tokens=None, completion_tokens=None,
        )
        assert cost == 0.0

    def test_never_raises_on_bad_input(self):
        from noctusai_lib.llm import estimate_cost_usd

        # Provider not in catalog at all
        cost = estimate_cost_usd(
            provider="aliens",
            model="ufo-1",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost == 0.0


# ── record_usage goes to the configured sink ───────────────────

class TestRecordUsageDispatch:
    def teardown_method(self):
        _restore_real_providers()

    def test_record_usage_writes_to_active_sink(self):
        from noctusai_lib.llm import InMemoryUsageSink, record_usage

        sink = InMemoryUsageSink()
        _install_with_sink(sink)

        async def run():
            await record_usage(
                provider="openai", model="gpt-4o-mini", operation="chat",
                org_id="org-xyz", prompt_tokens=200, completion_tokens=100,
                total_tokens=300,
            )

        asyncio.run(run())
        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.org_id == "org-xyz"
        assert event.prompt_tokens == 200
        # Cost computed via catalog: 200 * 0.15/1M + 100 * 0.60/1M
        expected = (200 * 0.15 + 100 * 0.60) / 1_000_000.0
        assert abs(event.cost_estimate_usd - expected) < 1e-9

    def test_record_usage_noop_when_sink_is_none(self):
        from noctusai_lib.llm import record_usage
        from noctusai_lib.llm import FakeProvider, LLMConfig
        from noctusai_lib.llm.client import _reset_for_testing, configure_llm
        from noctusai_lib.llm.registry import register

        _reset_for_testing()
        fake = FakeProvider()

        class _FakeClass:
            def __new__(cls):
                return fake

        register("openai", _FakeClass)  # type: ignore[arg-type]
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: "sk-test",
            default_provider="openai",
            usage_sink=None,
        ))

        async def run():
            # Should not raise even with no sink
            await record_usage(
                provider="openai", model="gpt-4o-mini", operation="chat",
                prompt_tokens=1, completion_tokens=1, total_tokens=2,
            )

        asyncio.run(run())  # survives no-op

    def test_sink_failure_is_swallowed(self):
        """A broken sink must not break a successful LLM call."""
        from noctusai_lib.llm import record_usage, LLMConfig
        from noctusai_lib.llm import FakeProvider
        from noctusai_lib.llm.client import _reset_for_testing, configure_llm
        from noctusai_lib.llm.registry import register

        class ExplodingSink:
            async def record(self, event):
                raise RuntimeError("oops")

        _reset_for_testing()
        fake = FakeProvider()

        class _FakeClass:
            def __new__(cls):
                return fake

        register("openai", _FakeClass)  # type: ignore[arg-type]
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: "sk-test",
            default_provider="openai",
            usage_sink=ExplodingSink(),
        ))

        async def run():
            # If the sink's failure propagated, this would raise.
            await record_usage(
                provider="openai", model="gpt-4o-mini", operation="chat",
                prompt_tokens=1, completion_tokens=1, total_tokens=2,
            )

        asyncio.run(run())
