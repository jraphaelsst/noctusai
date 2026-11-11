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


# ── key hygiene (security review r2, P2-1): the Redis KEY must not be the bearer secret ─────────


def _legacy_key(sid: str) -> str:
    return f"nai_session:{sid}"


def test_session_is_keyed_by_sha256_never_the_raw_cookie_value():
    import hashlib

    async def _t():
        store = _new_store()
        client = store._get_client()
        sid = await store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt")
        keys = [k async for k in client.scan_iter(match="nai_session:*")]
        assert keys == [f"nai_session:{hashlib.sha256(sid.encode()).hexdigest()}"]
        assert sid not in keys[0]

    _run(_t())


def test_legacy_raw_key_is_read_then_migrated_with_ttl_preserved():
    """Deploying the hashed key must log nobody out: a pre-existing raw-keyed record still resolves."""

    async def _t():
        store = _new_store()
        client = store._get_client()
        sid = await store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt-legacy")
        hashed = store._key(sid)
        # Re-create the pre-deploy state: the same record under the RAW key.
        raw = await client.get(hashed)
        await client.delete(hashed)
        await client.set(_legacy_key(sid), raw, ex=5000)

        ctx = await store.lookup(sid)  # hashed miss -> legacy hit -> migrate
        assert ctx is not None and ctx.raw_token == sid
        assert await client.exists(_legacy_key(sid)) == 0
        assert await client.exists(hashed) == 1
        assert 4000 < await client.ttl(hashed) <= 5000  # TTL survived the migration
        assert (await store.read_tokens(sid)).refresh_token == "rt-legacy"

    _run(_t())


def test_legacy_record_survives_every_operation_and_delete_clears_both():
    async def _t():
        store = _new_store()
        client = store._get_client()
        sid = await store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt")
        raw = await client.get(store._key(sid))
        await client.delete(store._key(sid))
        await client.set(_legacy_key(sid), raw, ex=5000)
        await store.write_tokens(sid, refresh_token="rt2", access_token="at", access_expires_at=1)
        assert (await store.read_tokens(sid)).refresh_token == "rt2"
        # a second legacy record: refresh_ttl + delete
        sid2 = "L" * 43  # legacy shape: token_urlsafe(32) is 43 chars
        await client.set(_legacy_key(sid2), raw, ex=100)
        await store.refresh_ttl(sid2, 7000)
        assert await client.ttl(store._key(sid2)) > 6000
        await client.set(_legacy_key(sid2), raw, ex=100)  # both forms present
        await store.delete(sid2)
        assert await client.exists(store._key(sid2), _legacy_key(sid2)) == 0

    _run(_t())


# ── P1-A (security re-check r3): the dual read must NOT turn a hashed key name into a cookie ─────
# The Redis key `nai_session:<H>` (H = sha256(session_id), visible in SCAN / ACL LOG / a dump) is exactly
# what the dual read RENAMEd onto sha256(H) when a request presented H as its cookie: the attacker got the
# victim's session and the victim was logged out. Only ids with the legacy token_urlsafe(32) shape may adopt.

import hashlib  # noqa: E402


def _victim_and_leaked_hash(store):
    async def _mk():
        sid = await store.create(user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt-victim", ttl_seconds=5000)
        return sid, hashlib.sha256(sid.encode()).hexdigest()

    return _mk()


def test_presenting_the_leaked_hash_never_resolves_and_never_logs_the_victim_out():
    async def _t():
        store = _new_store()
        client = store._get_client()
        sid, leaked = await _victim_and_leaked_hash(store)
        assert await store.lookup(leaked) is None
        assert await client.exists(store._key(sid)) == 1  # victim's key untouched
        assert (await store.lookup(sid)) is not None and (await store.read_tokens(sid)).refresh_token == "rt-victim"

    _run(_t())


def test_leaked_hash_cannot_refresh_or_write_the_victims_session():
    async def _t():
        store = _new_store()
        client = store._get_client()
        sid, leaked = await _victim_and_leaked_hash(store)
        before = await client.get(store._key(sid))
        await store.refresh_ttl(leaked, 9999)
        await store.write_tokens(leaked, refresh_token="attacker", access_token="x", access_expires_at=1)
        assert await client.get(store._key(sid)) == before  # record unchanged
        assert 4000 < await client.ttl(store._key(sid)) <= 5000  # TTL not extended
        assert await client.exists(f"nai_session:{hashlib.sha256(leaked.encode()).hexdigest()}") == 0  # nothing minted
        assert await store.lookup(sid) is not None

    _run(_t())


def test_only_legacy_shaped_ids_adopt():
    from noctusai_lib.api.auth.session.store import is_valid_session_id

    import secrets

    assert is_valid_session_id(secrets.token_urlsafe(32))
    for bad in ("a" * 64, hashlib.sha256(b"x").hexdigest(), "short", "", "a" * 44, "has space" + "a" * 34, "é" * 43):
        assert not is_valid_session_id(bad)


def test_leaked_hash_cannot_delete_the_victims_session():
    async def _t():
        store = _new_store()
        client = store._get_client()
        sid, leaked = await _victim_and_leaked_hash(store)
        await store.delete(leaked)
        assert await client.exists(store._key(sid)) == 1 and await store.lookup(sid) is not None

    _run(_t())
