"""Redis auth seam: resolution, redaction, fail-closed, factories, limiter URI.

No real Redis: factories are built (lazy connection) and inspected, never
connected. -> KB § PATTERNS/backend/redis-auth-seam.md
"""
from __future__ import annotations

import fakeredis
import pytest

from noctusai_lib.api.rate_limit import create_limiter, resolve_limiter_storage_uri
from noctusai_lib.integrations.redis import (
    RedisAuthRequired,
    make_async_redis_client,
    make_redis_client,
    redact_redis_url,
    redis_connection_url,
)

# NOCTUS_RATE_LIMIT_MEMORY_ONLY: the seed pytest plugin sets it for every test
# session; these tests exercise the Redis-backed path, so they switch it off.
_ENV = ("REDIS_URL", "REDIS_USERNAME", "REDIS_PASSWORD", "REDIS_REQUIRE_AUTH",
        "NOCTUS_RATE_LIMIT_MEMORY_ONLY")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)


def _kw(client):
    return client.connection_pool.connection_kwargs


class TestConnectionUrl:
    def test_no_creds_passthrough(self):
        assert redis_connection_url("redis://h:6379/0") == "redis://h:6379/0"

    def test_env_url_fallback(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://envhost:6379")
        assert redis_connection_url() == "redis://envhost:6379"

    def test_missing_url_raises(self):
        with pytest.raises(ValueError):
            redis_connection_url()

    def test_split_creds_merge_and_quote(self):
        url = redis_connection_url("redis://h:6379/2", username="app", password="p@ss/w:d")
        assert url == "redis://app:p%40ss%2Fw%3Ad@h:6379/2"

    def test_password_only(self):
        assert redis_connection_url("redis://h:6379", password="pw") == "redis://:pw@h:6379"

    def test_env_split_creds(self, monkeypatch):
        monkeypatch.setenv("REDIS_USERNAME", "u")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        assert redis_connection_url("rediss://h:6380") == "rediss://u:pw@h:6380"

    def test_url_creds_win_over_split(self):
        url = redis_connection_url("redis://urluser:urlpw@h", username="x", password="y")
        assert url == "redis://urluser:urlpw@h"


class TestRedact:
    def test_masks_password_keeps_user(self):
        assert redact_redis_url("redis://app:secret@h:6379/0") == "redis://app:***@h:6379/0"

    def test_no_password_unchanged(self):
        assert redact_redis_url("redis://h:6379") == "redis://h:6379"

    def test_password_only(self):
        assert redact_redis_url("redis://:secret@h") == "redis://:***@h"


class TestRequireAuth:
    def test_raises_without_credentials(self):
        with pytest.raises(RedisAuthRequired):
            make_redis_client("redis://h", require_auth=True)
        with pytest.raises(RedisAuthRequired):
            redis_connection_url("redis://h", require_auth=True)

    def test_env_flag_raises(self, monkeypatch):
        monkeypatch.setenv("REDIS_REQUIRE_AUTH", "true")
        with pytest.raises(RedisAuthRequired):
            make_async_redis_client("redis://h")

    def test_satisfied_by_url_or_split(self):
        make_redis_client("redis://u:p@h", require_auth=True)
        make_redis_client("redis://h", password="p", require_auth=True)


class TestFactories:
    def test_sync_passes_split_creds_as_kwargs(self):
        kw = _kw(make_redis_client("redis://h:6379/1", username="app", password="pw"))
        assert (kw["username"], kw["password"], kw["db"]) == ("app", "pw", 1)
        assert kw["decode_responses"] is True

    def test_async_factory_is_asyncio_client_with_creds(self):
        from redis.asyncio import Redis as AsyncRedis

        c = make_async_redis_client("redis://h", username="app", password="pw")
        assert isinstance(c, AsyncRedis)
        assert _kw(c)["password"] == "pw"

    def test_url_creds_used_when_present(self):
        kw = _kw(make_redis_client("redis://a:b@h", username="x", password="y"))
        assert (kw["username"], kw["password"]) == ("a", "b")

    def test_kwargs_forwarded_and_decode_opt_out(self):
        kw = _kw(make_redis_client("redis://h", decode_responses=False, socket_connect_timeout=2))
        assert kw["decode_responses"] is False and kw["socket_connect_timeout"] == 2


class TestLimiterStorageUri:
    def test_storage_uri_carries_creds_when_reachable(self, monkeypatch):
        monkeypatch.setenv("REDIS_USERNAME", "app")
        monkeypatch.setenv("REDIS_PASSWORD", "pw")
        uri = resolve_limiter_storage_uri(
            "redis://h:6379", probe_client=fakeredis.FakeStrictRedis()
        )
        assert uri == "redis://app:pw@h:6379"

    def test_unreachable_falls_back_without_leaking_password(self, caplog):
        with caplog.at_level("WARNING"):
            uri = resolve_limiter_storage_uri("redis://app:topsecret@127.0.0.1:1")
        assert uri is None
        assert "topsecret" not in caplog.text

    def test_no_url_means_in_memory(self):
        assert resolve_limiter_storage_uri(None) is None
        assert create_limiter(redis_url=None) is not None

    def test_require_auth_is_not_swallowed(self, monkeypatch):
        monkeypatch.setenv("REDIS_REQUIRE_AUTH", "1")
        with pytest.raises(RedisAuthRequired):
            create_limiter(redis_url="redis://127.0.0.1:1")


def test_hermetic_seam_forces_in_memory_even_when_redis_is_reachable(monkeypatch):
    """The seed pytest plugin's seam: per-process counters, never a shared Redis
    (2026-10-10 — a reachable developer Redis let parallel test processes reset
    each other's rate-limit windows)."""
    from noctusai_lib.api.rate_limit import MEMORY_ONLY_VAR

    monkeypatch.setenv(MEMORY_ONLY_VAR, "1")

    class _Reachable:
        def ping(self):
            return True

    assert resolve_limiter_storage_uri("redis://127.0.0.1:6379", probe_client=_Reachable()) is None

