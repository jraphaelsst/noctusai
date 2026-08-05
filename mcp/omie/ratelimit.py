"""Client-side enforcement of Omie's documented consumption limits.

Source: ajuda.omie.com.br § "Limites de Consumo da API do Omie" —

  * 960 requests/min per **IP**
  * 240 requests/min per **IP + app_key + method**
  * 4 concurrent requests per **IP + app_key + method** (some methods: 1)
  * 10 consecutive failures on the same IP+app_key+method ⇒ **HTTP 425,
    blocked for 30 minutes**

That last one is why this module exists rather than "just retry on 429".
Omie punishes a hot retry loop with a half-hour outage for that
method — so the connector throttles *before* sending, and a failure streak
opens the circuit locally instead of spending the remaining attempts that
would trigger the server-side block.

Windows are per-process. A single MCP server process is the whole client
for its host, which is the granularity Omie meters (per IP), so this is
the right place for it; it is deliberately NOT distributed state.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque, Optional

# Omie's published ceilings, held at ~90% so a burst that races the window
# boundary still lands inside the server-side limit.
GLOBAL_PER_MINUTE = 960
PER_METHOD_PER_MINUTE = 240
PER_METHOD_CONCURRENCY = 4
SAFETY = 0.9

#: Consecutive failures on one key before we stop sending. Omie blocks at
#: 10; we open at 6 to leave headroom for other clients on the same IP.
FAILURE_STREAK_OPEN = 6
CIRCUIT_COOLDOWN_SECONDS = 60.0


class _SlidingWindow:
    """Count of events in the trailing 60s; `wait_for_slot` sleeps to fit."""

    def __init__(self, limit: int):
        self.limit = max(1, int(limit * SAFETY))
        self._events: Deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def delay(self, now: Optional[float] = None) -> float:
        now = now if now is not None else time.monotonic()
        self._prune(now)
        if len(self._events) < self.limit:
            return 0.0
        return max(0.0, 60.0 - (now - self._events[0])) + 0.01

    def record(self, now: Optional[float] = None) -> None:
        self._events.append(now if now is not None else time.monotonic())

    def count(self) -> int:
        self._prune(time.monotonic())
        return len(self._events)


class OmieRateLimiter:
    """Per-process limiter, keyed by `(app_key, endpoint_path, call)`."""

    def __init__(self) -> None:
        self._global = _SlidingWindow(GLOBAL_PER_MINUTE)
        self._per_method: dict[str, _SlidingWindow] = {}
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._failures: dict[str, int] = defaultdict(int)
        self._open_until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def key(app_key: str, path: str, call: str) -> str:
        return f"{app_key[-6:]}|{path}|{call}"

    def _window(self, key: str) -> _SlidingWindow:
        w = self._per_method.get(key)
        if w is None:
            w = self._per_method[key] = _SlidingWindow(PER_METHOD_PER_MINUTE)
        return w

    def _sem(self, key: str) -> asyncio.Semaphore:
        s = self._sems.get(key)
        if s is None:
            s = self._sems[key] = asyncio.Semaphore(PER_METHOD_CONCURRENCY)
        return s

    def circuit_block(self, key: str) -> Optional[float]:
        """Seconds remaining on a locally-opened circuit, else None."""
        until = self._open_until.get(key)
        if until is None:
            return None
        remaining = until - time.monotonic()
        if remaining <= 0:
            self._open_until.pop(key, None)
            self._failures[key] = 0
            return None
        return remaining

    async def acquire(self, key: str) -> asyncio.Semaphore:
        """Throttle to fit both windows, then take the concurrency slot.

        Returns the semaphore so the caller releases it in a `finally`.
        """
        while True:
            async with self._lock:
                delay = max(self._global.delay(), self._window(key).delay())
                if delay <= 0:
                    now = time.monotonic()
                    self._global.record(now)
                    self._window(key).record(now)
                    break
            await asyncio.sleep(min(delay, 60.0))
        sem = self._sem(key)
        await sem.acquire()
        return sem

    def record_success(self, key: str) -> None:
        self._failures[key] = 0

    def record_failure(self, key: str) -> None:
        """Track the streak; open the local circuit before Omie blocks us."""
        self._failures[key] += 1
        if self._failures[key] >= FAILURE_STREAK_OPEN:
            self._open_until[key] = time.monotonic() + CIRCUIT_COOLDOWN_SECONDS

    def snapshot(self) -> dict:
        """Observable state for `omie.diagnostics.rate_limit_status`."""
        return {
            "global_last_minute": self._global.count(),
            "global_limit_per_minute": GLOBAL_PER_MINUTE,
            "effective_global_limit": self._global.limit,
            "per_method_limit_per_minute": PER_METHOD_PER_MINUTE,
            "per_method_concurrency": PER_METHOD_CONCURRENCY,
            "tracked_methods": len(self._per_method),
            "methods_last_minute": {
                k: w.count() for k, w in self._per_method.items() if w.count()
            },
            "open_circuits": {
                k: round(v, 1)
                for k in list(self._open_until)
                if (v := self.circuit_block(k)) is not None
            },
            "failure_streaks": {k: v for k, v in self._failures.items() if v},
        }


#: Module-level singleton — one client per process, matching Omie's per-IP meter.
limiter = OmieRateLimiter()


__all__ = [
    "OmieRateLimiter",
    "limiter",
    "GLOBAL_PER_MINUTE",
    "PER_METHOD_PER_MINUTE",
    "PER_METHOD_CONCURRENCY",
    "FAILURE_STREAK_OPEN",
]
