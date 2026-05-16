"""Per-conversation inbound rate limiter — security hardening (absorbed from imobi-scheduling, Wave 2.3).

The seed `noctusai_lib.api.rate_limit.create_limiter` (slowapi-backed)
covers **per-IP HTTP rate limiting** on FastAPI routes. That axis is
already wired on the webhook endpoint via `webhook_rate_limit` setting.

This module adds an **orthogonal axis**: per-conversation inbound
message rate. WAHA pushes all inbound webhooks from a small set of
upstream IPs (its own infra), so per-IP limiting cannot distinguish a
flooding user from a legitimate one. The key here is the WhatsApp
`chat_id` (the conversation identity), not the upstream sender IP.

**Shape decision** (per `KB § PATTERNS/seed-fake-real-adapter.md`):
ships Protocol + a single Redis-backed implementation that works
against both the real Redis client and the `fakeredis` test fake. No
separate "Fake" class — the test path swaps in `make_fake_redis_client()`
and the same `RedisConversationRateLimiter` is exercised. Pure-logic
adapter (Redis is the only IO; the fake exercises identical code
paths) so a separate Fake class would be ceremony per the exemption
test (`KB § PATTERNS/seed-fake-real-adapter.md` § Exemption).

**Seed lift destination — N=2 confirmed**: a second product needing
per-conversation rate limiting (e.g. therapy bot, mailing inbound
replies) flips this to `noctusai_lib.api.conversation_rate_limit` per
`KB § PATTERNS/seed-lib-layout.md` § api. **N=1 today** — file the
follow-up if therapy/mailing inherit.

**Window math**: fixed-window counter (1-second resolution). Each
inbound message increments a counter at key
`ratelimit:conversation:{chat_id}:{epoch_window}`; counter expires
after `window_seconds`. Simple, cheap, no Redis Lua needed. The minor
edge case (a burst straddling two windows can briefly exceed the
limit by ~2x) is acceptable for the threat model (flood detection,
not micro-second precision).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a `check(chat_id)` call.

    Attributes:
        allowed: True if the inbound should be processed; False if rate
            limit exceeded.
        current_count: Number of inbound messages observed in the
            current window (post-increment if `allowed`, pre-check if
            rejected — see `check` docstring).
        limit: Configured per-window maximum.
        window_seconds: Configured window size.
    """

    allowed: bool
    current_count: int
    limit: int
    window_seconds: int


@runtime_checkable
class ConversationRateLimiter(Protocol):
    """Per-conversation rate-limit Protocol.

    Single-method surface — `check(chat_id)`. Implementations decide
    storage (Redis, in-memory, per-deployment); the caller treats them
    uniformly.
    """

    def check(self, chat_id: str) -> RateLimitDecision:
        """Return a decision for this inbound. MUST increment the
        counter atomically as part of the check (otherwise concurrent
        callers race past the limit)."""
        ...


class RedisConversationRateLimiter:
    """Redis-backed fixed-window counter.

    Suitable for production (real Redis) and tests (fakeredis) — both
    satisfy the `RedisBufferClient`-shape that the seed's
    `make_redis_client` / `make_fake_redis_client` factories return.

    Algorithm:
      1. Compute window bucket: `now_epoch // window_seconds`.
      2. Key: `prefix:{chat_id}:{bucket}`.
      3. `INCR` (atomic). On first call within bucket, `EXPIRE`.
      4. If count > limit → reject; else accept.

    The pre-emptive `EXPIRE` after every INCR is idempotent and cheap;
    the alternative ("only EXPIRE when INCR returned 1") races against
    a worker crash between the two calls. Pay the extra microsecond.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        limit: int = 30,
        window_seconds: int = 60,
        prefix: str = "ratelimit:conversation",
    ) -> None:
        """Construct the limiter.

        Args:
            redis_client: Any `RedisBufferClient`-shaped client
                (real `redis.Redis` or `fakeredis.FakeStrictRedis`).
            limit: Max messages per window before rejection. Default
                30 — calibrated against the WhatsApp UI typing speed
                (~2 messages/sec sustained is well above human typing).
                A flood from a misbehaving client or a prompt-injection
                loop will hit this in seconds.
            window_seconds: Bucket size. Default 60s — gives the bot
                room to recover from a brief burst (user pasting a
                long message in chunks) without rejecting legitimate
                conversation.
            prefix: Redis key prefix. Override for multi-tenant tests
                that need isolated counters.
        """
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")
        self._redis = redis_client
        self._limit = limit
        self._window_seconds = window_seconds
        self._prefix = prefix

    def check(self, chat_id: str) -> RateLimitDecision:
        """Atomically increment the bucket + return the decision.

        Concurrent callers: Redis `INCR` is atomic, so two parallel
        callers cannot both observe `count == limit` on the same
        bucket — exactly one wins. The loser's `current_count` will
        be `limit + 1` (or higher under heavier concurrency).
        """
        if not chat_id:
            logger.warning("Rate-limit check received empty chat_id; rejecting")
            return RateLimitDecision(
                allowed=False,
                current_count=0,
                limit=self._limit,
                window_seconds=self._window_seconds,
            )

        bucket = int(time.time()) // self._window_seconds
        key = f"{self._prefix}:{chat_id}:{bucket}"
        try:
            count = int(self._redis.incr(key))
            self._redis.expire(key, self._window_seconds)
        except Exception as exc:  # noqa: BLE001 — fail-open on Redis outage.
            logger.warning(
                "Rate-limit Redis check failed for chat_id=%s; failing OPEN: %s",
                chat_id,
                exc,
            )
            return RateLimitDecision(
                allowed=True,
                current_count=0,
                limit=self._limit,
                window_seconds=self._window_seconds,
            )

        allowed = count <= self._limit
        if not allowed:
            logger.warning(
                "Per-conversation rate limit exceeded: chat_id=%s count=%d limit=%d window_s=%d",
                chat_id,
                count,
                self._limit,
                self._window_seconds,
            )
        return RateLimitDecision(
            allowed=allowed,
            current_count=count,
            limit=self._limit,
            window_seconds=self._window_seconds,
        )


# Module-level singleton — mirrors `app/services/metrics.py` pattern.
_limiter: Optional[ConversationRateLimiter] = None


def configure_rate_limiter(limiter: ConversationRateLimiter) -> None:
    """Install the module-level limiter (idempotent across re-configs)."""
    global _limiter
    _limiter = limiter
    logger.info(
        "Conversation rate limiter configured: %s",
        type(limiter).__name__,
    )


def get_rate_limiter() -> Optional[ConversationRateLimiter]:
    """Return the configured limiter, or None if not yet wired.

    None is a valid state — the webhook router treats it as
    "rate-limiting disabled" and processes inbounds unconditionally.
    """
    return _limiter


def _reset_for_tests() -> None:
    """Test helper — clears the module-level singleton."""
    global _limiter
    _limiter = None


__all__ = [
    "ConversationRateLimiter",
    "RateLimitDecision",
    "RedisConversationRateLimiter",
    "configure_rate_limiter",
    "get_rate_limiter",
]
