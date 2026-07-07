"""Tests for the Redis-backed SessionStore real adapter + factory.

Uses ``fakeredis.aioredis.FakeRedis`` as the injected client so no live
Redis is required. ``fakeredis`` binds to the event loop it is first used
in, so each test does all of its create/lookup/delete work inside a SINGLE
coroutine driven once by ``_run`` (one loop per test).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import fakeredis.aioredis
import pytest

from noctusai_lib.api.auth.session import (
    FakeSessionStore,
    RedisSessionStore,
    make_session_store,
)


def _run(coro):
    """Run a coroutine synchronously from a sync test body."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _new_store() -> RedisSessionStore:
    """Build a Redis store over a fresh fakeredis client (call INSIDE a coroutine)."""
    return RedisSessionStore(client=fakeredis.aioredis.FakeRedis(decode_responses=True))


# ── RedisSessionStore ────────────────────────────────────────────────


def test_create_then_lookup_returns_user_ctx():
    async def _t():
        store = _new_store()
        user_id, org_id = uuid4(), uuid4()
        session_id = await store.create(
            user_id=user_id, org_id=org_id, supabase_refresh_token="rt-abc"
        )
        ctx = await store.lookup(session_id)
        assert ctx is not None
        assert ctx.user_id == user_id
        assert ctx.org_id == org_id
        assert ctx.caller_kind == "user"
        assert ctx.raw_token == session_id  # opaque id, never the refresh token
        assert ctx.api_token_id is None

    _run(_t())


def test_refresh_token_never_surfaces_in_context():
    async def _t():
        store = _new_store()
        session_id = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="super-secret-rt"
        )
        ctx = await store.lookup(session_id)
        assert "super-secret-rt" not in str(ctx)

    _run(_t())


def test_lookup_absent_returns_none():
    async def _t():
        store = _new_store()
        assert await store.lookup("does-not-exist") is None

    _run(_t())


def test_delete_makes_lookup_return_none():
    async def _t():
        store = _new_store()
        session_id = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt"
        )
        await store.delete(session_id)
        assert await store.lookup(session_id) is None

    _run(_t())


def test_expired_session_lookup_returns_none():
    async def _t():
        store = _new_store()
        session_id = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt", ttl_seconds=1
        )
        # Force the key to expire, then confirm lookup treats it as absent.
        client = store._get_client()
        await client.pexpire(store._key(session_id), 1)  # 1ms
        await asyncio.sleep(0.02)
        assert await store.lookup(session_id) is None

    _run(_t())


def test_delete_absent_is_noop():
    async def _t():
        store = _new_store()
        await store.delete("nope")  # must not raise

    _run(_t())


def test_requires_url_or_client():
    with pytest.raises(ValueError):
        RedisSessionStore()


# ── factory ──────────────────────────────────────────────────────────


def test_factory_none_url_returns_fake():
    assert isinstance(make_session_store(None), FakeSessionStore)


def test_factory_redis_url_returns_redis():
    assert isinstance(make_session_store("redis://localhost:6379/0"), RedisSessionStore)


def test_factory_injected_client_returns_redis_and_works():
    async def _t():
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = make_session_store(None, client=fake)
        assert isinstance(store, RedisSessionStore)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt"
        )
        assert await store.lookup(sid) is not None

    _run(_t())
