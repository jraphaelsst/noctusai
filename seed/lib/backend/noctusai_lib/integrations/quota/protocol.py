"""`QuotaTracker` Protocol — pluggable quota / rate-limit contract.

Every consumer (YouTube 10k/day, WhatsApp tiered, LLM provider TPM/RPM,
Google Maps, etc.) gets a tracker through `make_quota_tracker(...)` and
talks to it through this Protocol — never the concrete backend. The
backends share an atomicity guarantee on `consume`: when there is
insufficient quota, NO units are recorded (the call is denied AND
no-op on the underlying counter).

Async-only by design — the production backend is Redis-backed and the
Real adapter executes a Lua script over `redis.asyncio.Redis`. The
InMemory backend is sync internally but exposes the same `async`
surface so consumers never branch on backend kind.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from noctusai_lib.integrations.quota.types import QuotaCheck, QuotaConfig


@runtime_checkable
class QuotaTracker(Protocol):
    """Pluggable quota / rate-limit tracker.

    Concrete implementations:
    - `InMemoryQuotaTracker` — deque-per-key sliding window. Tests + dev.
    - `RedisQuotaTracker` — Redis ZSET sliding window via Lua. Production.
    """

    async def register_quota(self, *, key: str, config: QuotaConfig) -> None:
        """Declare a quota's window + cap.

        Calling `consume(key=...)` before the key is registered raises
        `KeyError` — no implicit "infinite quota" default. Re-registering
        a key replaces the prior config; existing counter contents are
        preserved (so you can hot-reload a cap up/down without losing
        in-flight bookkeeping). The new cap takes effect on the next
        `consume` / `peek`.
        """

    async def consume(self, *, key: str, units: int = 1) -> QuotaCheck:
        """Atomically record usage of `units` against `key`.

        Returns `QuotaCheck`:
        - `allowed=True` AND units recorded — when current usage + units
          fits within the effective cap (`cap + burst`).
        - `allowed=False` AND units NOT recorded — when the addition
          would exceed the effective cap. The call is a no-op on the
          underlying counter (atomic; no partial commits).

        Raises:
        - `KeyError` if `key` was never registered.
        - `ValueError` if `units < 0`.
        - Backend-specific I/O errors (e.g. `redis.RedisError`) are
          logged at WARN+ and re-raised; never swallowed.
        """

    async def peek(self, *, key: str) -> QuotaCheck:
        """Non-mutating snapshot of the current quota state.

        `allowed` reflects whether a 1-unit `consume` would succeed
        right now (i.e., `used < effective_cap`). Useful for dashboards,
        pre-flight checks, and "are we close to throttle?" banners.

        Raises `KeyError` if `key` was never registered.
        """

    async def reset(self, *, key: str) -> None:
        """Clear all recorded usage for `key`. Operator escape hatch.

        Configuration (`QuotaConfig` registered for `key`) is preserved;
        only the counter is wiped. Use cases: rotating an API key,
        recovering from a runaway debug script, manual override after
        a vendor side resets a daily bucket.

        Raises `KeyError` if `key` was never registered.
        """
