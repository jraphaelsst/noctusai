"""Tests for `app.services.conversation_rate_limit` — Phase 11 security hardening.

Verifies the per-conversation inbound rate limiter:
  * Allows the first N messages within the window.
  * Rejects the (N+1)-th message.
  * Counts isolate per `chat_id`.
  * Fail-open behaviour when Redis raises.
  * Window rollover resets the counter.
  * Empty chat_id is rejected loud.

Uses `make_fake_redis_client()` per `KB § PATTERNS/seed-fake-real-adapter.md`
— fakeredis exercises the same `incr` / `expire` code paths as real Redis.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.redis import make_fake_redis_client

from app.services.conversation_rate_limit import (
    RedisConversationRateLimiter,
    _reset_for_tests,
    configure_rate_limiter,
    get_rate_limiter,
)


@pytest.fixture(autouse=True)
def _reset_module():
    """Each test starts with no module-level limiter wired."""
    _reset_for_tests()
    yield
    _reset_for_tests()


@pytest.fixture
def redis_client():
    """Fresh in-memory redis per test — no cross-test pollution."""
    return make_fake_redis_client()


class TestRedisConversationRateLimiterAllow:
    def test_first_message_allowed(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client, limit=5, window_seconds=60)
        decision = limiter.check("chat-abc")
        assert decision.allowed is True
        assert decision.current_count == 1
        assert decision.limit == 5
        assert decision.window_seconds == 60

    def test_under_limit_all_allowed(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client, limit=3, window_seconds=60)
        decisions = [limiter.check("chat-x") for _ in range(3)]
        assert all(d.allowed for d in decisions)
        assert [d.current_count for d in decisions] == [1, 2, 3]


class TestRedisConversationRateLimiterReject:
    def test_over_limit_rejected(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client, limit=2, window_seconds=60)
        d1 = limiter.check("chat-y")
        d2 = limiter.check("chat-y")
        d3 = limiter.check("chat-y")
        assert d1.allowed is True
        assert d2.allowed is True
        assert d3.allowed is False
        assert d3.current_count == 3
        assert d3.limit == 2

    def test_subsequent_messages_still_rejected_in_same_window(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client, limit=1, window_seconds=60)
        limiter.check("chat-z")
        for _ in range(5):
            decision = limiter.check("chat-z")
            assert decision.allowed is False


class TestRedisConversationRateLimiterIsolation:
    def test_counts_isolated_per_chat_id(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client, limit=2, window_seconds=60)
        # Burn chat-a's budget.
        limiter.check("chat-a")
        limiter.check("chat-a")
        rejected = limiter.check("chat-a")
        assert rejected.allowed is False
        # chat-b is independent.
        d_b = limiter.check("chat-b")
        assert d_b.allowed is True
        assert d_b.current_count == 1


class TestRedisConversationRateLimiterEmptyChatId:
    def test_empty_chat_id_rejected(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client, limit=10, window_seconds=60)
        decision = limiter.check("")
        assert decision.allowed is False
        assert decision.current_count == 0


class TestRedisConversationRateLimiterFailOpen:
    def test_redis_outage_fails_open(self):
        broken_redis = MagicMock()
        broken_redis.incr.side_effect = ConnectionError("redis down")
        limiter = RedisConversationRateLimiter(
            broken_redis, limit=5, window_seconds=60
        )
        decision = limiter.check("chat-abc")
        # Fail-open: legitimate inbounds must not be blocked by a
        # rate-limit storage outage.
        assert decision.allowed is True
        assert decision.current_count == 0


class TestRedisConversationRateLimiterConfigValidation:
    def test_zero_limit_raises(self, redis_client):
        with pytest.raises(ValueError, match="limit must be positive"):
            RedisConversationRateLimiter(redis_client, limit=0)

    def test_negative_window_raises(self, redis_client):
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            RedisConversationRateLimiter(redis_client, limit=5, window_seconds=-1)


class TestRedisConversationRateLimiterWindowRollover:
    def test_new_window_resets_counter(self, redis_client, monkeypatch):
        """Window rollover via patched `time.time` — see what happens
        when the bucket epoch advances. Patches the EXTERNAL time
        module imported by the rate_limit module — not our code."""
        clock = [1_700_000_000.0]  # epoch seconds

        def fake_time():
            return clock[0]

        monkeypatch.setattr(
            "app.services.conversation_rate_limit.time.time", fake_time
        )
        limiter = RedisConversationRateLimiter(redis_client, limit=2, window_seconds=60)
        # Saturate the current window.
        limiter.check("chat-roll")
        limiter.check("chat-roll")
        assert limiter.check("chat-roll").allowed is False
        # Advance past the window boundary.
        clock[0] += 61
        decision = limiter.check("chat-roll")
        # New bucket — counter resets.
        assert decision.allowed is True
        assert decision.current_count == 1


class TestModuleLevelSingleton:
    def test_get_returns_none_before_configure(self):
        assert get_rate_limiter() is None

    def test_configure_then_get(self, redis_client):
        limiter = RedisConversationRateLimiter(redis_client)
        configure_rate_limiter(limiter)
        assert get_rate_limiter() is limiter

    def test_reset_clears(self, redis_client):
        configure_rate_limiter(RedisConversationRateLimiter(redis_client))
        _reset_for_tests()
        assert get_rate_limiter() is None
