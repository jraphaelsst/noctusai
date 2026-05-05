"""Pluggable quota / rate-limit tracker — Protocol+InMemory+Redis+factory.

Lifted 2026-05-04 by `projects/seed-hardening-from-youtube-crawler/`
Phase 3.3 to give every IO-touching integration a uniform place to
record + check usage against a vendor's quota or rate-limit. Today's
recurrence: YouTube (10k units/day across `search.list` 100-cost +
`videos.list` 1-cost), WhatsApp (tiered per-business-account), LLM
providers (TPM + RPM per provider+model), Google Maps (per-day +
per-second). Without a seed home, each integration grew its own
counter (or didn't track at all).

**What ships:**
- `QuotaConfig`, `QuotaCheck` value objects.
- `QuotaTracker` Protocol (async surface).
- `InMemoryQuotaTracker` — deque-per-key sliding window. Tests / dev /
  single-process.
- `RedisQuotaTracker` — ZSET sliding window via Lua script (atomic
  check-and-consume). Production.
- `make_quota_tracker(kind='memory'|'redis', redis_client=...)`.

**Sliding window, not fixed window** — see `types.py` for the
rationale (vendor contracts universally read "≤ N in last X seconds";
fixed window allows a 2x boundary burst that no real consumer wants).

**Atomic semantics.** `consume(units=N)` is all-or-nothing: when the
addition would exceed the cap, NO units are recorded and `allowed=False`
is returned. Consumers can retry or back off without worrying about
partial commits. The Redis backend enforces this server-side via Lua;
the InMemory backend uses an asyncio.Lock per instance.

Wire pattern (production):

    from noctusai_lib.integrations.redis import make_redis_client
    from noctusai_lib.integrations.quota import (
        QuotaConfig, make_quota_tracker,
    )

    redis = make_redis_client(settings.redis_url)
    tracker = make_quota_tracker(kind="redis", redis_client=redis)
    await tracker.register_quota(
        key=f"yt:{tenant_id}",
        config=QuotaConfig(cap=10_000, window_seconds=86_400),
    )
    check = await tracker.consume(key=f"yt:{tenant_id}", units=100)
    if not check.allowed:
        raise QuotaExceeded(...)
"""

from noctusai_lib.integrations.quota.factory import make_quota_tracker
from noctusai_lib.integrations.quota.in_memory import InMemoryQuotaTracker
from noctusai_lib.integrations.quota.protocol import QuotaTracker
from noctusai_lib.integrations.quota.redis_backend import RedisQuotaTracker
from noctusai_lib.integrations.quota.types import QuotaCheck, QuotaConfig

__all__ = [
    "InMemoryQuotaTracker",
    "QuotaCheck",
    "QuotaConfig",
    "QuotaTracker",
    "RedisQuotaTracker",
    "make_quota_tracker",
]
