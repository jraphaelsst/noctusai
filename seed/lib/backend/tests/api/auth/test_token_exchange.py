"""Tests for the ``SupabaseTokenExchanger`` + Fake + factory (SEC-1/2).

The exchange logic is exercised WITHOUT a live Supabase by injecting a fake
``refresh_fn`` (the SEC-1 seam — the real one runs on a throwaway anon
client, verified in prod shape in Slice 4). Redis (store + per-session lock)
is ``fakeredis``. A controllable ``clock`` drives the near-expiry logic
deterministically for the sequential tests; the concurrency test uses the
real clock so the wait-for-publish poll terminates.
"""

from __future__ import annotations

import asyncio
import threading
import time
from uuid import uuid4

import fakeredis.aioredis
import pytest

from noctusai_lib.api.auth.session import (
    FakeSessionStore,
    FakeTokenExchanger,
    InvalidCredentialsError,
    RedisSessionStore,
    SupabaseTokenExchanger,
    make_token_exchanger,
)
from noctusai_lib.api.auth.session.token_exchange import (
    RefreshResult,
    TokenExchangeError,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _client():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class _FixedClock:
    """A settable clock for deterministic near-expiry tests."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _make(store, client, *, refresh_fn, clock=None, **kw):
    return SupabaseTokenExchanger(
        store,
        lock_client=client,
        refresh_fn=refresh_fn,
        clock=clock or time.time,
        **kw,
    )


# ── cache-first behaviour (SEC-2) ────────────────────────────────────


def test_cached_token_returned_without_refresh():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        # Cache a token that expires well beyond the skew window.
        await store.write_tokens(
            sid, refresh_token="rt0", access_token="cached-at",
            access_expires_at=int(clock.now) + 3600,
        )
        calls = []

        def refresh_fn(rt):  # must NOT be called
            calls.append(rt)
            return RefreshResult("x", "y", int(clock.now) + 3600)

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        assert await ex.access_token_for(sid) == "cached-at"
        assert calls == []

    _run(_t())


def test_refreshes_when_no_access_token_cached():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        calls = []

        def refresh_fn(rt):
            calls.append(rt)
            return RefreshResult("fresh-at", "rt1", int(clock.now) + 3600)

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        assert await ex.access_token_for(sid) == "fresh-at"
        assert calls == ["rt0"]  # refreshed with the stored refresh token

    _run(_t())


def test_refreshes_when_cached_token_near_expiry():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        # Cached token expires in 30s — inside the default 60s skew.
        await store.write_tokens(
            sid, refresh_token="rt0", access_token="stale-at",
            access_expires_at=int(clock.now) + 30,
        )
        calls = []

        def refresh_fn(rt):
            calls.append(rt)
            return RefreshResult("new-at", "rt1", int(clock.now) + 3600)

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        assert await ex.access_token_for(sid) == "new-at"
        assert calls == ["rt0"]

    _run(_t())


def test_rotated_refresh_token_written_back():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )

        def refresh_fn(rt):
            return RefreshResult("at1", "ROTATED-rt", int(clock.now) + 3600)

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        await ex.access_token_for(sid)
        tokens = await store.read_tokens(sid)
        assert tokens.refresh_token == "ROTATED-rt"      # SEC-2 write-back
        assert tokens.access_token == "at1"
        assert tokens.access_expires_at == int(clock.now) + 3600

    _run(_t())


def test_second_call_uses_cache_from_first_refresh():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        calls = []

        def refresh_fn(rt):
            calls.append(rt)
            return RefreshResult("at1", "rt1", int(clock.now) + 3600)

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        await ex.access_token_for(sid)
        await ex.access_token_for(sid)
        assert len(calls) == 1  # second call hit the cache

    _run(_t())


# ── error paths ──────────────────────────────────────────────────────


def test_no_session_raises_invalid_credentials():
    async def _t():
        client = _client()
        store = RedisSessionStore(client=client)
        ex = _make(store, client, refresh_fn=lambda rt: RefreshResult("a", "b", 1))
        with pytest.raises(InvalidCredentialsError):
            await ex.access_token_for("no-such-session")

    _run(_t())


def test_expired_refresh_token_propagates_as_invalid_credentials():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )

        def refresh_fn(rt):
            raise InvalidCredentialsError("refresh token revoked")

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        with pytest.raises(InvalidCredentialsError):
            await ex.access_token_for(sid)

    _run(_t())


def test_refresh_transport_failure_raises_exchange_error():
    async def _t():
        clock = _FixedClock()
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )

        def refresh_fn(rt):
            raise ConnectionError("supabase unreachable")

        ex = _make(store, client, refresh_fn=refresh_fn, clock=clock)
        with pytest.raises(TokenExchangeError):
            await ex.access_token_for(sid)

    _run(_t())


# ── SEC-2 core: concurrent calls collapse to ONE refresh ─────────────


def test_concurrent_calls_trigger_single_refresh():
    """The whole point of the lock: N simultaneous requests for a session
    whose token needs refreshing must fire exactly ONE upstream refresh
    (a second concurrent refresh replays the rotating token → Supabase
    reuse-detection revokes the family → mass forced logout)."""

    async def _t():
        client = _client()
        store = RedisSessionStore(client=client)
        sid = await store.create(
            user_id=uuid4(), org_id=uuid4(), supabase_refresh_token="rt0"
        )
        count = {"n": 0}
        lock = threading.Lock()

        def refresh_fn(rt):
            with lock:
                count["n"] += 1
            time.sleep(0.15)  # widen the race window
            return RefreshResult("shared-at", "rt1", int(time.time()) + 3600)

        # Real clock so the contended waiters' poll loop terminates.
        ex = _make(store, client, refresh_fn=refresh_fn)
        results = await asyncio.gather(
            *[ex.access_token_for(sid) for _ in range(6)]
        )
        assert count["n"] == 1                       # exactly one refresh
        assert all(r == "shared-at" for r in results)  # everyone got the token

    _run(_t())


# ── FakeTokenExchanger ───────────────────────────────────────────────


def test_fake_exchanger_returns_token_and_records_calls():
    async def _t():
        ex = FakeTokenExchanger(token="tok")
        assert await ex.access_token_for("s1") == "tok"
        assert await ex.access_token_for("s2") == "tok"
        assert ex.calls == ["s1", "s2"]

    _run(_t())


def test_fake_exchanger_per_session_tokens():
    async def _t():
        ex = FakeTokenExchanger(tokens={"s1": "a", "s2": "b"})
        assert await ex.access_token_for("s1") == "a"
        assert await ex.access_token_for("s2") == "b"
        assert await ex.access_token_for("other") == "fake-access-token"

    _run(_t())


# ── factory ──────────────────────────────────────────────────────────


def test_factory_without_lock_returns_fake():
    ex = make_token_exchanger(FakeSessionStore())
    assert isinstance(ex, FakeTokenExchanger)


def test_factory_lock_without_refresh_capability_raises():
    with pytest.raises(ValueError):
        make_token_exchanger(FakeSessionStore(), lock_client=_client())


def test_factory_builds_real_with_refresh_fn():
    ex = make_token_exchanger(
        FakeSessionStore(),
        lock_client=_client(),
        refresh_fn=lambda rt: RefreshResult("a", "b", 1),
    )
    assert isinstance(ex, SupabaseTokenExchanger)


def test_factory_builds_real_with_supabase_creds():
    ex = make_token_exchanger(
        FakeSessionStore(),
        lock_client=_client(),
        supabase_url="https://x.supabase.co",
        supabase_anon_key="anon-key",
    )
    assert isinstance(ex, SupabaseTokenExchanger)
