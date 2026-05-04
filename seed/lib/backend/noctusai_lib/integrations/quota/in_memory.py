"""In-memory `QuotaTracker` — deque-per-key sliding window.

Deterministic, network-free, suitable for tests + dev + single-process
deployments. Not safe across multiple processes (no shared state) —
production multi-worker deployments should use `RedisQuotaTracker`.

The counter is a `dict[str, deque[float]]` mapping key → list of UTC
epoch-seconds timestamps, one per recorded unit. `consume(units=N)`
appends N timestamps atomically (under the per-instance asyncio.Lock
so concurrent `asyncio.gather(...)` calls don't double-count).
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict

from noctusai_lib.integrations.quota.protocol import QuotaTracker
from noctusai_lib.integrations.quota.types import QuotaCheck, QuotaConfig


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryQuotaTracker:
    """Deque-per-key sliding-window quota tracker. Async-safe within a
    single asyncio event loop via per-instance lock; not multi-process.

    `now` is injected for deterministic tests — pass a callable returning
    an aware UTC datetime. Defaults to `datetime.now(timezone.utc)`.
    """

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now: Callable[[], datetime] = now or _default_now
        self._configs: Dict[str, QuotaConfig] = {}
        self._records: Dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Protocol surface

    async def register_quota(self, *, key: str, config: QuotaConfig) -> None:
        async with self._lock:
            self._configs[key] = config
            # Preserve existing records on re-register (cap hot-swap).
            self._records.setdefault(key, deque())

    async def consume(self, *, key: str, units: int = 1) -> QuotaCheck:
        if units < 0:
            raise ValueError(f"units must be >= 0; got {units}")

        async with self._lock:
            config = self._require_config(key)
            now_dt = self._now_aware_utc()
            self._evict(key, now_dt, config.window_seconds)

            records = self._records[key]
            current_used = len(records)
            effective_cap = config.effective_cap

            if current_used + units > effective_cap:
                # Denied — no partial commit; counter unchanged.
                return self._build_check(
                    key=key,
                    allowed=False,
                    used=current_used,
                    config=config,
                    now_dt=now_dt,
                )

            ts = now_dt.timestamp()
            for _ in range(units):
                records.append(ts)

            return self._build_check(
                key=key,
                allowed=True,
                used=len(records),
                config=config,
                now_dt=now_dt,
            )

    async def peek(self, *, key: str) -> QuotaCheck:
        async with self._lock:
            config = self._require_config(key)
            now_dt = self._now_aware_utc()
            self._evict(key, now_dt, config.window_seconds)
            used = len(self._records[key])
            return self._build_check(
                key=key,
                allowed=used < config.effective_cap,
                used=used,
                config=config,
                now_dt=now_dt,
            )

    async def reset(self, *, key: str) -> None:
        async with self._lock:
            self._require_config(key)
            self._records[key] = deque()

    # ------------------------------------------------------------------
    # Internals

    def _require_config(self, key: str) -> QuotaConfig:
        config = self._configs.get(key)
        if config is None:
            raise KeyError(
                f"QuotaTracker: key {key!r} not registered. "
                "Call register_quota(key=..., config=...) first."
            )
        return config

    def _now_aware_utc(self) -> datetime:
        ts = self._now()
        if ts.tzinfo is None:
            # Coerce to UTC defensively rather than silently mixing tz —
            # surfacing the mismatch via assert would crash production
            # consumers that pass naive datetimes by accident.
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    def _evict(self, key: str, now_dt: datetime, window_seconds: int) -> None:
        records = self._records.setdefault(key, deque())
        cutoff = now_dt.timestamp() - window_seconds
        while records and records[0] <= cutoff:
            records.popleft()

    def _build_check(
        self,
        *,
        key: str,
        allowed: bool,
        used: int,
        config: QuotaConfig,
        now_dt: datetime,
    ) -> QuotaCheck:
        records = self._records[key]
        effective_cap = config.effective_cap
        remaining = max(0, effective_cap - used)
        if records:
            oldest_ts = records[0]
            reset_at = datetime.fromtimestamp(
                oldest_ts + config.window_seconds,
                tz=timezone.utc,
            )
        else:
            reset_at = now_dt
        return QuotaCheck(
            allowed=allowed,
            remaining=remaining,
            used=used,
            reset_at=reset_at,
            key=key,
        )


# Verify `InMemoryQuotaTracker` satisfies the Protocol at import time.
# This catches signature drift between `protocol.py` and the concrete
# implementation in CI.
_protocol_check: QuotaTracker = InMemoryQuotaTracker()  # type: ignore[assignment]
del _protocol_check
