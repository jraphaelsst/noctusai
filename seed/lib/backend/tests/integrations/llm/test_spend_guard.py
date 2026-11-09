"""The per-surface rolling spend guard on every LLM call path (`spend_guard.py`).

Defaults under test: NO limit configured => nothing is read and nothing blocks; a configured limit is
`observe` (log only) unless it says `enforce`."""
from __future__ import annotations

import json
import logging

import pytest

from noctusai_lib.integrations.llm import (
    InMemorySpendWindowReader,
    InMemoryUsageSink,
    LLMConfig,
    SpendCeilingExceeded,
    SpendCeilingUnverifiable,
    SurfaceLimit,
    chat_completion,
    configure_llm,
    configure_spend_guard,
    register,
)
from noctusai_lib.integrations.llm import spend_guard
from noctusai_lib.integrations.llm.attribution import llm_usage_context
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.providers import FakeProvider

ORG = "00000000-0000-0000-0000-0000000000aa"


@pytest.fixture
def world():
    fake = FakeProvider(chat_responses=["ok"] * 10)
    register("fake-guard", lambda: fake)
    configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=InMemoryUsageSink()))
    reader = InMemorySpendWindowReader()
    yield fake, reader
    configure_spend_guard(reader=None, limits={})
    _reset_for_testing()


async def _call():
    return await chat_completion([{"role": "user", "content": "x"}], provider="fake-guard", model="m",
                                 org_id=ORG, cache=False)


@pytest.mark.asyncio
async def test_default_no_limits_reads_nothing_and_blocks_nothing(world):
    _, reader = world
    reader.totals[(ORG, "agents", None)] = 10_000.0
    configure_spend_guard(reader=reader, limits={})
    with llm_usage_context(product="agents"):
        assert await _call() == "ok"
    assert reader.reads == 0


@pytest.mark.asyncio
async def test_observe_mode_logs_would_block_and_lets_the_call_through(world, caplog):
    fake, reader = world
    reader.totals[(ORG, "agents", None)] = 50.0
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0)})  # default mode observe
    with caplog.at_level(logging.WARNING), llm_usage_context(product="agents"):
        assert await _call() == "ok"
    assert any("llm.spend_guard.would_block" in r.getMessage() for r in caplog.records)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_enforce_mode_refuses_before_the_provider_is_called(world):
    fake, reader = world
    reader.totals[(ORG, "agents", None)] = 50.0
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")})
    with llm_usage_context(product="agents"), pytest.raises(SpendCeilingExceeded) as exc:
        await _call()
    assert exc.value.status_code == 429
    assert fake.calls == []


@pytest.mark.asyncio
async def test_enforce_under_the_limit_passes(world):
    _, reader = world
    reader.totals[(ORG, "agents", None)] = 1.0
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")})
    with llm_usage_context(product="agents"):
        assert await _call() == "ok"


@pytest.mark.asyncio
async def test_other_surfaces_are_untouched_by_a_surface_limit(world):
    _, reader = world
    reader.totals[(ORG, "agents", None)] = 50.0
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")})
    with llm_usage_context(product="social-wiring"):
        assert await _call() == "ok"
    assert reader.reads == 0


@pytest.mark.asyncio
async def test_feature_specific_limit_wins_over_the_product_limit(world):
    _, reader = world
    reader.totals[(ORG, "agents", "relatorio")] = 50.0
    configure_spend_guard(reader=reader, limits={
        "agents": SurfaceLimit("agents", 1000.0, "enforce"),
        "agents:relatorio": SurfaceLimit("agents:relatorio", 10.0, "enforce"),
    })
    with llm_usage_context(product="agents", feature="relatorio"), pytest.raises(SpendCeilingExceeded):
        await _call()


@pytest.mark.asyncio
async def test_spend_read_is_cached_within_the_ttl(world):
    _, reader = world
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")})
    with llm_usage_context(product="agents"):
        await _call()
        await _call()
    assert reader.reads == 1


@pytest.mark.asyncio
async def test_enforce_failed_read_with_no_last_known_is_refused_loudly(world, caplog):
    _, reader = world
    reader.fail_with = RuntimeError("db down")
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")})
    with caplog.at_level(logging.ERROR), llm_usage_context(product="agents"), pytest.raises(SpendCeilingUnverifiable):
        await _call()
    assert any(r.levelname == "ERROR" for r in caplog.records)


@pytest.mark.asyncio
async def test_enforce_failed_read_serves_a_fresh_last_known_value(world, monkeypatch):
    _, reader = world
    t = [0.0]
    configure_spend_guard(
        reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")}, clock=lambda: t[0])
    with llm_usage_context(product="agents"):
        await _call()           # healthy read, cached
        t[0] += 31              # TTL passed -> re-read
        reader.fail_with = RuntimeError("blip")
        assert await _call() == "ok"   # last-known (1 USD < 10) keeps the surface up
        t[0] += 10_000          # last-known is stale now
        with pytest.raises(SpendCeilingUnverifiable):
            await _call()


@pytest.mark.asyncio
async def test_observe_failed_read_logs_error_and_proceeds(world, caplog):
    _, reader = world
    reader.fail_with = RuntimeError("db down")
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0)})
    with caplog.at_level(logging.ERROR), llm_usage_context(product="agents"):
        assert await _call() == "ok"
    assert any("observe mode" in r.getMessage() for r in caplog.records)


def test_malformed_limits_are_logged_not_silent(caplog):
    with caplog.at_level(logging.ERROR):
        assert spend_guard.parse_limits("{not json") == {}
        out = spend_guard.parse_limits(json.dumps({"a": {"usd": 5, "mode": "nope"}, "b": {"usd": 2}}))
    assert list(out) == ["b"] and out["b"].mode == "observe"
    assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 2


@pytest.mark.asyncio
async def test_guard_covers_embeddings_vision_and_audio_paths(world):
    from noctusai_lib.integrations.llm import generate_embedding, transcribe_audio

    fake, reader = world
    reader.totals[(ORG, "agents", None)] = 50.0
    configure_spend_guard(reader=reader, limits={"agents": SurfaceLimit("agents", 10.0, "enforce")})
    with llm_usage_context(product="agents"):
        with pytest.raises(SpendCeilingExceeded):
            await generate_embedding("x", provider="fake-guard", org_id=ORG)
        with pytest.raises(SpendCeilingExceeded):
            await transcribe_audio(b"x", provider="fake-guard", org_id=ORG)
