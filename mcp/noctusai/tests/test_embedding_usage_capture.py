"""Tests for the real-usage capture mechanism (vector-costs real-cost tracking).

`_embedding_corpus.capture_embedding_usage` / `install_capture_sink` install a
chaining UsageSink on the LLM config so refreshers can log the GROUND-TRUTH
provider token count (not the len//4 estimate). These tests drive the sink
directly (simulating what `record_usage` does inside the provider) rather than
hitting OpenAI.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _embedding_corpus as ec  # noqa: E402


class _FakeConfig:
    """Stand-in for the LLM config — only needs a settable `usage_sink`."""

    def __init__(self) -> None:
        self.usage_sink = None


class _Event:
    def __init__(self, total_tokens, prompt_tokens=0, cost=0.0):
        self.total_tokens = total_tokens
        self.prompt_tokens = prompt_tokens
        self.cost_estimate_usd = cost


@pytest.fixture
def fake_config(monkeypatch):
    cfg = _FakeConfig()
    # Patch the lazy import target inside the capture functions.
    fake_client = types.ModuleType("noctusai_lib.integrations.llm.client")
    fake_client.get_llm_config = lambda: cfg  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "noctusai_lib.integrations.llm.client", fake_client)
    return cfg


def test_accumulator_sums_real_usage(fake_config):
    with ec.capture_embedding_usage() as usage:
        sink = fake_config.usage_sink
        assert sink is not None  # the capture sink was installed
        asyncio.run(sink.record(_Event(total_tokens=120, prompt_tokens=120, cost=0.0000024)))
        asyncio.run(sink.record(_Event(total_tokens=80, prompt_tokens=80, cost=0.0000016)))
    assert usage.calls == 2
    assert usage.total_tokens == 200
    assert usage.prompt_tokens == 200
    assert abs(usage.cost_usd - 0.000004) < 1e-12
    assert usage.has_data is True


def test_sink_restored_after_block(fake_config):
    sentinel = object()
    fake_config.usage_sink = sentinel
    with ec.capture_embedding_usage():
        assert fake_config.usage_sink is not sentinel  # swapped during block
    assert fake_config.usage_sink is sentinel  # restored after


def test_chains_to_previous_sink(fake_config):
    seen = []

    class _Prev:
        async def record(self, event):
            seen.append(event.total_tokens)

    fake_config.usage_sink = _Prev()
    with ec.capture_embedding_usage() as usage:
        asyncio.run(fake_config.usage_sink.record(_Event(total_tokens=42)))
    # Both the accumulator AND the previous (production) sink saw the event.
    assert usage.total_tokens == 42
    assert seen == [42]


def test_has_data_false_when_no_events(fake_config):
    with ec.capture_embedding_usage() as usage:
        pass
    assert usage.has_data is False
    assert usage.total_tokens == 0


def test_install_restore_pair_for_linear_flows(fake_config):
    acc = ec.UsageAccumulator()
    restore = ec.install_capture_sink(acc)
    asyncio.run(fake_config.usage_sink.record(_Event(total_tokens=333, cost=0.001)))
    restore()
    assert acc.total_tokens == 333
    assert acc.has_data is True
    assert fake_config.usage_sink is None  # restored to the original (None)


def test_degrades_gracefully_without_config(monkeypatch):
    """No LLM config available → capture is a no-op, the block still runs."""
    broken = types.ModuleType("noctusai_lib.integrations.llm.client")
    def _raise():
        raise RuntimeError("no config")
    broken.get_llm_config = _raise  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "noctusai_lib.integrations.llm.client", broken)
    ran = []
    with ec.capture_embedding_usage() as usage:
        ran.append(True)
    assert ran == [True]
    assert usage.has_data is False
