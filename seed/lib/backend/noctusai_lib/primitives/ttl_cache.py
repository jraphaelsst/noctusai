"""In-process TTL cache + idle gate: the two seed answers to "this runs on every tick / request".

Born from the 2026-11-09 Supabase egress incident (``KB § PATTERNS/backend/polling-request-budget.md``): a
settings/config/credential read per request or per tick, and a periodic job that asks an EMPTY table "anything
for me?" every 30 s, spent a Free-plan quota on call volume alone. Both fixes are the same two ideas, so they live
here once instead of once per product:

* :class:`TTLCache` — read-through cache, ``ttl_s`` seconds (keep it <= 60 for settings / credentials), explicit
  ``invalidate`` for the write path of the SAME process, thread-safe (jobs run in worker threads), bounded.
  A loader that RAISES caches nothing (the next call retries): a failure is never remembered as an answer.
* :class:`IdleGate` — a periodic job asks ``due()`` first; an empty tick calls ``idle()`` (next look in at most
  ``fallback_s``, or sooner when the caller knows the next due instant); a producer in the same process calls
  ``wake()`` so the work it just queued is picked up at once. The job stays registered at its cadence; only the
  DB call is skipped.

Pure stdlib, no IO: safe in the ``primitives`` layer. The clock is injectable so a test advances time
instead of sleeping.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Generic, Hashable, Optional, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

_MISSING = object()


class TTLCache(Generic[K, V]):
    """Read-through TTL cache. ``get(key, loader)`` returns the cached value while it is younger than ``ttl_s``."""

    def __init__(
        self,
        ttl_s: float,
        *,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be > 0")
        self._ttl = float(ttl_s)
        self._max = max(1, int(max_entries))
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[K, tuple[float, V]] = {}
        self.loads = 0  # how many times a loader ran (tests and ops read it)

    def get(self, key: K, loader: Callable[[], V]) -> V:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key, _MISSING)
            if hit is not _MISSING and now - hit[0] < self._ttl:  # type: ignore[index]
                return hit[1]  # type: ignore[index]
        value = loader()  # outside the lock: a slow read must not serialise unrelated keys
        with self._lock:
            self.loads += 1
            if len(self._items) >= self._max and key not in self._items:
                self._items.pop(next(iter(self._items)))
            self._items[key] = (self._clock(), value)
        return value

    def peek(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """The fresh cached value, or ``default``. For an async caller that cannot hand ``get`` a sync loader."""
        with self._lock:
            hit = self._items.get(key, _MISSING)
            if hit is not _MISSING and self._clock() - hit[0] < self._ttl:  # type: ignore[index]
                return hit[1]  # type: ignore[index]
        return default

    def put(self, key: K, value: V) -> None:
        with self._lock:
            self.loads += 1
            if len(self._items) >= self._max and key not in self._items:
                self._items.pop(next(iter(self._items)))
            self._items[key] = (self._clock(), value)

    def invalidate(self, key: Optional[K] = None) -> None:
        """Drop one key, or everything (``key=None``). Call it on the write path of the process that wrote."""
        with self._lock:
            if key is None:
                self._items.clear()
            else:
                self._items.pop(key, None)


class IdleGate:
    """Skip-ticks gate for a periodic job: ``due()`` -> work or probe; ``idle()`` after an empty tick; ``wake()``
    from a producer. Starts due, so the first tick after boot always looks."""

    def __init__(self, fallback_s: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if fallback_s <= 0:
            raise ValueError("fallback_s must be > 0")
        self._fallback = float(fallback_s)
        self._clock = clock
        self._lock = threading.Lock()
        self._next_at = 0.0
        self.probes = 0  # ticks that did look (tests and ops read it)

    def due(self) -> bool:
        with self._lock:
            if self._clock() >= self._next_at:
                self.probes += 1
                return True
            return False

    def idle(self, *, next_due_in_s: Optional[float] = None) -> None:
        """The tick found nothing. Look again in ``fallback_s`` -- or sooner, when the caller knows work is due
        in ``next_due_in_s`` seconds (a campaign scheduled for later)."""
        delay = self._fallback if next_due_in_s is None else max(0.0, min(self._fallback, float(next_due_in_s)))
        with self._lock:
            self._next_at = self._clock() + delay

    def busy(self) -> None:
        """The tick found work: look again on the very next tick."""
        with self._lock:
            self._next_at = 0.0

    wake = busy


__all__ = ["IdleGate", "TTLCache"]
