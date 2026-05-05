"""Factory for `QuotaTracker` — single seam consumers reach for.

Mirrors the canonical `make_*` factory shape (see `make_redis_client`,
`make_youtube_client`, `get_calendar_adapter`). Pass `kind='memory'`
for tests / dev / single-process; pass `kind='redis'` with an injected
`redis_client` (sync `redis.Redis` or `fakeredis.FakeStrictRedis`) for
multi-process production.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Literal

from noctusai_lib.integrations.quota.in_memory import InMemoryQuotaTracker
from noctusai_lib.integrations.quota.protocol import QuotaTracker
from noctusai_lib.integrations.quota.redis_backend import RedisQuotaTracker


def make_quota_tracker(
    *,
    kind: Literal["memory", "redis"] = "memory",
    redis_client: Any = None,
    key_prefix: str = "noctus:quota",
    now: Callable[[], datetime] | None = None,
) -> QuotaTracker:
    """Build a `QuotaTracker`.

    - `kind='memory'` → `InMemoryQuotaTracker(now=now)`. Default. Safe
      for tests + dev + single-process. Not multi-process safe.
    - `kind='redis'` → `RedisQuotaTracker(redis_client, key_prefix=...,
      now=now)`. Production. Requires an injected `redis_client`
      (raises `ValueError` if missing).

    Tip: pass `redis_client=make_fake_redis_client()` for
    network-free production-shape tests of consumers that wire through
    the factory.
    """
    if kind == "memory":
        return InMemoryQuotaTracker(now=now)

    if kind == "redis":
        if redis_client is None:
            raise ValueError(
                "make_quota_tracker(kind='redis', ...) requires redis_client. "
                "Pass `make_redis_client(redis_url)` or "
                "`make_fake_redis_client()` for tests."
            )
        return RedisQuotaTracker(
            redis_client, key_prefix=key_prefix, now=now
        )

    raise ValueError(
        f"make_quota_tracker: unsupported kind={kind!r}; "
        "expected 'memory' or 'redis'."
    )


__all__ = ["make_quota_tracker"]
