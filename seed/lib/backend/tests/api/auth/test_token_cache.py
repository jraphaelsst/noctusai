"""Verified-token cache — the 30 s positive cache in front of Supabase Auth `get_user`.

Pins the security contract: sha256 keys (never the raw token), positive results
only, never past the token's own `exp`, bounded LRU, TTL honoured, revocation
bounded by the TTL, explicit logout eviction.
KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import asyncio
import time
import uuid
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth import (
    make_get_current_user_ungated,
    validate_bearer_token,
)
from noctusai_lib.api.auth import token_cache as tc
from noctusai_lib.api.auth.token_cache import TokenCache, discard_token_everywhere, token_digest


def _jwt(exp_in: float | None = 3600, sub: str = "u1") -> str:
    claims = {"sub": sub}
    if exp_in is not None:
        claims["exp"] = int(time.time() + exp_in)
    return pyjwt.encode(claims, "x" * 32, algorithm="HS256")


class _Auth:
    def __init__(self, user=None, exc=None, delay=0.0):
        self.calls = 0
        self._user, self._exc, self._delay = user, exc, delay

    def get_user(self, token):
        self.calls += 1
        if self._delay:
            time.sleep(self._delay)
        if self._exc:
            raise self._exc
        return SimpleNamespace(user=self._user)


class _User:
    def __init__(self, id="u1"):
        self.id = id
        self.user_metadata = {"a": 1}


def _client(**kw):
    return SimpleNamespace(auth=_Auth(**kw))


@pytest.fixture(autouse=True)
def _default_ttl():
    tc.configure_token_cache(None)
    yield
    tc.configure_token_cache(None)


class TestCacheContract:
    def test_default_ttl_is_30_seconds(self):
        assert tc.DEFAULT_TTL_S == 30.0 and TokenCache().ttl_s == 30.0

    def test_second_validation_within_ttl_skips_the_provider(self):
        cache, client, tok = TokenCache(), _client(user=_User()), _jwt()
        assert validate_bearer_token(client, tok, cache=cache).id == "u1"
        assert validate_bearer_token(client, tok, cache=cache).id == "u1"
        assert client.auth.calls == 1

    def test_entry_expires_after_the_ttl(self, monkeypatch):
        cache, client, tok = TokenCache(ttl_s=30), _client(user=_User()), _jwt()
        now = [1000.0]
        monkeypatch.setattr(tc.time, "monotonic", lambda: now[0])
        validate_bearer_token(client, tok, cache=cache)
        now[0] += 29.9
        validate_bearer_token(client, tok, cache=cache)
        assert client.auth.calls == 1
        now[0] += 0.2  # 30.1 s after the put
        validate_bearer_token(client, tok, cache=cache)
        assert client.auth.calls == 2

    def test_revoked_session_keeps_working_at_most_ttl_then_is_rejected(self, monkeypatch):
        """The accepted trade-off, as a test: revocation latency is bounded by the TTL."""
        cache, tok = TokenCache(ttl_s=30), _jwt()
        now = [0.0]
        monkeypatch.setattr(tc.time, "monotonic", lambda: now[0])
        ok = _client(user=_User())
        validate_bearer_token(ok, tok, cache=cache)
        revoked = SimpleNamespace(auth=_Auth(exc=_Rejected()))
        now[0] += 10
        assert validate_bearer_token(revoked, tok, cache=cache).id == "u1"  # still served
        now[0] += 25  # 35 s after the put
        with pytest.raises(HTTPException) as e:
            validate_bearer_token(revoked, tok, cache=cache)
        assert e.value.status_code == 401

    def test_failures_are_never_cached(self):
        cache, tok = TokenCache(), _jwt()
        bad = _client(exc=_Rejected())
        for _ in range(2):
            with pytest.raises(HTTPException):
                validate_bearer_token(bad, tok, cache=cache)
        assert bad.auth.calls == 2 and len(cache) == 0
        # no user from the provider => 401 and not cached
        empty = _client(user=None)
        with pytest.raises(HTTPException):
            validate_bearer_token(empty, tok, cache=cache)
        assert len(cache) == 0
        # a provider outage (503) is not cached either, and a recovery works at once
        down = _client(exc=ConnectionError("x"))
        with pytest.raises(HTTPException) as e:
            validate_bearer_token(down, tok, cache=cache)
        assert e.value.status_code == 503 and len(cache) == 0
        assert validate_bearer_token(_client(user=_User()), tok, cache=cache).id == "u1"

    def test_key_is_sha256_never_the_raw_token(self):
        cache, tok = TokenCache(), _jwt()
        cache.put(tok, _User())
        keys = list(cache._store)
        assert keys == [token_digest(tok)] and tok not in keys[0]
        assert tok not in repr(cache._store)

    def test_never_cached_past_the_tokens_own_exp(self, monkeypatch):
        cache = TokenCache(ttl_s=30)
        short = _jwt(exp_in=6)  # exp is whole seconds: lifetime is 5..6 s
        now = [0.0]
        monkeypatch.setattr(tc.time, "monotonic", lambda: now[0])
        assert cache.put(short, _User())
        now[0] += 4.0
        assert cache.get(short) is not None
        now[0] += 2.1  # token expired by ~6 s even though ttl is 30
        assert cache.get(short) is None

    def test_expired_or_exp_less_token_is_not_stored(self):
        cache = TokenCache()
        assert cache.put(_jwt(exp_in=-10), _User()) is False
        assert cache.put(_jwt(exp_in=None), _User()) is False
        assert cache.put("not-a-jwt", _User()) is False
        assert len(cache) == 0

    def test_lru_cap(self):
        cache = TokenCache(max_entries=3)
        toks = [_jwt(sub=f"s{i}") for i in range(4)]
        for t in toks[:3]:
            cache.put(t, _User())
        cache.get(toks[0])  # touch => toks[1] is now the oldest
        cache.put(toks[3], _User())
        assert len(cache) == 3
        assert cache.get(toks[1]) is None and cache.get(toks[0]) is not None

    def test_ttl_zero_disables(self):
        tc.configure_token_cache(0)
        cache, client, tok = TokenCache(), _client(user=_User()), _jwt()
        validate_bearer_token(client, tok, cache=cache)
        validate_bearer_token(client, tok, cache=cache)
        assert client.auth.calls == 2 and len(cache) == 0

    def test_ttl_is_a_setting_not_a_constant(self):
        tc.configure_token_cache(5)
        assert TokenCache().ttl_s == 5
        tc.configure_token_cache("garbage")  # not a number => default, never a crash
        assert TokenCache().ttl_s == 30.0

    def test_cached_user_is_a_copy(self):
        cache, tok = TokenCache(), _jwt()
        cache.put(tok, _User())
        first = cache.get(tok)
        first.user_metadata["a"] = "tampered"
        assert cache.get(tok).user_metadata == {"a": 1}

    def test_logout_evicts_everywhere(self):
        # A unique subject: _jwt() is deterministic within a second, and every live cache in the
        # process (other tests' dependencies included) would otherwise also count as holding it.
        a, b, tok = TokenCache(), TokenCache(), _jwt(sub=f"logout-{uuid.uuid4()}")
        a.put(tok, _User())
        b.put(tok, _User())
        assert discard_token_everywhere(tok) == 2
        assert a.get(tok) is None and b.get(tok) is None


class _Rejected(Exception):
    status = 401


class TestTheDependencyDoesNotBlockTheLoop:
    def test_cache_hit_builds_no_client(self):
        built = []
        client = _client(user=_User())

        def factory():
            built.append(1)
            return client

        dep = make_get_current_user_ungated(factory)
        tok = _jwt()

        async def go():
            await dep(authorization=f"Bearer {tok}")
            await dep(authorization=f"Bearer {tok}")

        asyncio.run(go())
        assert client.auth.calls == 1 and len(built) == 1

    def test_slow_provider_calls_overlap_instead_of_serialising(self):
        """3 concurrent requests with a 0.3 s provider round-trip finish in ~0.3 s,
        not ~0.9 s (the measured staircase) — the sync call is off the event loop."""
        client = _client(user=_User(), delay=0.3)
        dep = make_get_current_user_ungated(lambda: client)
        toks = [_jwt(sub=f"s{i}") for i in range(3)]

        async def go():
            return await asyncio.gather(*(dep(authorization=f"Bearer {t}") for t in toks))

        t0 = time.perf_counter()
        out = asyncio.run(go())
        elapsed = time.perf_counter() - t0
        assert len(out) == 3 and client.auth.calls == 3
        assert elapsed < 0.7, f"serialised: {elapsed:.2f}s"

    def test_each_validator_has_its_own_cache(self):
        a = make_get_current_user_ungated(lambda: _client(user=_User()))
        b = make_get_current_user_ungated(lambda: _client(user=_User()))
        assert a.token_cache is not b.token_cache
