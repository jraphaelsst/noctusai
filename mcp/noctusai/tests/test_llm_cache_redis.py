"""Phase 11 — Redis cache backend tests.

Uses `fakeredis.aioredis.FakeRedis` so no live Redis server is required.
The fake implements the subset of commands we use (`GET`, `SETEX`, `DEL`,
`SCAN`) with real Redis semantics.
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


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def redis_backend(fake_redis):
    from noctusai_lib.llm.backends import RedisCacheBackend
    return RedisCacheBackend(client=fake_redis)


# ── Basic CacheBackend Protocol ─────────────────────────────────

class TestBasicProtocol:
    def test_set_and_get_round_trip(self, redis_backend):
        async def run():
            await redis_backend.setex("k1", 60, "hello")
            assert await redis_backend.get("k1") == "hello"

        asyncio.run(run())

    def test_get_miss_returns_none(self, redis_backend):
        async def run():
            assert await redis_backend.get("missing") is None

        asyncio.run(run())

    def test_delete_returns_count(self, redis_backend):
        async def run():
            await redis_backend.setex("k1", 60, "v1")
            await redis_backend.setex("k2", 60, "v2")
            deleted = await redis_backend.delete("k1", "k2", "missing")
            assert deleted == 2
            assert await redis_backend.get("k1") is None

        asyncio.run(run())

    def test_delete_nothing_returns_zero(self, redis_backend):
        async def run():
            assert await redis_backend.delete() == 0

        asyncio.run(run())


# ── SCAN-based iteration ────────────────────────────────────────

class TestScanKeys:
    def test_scan_yields_matching_keys(self, redis_backend):
        async def run():
            # Mix of prefixes so SCAN pattern has to actually filter
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:aaa", 60, "x")
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:bbb", 60, "y")
            await redis_backend.setex("llm:therapy:openai:gpt-4o:v1:ccc", 60, "z")
            found = []
            async for k in redis_backend.scan_keys("llm:erp:openai:gpt-4o-mini:*"):
                found.append(k)
            assert sorted(found) == [
                "llm:erp:openai:gpt-4o-mini:v1:aaa",
                "llm:erp:openai:gpt-4o-mini:v1:bbb",
            ]

        asyncio.run(run())

    def test_scan_empty_pattern_yields_nothing(self, redis_backend):
        async def run():
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:a", 60, "x")
            found = []
            async for k in redis_backend.scan_keys("nonexistent:*"):
                found.append(k)
            assert found == []

        asyncio.run(run())


# ── Prefix flush ────────────────────────────────────────────────

class TestFlushPrefix:
    def test_flush_deletes_matching_and_preserves_others(self, redis_backend):
        async def run():
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:a", 60, "x")
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:b", 60, "y")
            await redis_backend.setex("llm:therapy:openai:gpt-4o:v1:c", 60, "z")

            await redis_backend.flush_prefix("llm:erp:openai:gpt-4o-mini:")

            # Matching keys are gone
            assert await redis_backend.get("llm:erp:openai:gpt-4o-mini:v1:a") is None
            assert await redis_backend.get("llm:erp:openai:gpt-4o-mini:v1:b") is None
            # Non-matching preserved
            assert await redis_backend.get("llm:therapy:openai:gpt-4o:v1:c") == "z"

        asyncio.run(run())

    def test_flush_empty_returns_zero_count(self, redis_backend):
        async def run():
            result = await redis_backend.flush_prefix("llm:nothing:")
            assert result == 0

        asyncio.run(run())

    def test_flush_chunks_large_keyspaces(self, redis_backend):
        """Insert 500 keys under one prefix; flush should still delete all."""
        async def run():
            for i in range(500):
                await redis_backend.setex(f"llm:bulk:openai:gpt-4o-mini:v1:{i}", 60, str(i))
            await redis_backend.flush_prefix("llm:bulk:openai:gpt-4o-mini:")
            found = []
            async for k in redis_backend.scan_keys("llm:bulk:*"):
                found.append(k)
            assert found == []

        asyncio.run(run())


# ── Integration: flush_for_model dispatches to RedisCacheBackend ────

class TestFlushForModelDispatch:
    def test_dispatches_to_redis_flush_prefix(self, redis_backend):
        from noctusai_lib.llm.cache import flush_for_model

        async def run():
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:a", 60, "x")
            await redis_backend.setex("llm:erp:openai:gpt-4o-mini:v1:b", 60, "y")
            # `flush_for_model` must see `flush_prefix` on the backend and
            # call it (rather than fall back to the 0 branch it uses for
            # unknown backends).
            await flush_for_model(
                redis_backend, product="erp", provider="openai", model="gpt-4o-mini",
            )
            assert await redis_backend.get("llm:erp:openai:gpt-4o-mini:v1:a") is None

        asyncio.run(run())


# ── Construction guards ─────────────────────────────────────────

class TestConstruction:
    def test_requires_url_or_client(self):
        from noctusai_lib.llm.backends import RedisCacheBackend

        with pytest.raises(ValueError, match="url"):
            RedisCacheBackend()

    def test_from_url_lazily(self, fake_redis):
        """Constructor should NOT open the connection immediately."""
        from noctusai_lib.llm.backends import RedisCacheBackend

        backend = RedisCacheBackend(url="redis://localhost:6379/0")
        # No connection attempt yet — _client is None
        assert backend._client is None

    def test_from_client_skips_lazy_open(self, fake_redis):
        from noctusai_lib.llm.backends import RedisCacheBackend

        backend = RedisCacheBackend(client=fake_redis)
        assert backend._client is fake_redis


# ── default_llm_config wires Redis when redis_url is given ─────

class TestDefaultConfigAutoWires:
    def test_redis_url_enables_cache(self):
        _SEED = Path(__file__).resolve().parents[3] / "seed" / "backend" / "framework"
        if str(_SEED) not in sys.path:
            sys.path.insert(0, str(_SEED))
        from noctusai_seed.llm_defaults import default_llm_config

        cfg = default_llm_config(redis_url="redis://localhost:6379/0")
        assert cfg.cache_enabled is True
        assert cfg.cache_backend is not None
        # The backend is a RedisCacheBackend — confirm by attribute (not isinstance
        # to avoid cross-import in this test sweep).
        assert type(cfg.cache_backend).__name__ == "RedisCacheBackend"

    def test_no_redis_url_keeps_cache_disabled(self):
        _SEED = Path(__file__).resolve().parents[3] / "seed" / "backend" / "framework"
        if str(_SEED) not in sys.path:
            sys.path.insert(0, str(_SEED))
        from noctusai_seed.llm_defaults import default_llm_config

        cfg = default_llm_config()
        assert cfg.cache_enabled is False
        assert cfg.cache_backend is None
