"""Redis client factory.

Mirrors the noctusai_lib `make_*` factory pattern (see `database.py`).
Consumers call `make_redis_client(redis_url)` with their settings'
`redis_url` and cache the result at module scope (typically inside a
`configure_*_module(...)` call).

Used by `noctusai_lib.domain.chatbot` for the buffer + debounce
ZSET; consumers may also use it directly for non-conversation Redis
needs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis


def make_redis_client(redis_url: str, **kwargs: Any) -> "Redis":
    """Construct a sync `redis.Redis` from a URL.

    Args:
        redis_url: redis:// or rediss:// URL.
        **kwargs: forwarded to `Redis.from_url(...)`. `decode_responses=True`
            is set by default; pass `decode_responses=False` to opt out.

    Returns:
        Configured `Redis` instance. Caller owns lifecycle (no implicit
        connection-pool sharing across factory calls).
    """
    from redis import Redis

    kwargs.setdefault("decode_responses", True)
    return Redis.from_url(redis_url, **kwargs)


def make_fake_redis_client(**kwargs: Any) -> "Redis":
    """In-memory Redis-compatible client for tests + dev (no network).

    Wraps `fakeredis.FakeStrictRedis` with the same `decode_responses=True`
    default as `make_redis_client`. The returned instance satisfies
    `noctusai_lib.domain.chatbot.RedisBufferClient` Protocol naturally —
    drop-in for `make_redis_client(redis_url)` in test/dev paths.

    Per the gold-standard Fake+Real shape (`KB § PATTERNS/seed-fake-real-adapter.md`)
    every IO-touching seed module ships a Fake. The redis module's Fake
    delegates to `fakeredis` rather than hand-rolling because Redis's
    surface area is large and `fakeredis` is the de-facto Python fake.
    """
    import fakeredis  # lazy — only test/dev paths import this

    kwargs.setdefault("decode_responses", True)
    return fakeredis.FakeStrictRedis(**kwargs)
