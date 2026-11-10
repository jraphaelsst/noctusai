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
# NOC-REMEDIATE[ttl-cache-adopt]: hand-rolled TTL caches that should move onto TTLCache (epoch-fenced invalidation):
# api/auth/token_cache.py, domain/module_enablement/store.py, domain/licensing.py, api/auth/org_selection.py — 2026-11-10.
from __future__ import annotations

import threading
import time
from typing import Callable, Generic, Hashable, Optional, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

_MISSING = object()


class TTLCache(Generic[K, V]):
    """Read-through TTL cache. ``get(key, loader)`` returns the cached value while it is younger than ``ttl_s``.

    ``invalidate`` bumps an epoch; a load that STARTED before it never writes its (stale) value back, so a write
    that invalidates while a read is in flight is not undone for the whole TTL. An async caller that cannot hand
    ``get`` a sync loader captures :attr:`epoch` before its read and passes it to :meth:`put`."""

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
        self._epoch = 0
        self.loader_runs = 0  # how many times a `get` loader ran (tests and ops read it)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def epoch(self) -> int:
        with self._lock:
            return self._epoch

    def get(self, key: K, loader: Callable[[], V]) -> V:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key, _MISSING)
            if hit is not _MISSING and now - hit[0] < self._ttl:  # type: ignore[index]
                return hit[1]  # type: ignore[index]
            epoch = self._epoch
        value = loader()  # outside the lock: a slow read must not serialise unrelated keys
        with self._lock:
            self.loader_runs += 1
        self.put(key, value, epoch=epoch)
        return value

    def peek(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """The fresh cached value, or ``default``. For an async caller that cannot hand ``get`` a sync loader."""
        with self._lock:
            hit = self._items.get(key, _MISSING)
            if hit is not _MISSING and self._clock() - hit[0] < self._ttl:  # type: ignore[index]
                return hit[1]  # type: ignore[index]
        return default

    def put(self, key: K, value: V, *, epoch: Optional[int] = None) -> bool:
        """Store ``value``. With ``epoch`` (captured before the read that produced it) the write is dropped when an
        ``invalidate`` happened since: returns whether it was stored."""
        with self._lock:
            if epoch is not None and epoch != self._epoch:
                return False
            if len(self._items) >= self._max and key not in self._items:
                self._items.pop(next(iter(self._items)))
            self._items[key] = (self._clock(), value)
            return True

    def invalidate(self, key: Optional[K] = None) -> None:
        """Drop one key, or everything (``key=None``), and fence every load already in flight."""
        with self._lock:
            self._epoch += 1
            if key is None:
                self._items.clear()
            else:
                self._items.pop(key, None)


class IdleGate:
    """Skip-ticks gate for a periodic job: ``due()`` -> work or probe; ``idle()`` after an empty tick; ``wake()``
    from a producer. Starts due, so the first tick after boot always looks.

    A ``wake()`` that lands while a probe is in flight is never lost: ``due()`` records the epoch it saw and
    ``idle()`` only applies when no wake arrived since."""

    def __init__(self, fallback_s: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        if fallback_s <= 0:
            raise ValueError("fallback_s must be > 0")
        self._fallback = float(fallback_s)
        self._clock = clock
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._epoch = 0
        self._probe_epoch = 0
        self._failures = 0
        self.probes = 0  # ticks that did look (tests and ops read it)

    def due(self) -> bool:
        with self._lock:
            if self._clock() >= self._next_at:
                self.probes += 1
                self._probe_epoch = self._epoch
                return True
            return False

    def idle(self, *, next_due_in_s: Optional[float] = None) -> None:
        """The tick found nothing. Look again in ``fallback_s`` -- or sooner, when the caller knows work is due
        in ``next_due_in_s`` seconds (a campaign scheduled for later). Ignored when a ``wake()`` arrived while the
        probe ran: that producer's work is not covered by what the probe read."""
        delay = self._fallback if next_due_in_s is None else max(0.0, min(self._fallback, float(next_due_in_s)))
        with self._lock:
            self._failures = 0
            if self._epoch != self._probe_epoch:
                return
            self._next_at = self._clock() + delay

    def busy(self) -> None:
        """The tick found work (or failed): look again on the very next tick."""
        with self._lock:
            self._epoch += 1
            self._failures = 0
            self._next_at = 0.0

    wake = busy

    def failed(self, *, base_s: float = 30.0) -> None:
        """A tick FAILED (a 402 outage, a 5xx): retry with exponential backoff -- ``base_s``, 2x, 4x ... capped at
        ``fallback_s`` -- instead of at the tick rate. A success (``idle``/``busy``) resets it; a ``wake()`` that
        arrived during the probe still makes the next tick look."""
        with self._lock:
            self._failures += 1
            delay = min(self._fallback, float(base_s) * (2 ** (self._failures - 1)))
            if self._epoch != self._probe_epoch:
                return
            self._next_at = self._clock() + delay


__all__ = ["IdleGate", "TTLCache"]
