"""`DefaultingQuotaTracker` — per-tenant keys without a registration step.

Every tracker REFUSES a key that was never registered (`KeyError` — no
implicit infinite quota, see `protocol.py`). That is right for a fixed key
set, but a per-tenant key (`f"fotos.edit:{org_id}"`) belongs to a set nobody
can enumerate up front: a registration step at boot misses every tenant
created later, and a registration step per call site is a copy that drifts.

This wrapper registers ONE declared default the first time a key is seen,
then behaves exactly like the tracker it wraps. The default is explicit and
finite — it never turns an unknown key into an unlimited one. A key that
was registered on the inner tracker beforehand keeps its own config (a
per-tenant override is just an ordinary `register_quota`).

    tracker = DefaultingQuotaTracker(
        make_quota_tracker(kind="redis", redis_client=redis),
        default=QuotaConfig(cap=300, window_seconds=86_400),
    )
    await tracker.consume(key=f"fotos.edit:{org_id}")
"""

from __future__ import annotations

import asyncio

from noctusai_lib.integrations.quota.protocol import QuotaTracker
from noctusai_lib.integrations.quota.types import QuotaCheck, QuotaConfig


class DefaultingQuotaTracker:
    """A `QuotaTracker` that auto-registers `default` for unseen keys."""

    def __init__(self, inner: QuotaTracker, *, default: QuotaConfig) -> None:
        self._inner = inner
        self._default = default
        self._known: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def default(self) -> QuotaConfig:
        return self._default

    async def _ensure(self, key: str) -> None:
        if key in self._known:
            return
        async with self._lock:
            if key in self._known:
                return
            try:
                await self._inner.peek(key=key)
            except KeyError:
                await self._inner.register_quota(key=key, config=self._default)
            self._known.add(key)

    async def register_quota(self, *, key: str, config: QuotaConfig) -> None:
        await self._inner.register_quota(key=key, config=config)
        self._known.add(key)

    async def consume(self, *, key: str, units: int = 1) -> QuotaCheck:
        await self._ensure(key)
        return await self._inner.consume(key=key, units=units)

    async def peek(self, *, key: str) -> QuotaCheck:
        await self._ensure(key)
        return await self._inner.peek(key=key)

    async def reset(self, *, key: str) -> None:
        await self._ensure(key)
        await self._inner.reset(key=key)


__all__ = ["DefaultingQuotaTracker"]
