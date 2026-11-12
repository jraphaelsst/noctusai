"""Per-process wake registry: an in-process state change cuts an idle worker's sleep.

`Worker` backs its idle poll off to 300s (egress incident 2026-11-09: a fixed
1s poll of an empty queue made ~10 workers fire ~15k claim RPCs/hour; W1-C
2026-11-12: at a 30s cap prod still saw 56k `claim_next_job`/day, ~20 loops).
Workers run in the API process next to the routes that enqueue for them, so a
producer in the SAME process calls `notify_enqueued(job_type)` and every
registered worker handling that type wakes at once and resets to its base poll
interval. A job that only becomes claimable LATER (future `scheduled_for`, a
retry backoff, a `reschedule`) passes `run_at=`: the registry arms a timer so
the worker wakes when the job is due instead of at the idle cap.
Producers in another process/container cannot reach this registry; their jobs
wait at most `max_idle_interval_seconds`.

Thread-safe: `notify_enqueued` may run off the event-loop thread (to_thread /
run_blocking callers); the wake is delivered with `loop.call_soon_threadsafe`,
never by setting an asyncio.Event from a foreign thread.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
import weakref

_lock = threading.Lock()
_wakers: "weakref.WeakSet[Waker]" = weakref.WeakSet()


class Waker:
    """One registered worker: its loop, its wake event, the job types it serves."""

    def __init__(self, loop: asyncio.AbstractEventLoop, types: frozenset[str]) -> None:
        self.loop = loop
        self.types = types
        self.event = asyncio.Event()
        self._timers: dict[int, asyncio.TimerHandle] = {}

    def _set(self) -> None:
        self.event.set()

    def _arm(self, delay_s: float) -> None:
        """Set the wake event after `delay_s` (loop thread only). One timer per whole second."""
        key = int(delay_s)
        if key in self._timers:
            return

        def fire(k: int = key) -> None:
            self._timers.pop(k, None)
            self.event.set()

        self._timers[key] = self.loop.call_later(delay_s, fire)

    def _disarm(self) -> None:
        for h in self._timers.values():
            h.cancel()
        self._timers.clear()


def register(loop: asyncio.AbstractEventLoop, types: list[str]) -> Waker:
    waker = Waker(loop, frozenset(types))
    with _lock:
        _wakers.add(waker)
    return waker


def unregister(waker: Waker) -> None:
    with _lock:
        _wakers.discard(waker)
    try:
        waker.loop.call_soon_threadsafe(waker._disarm)
    except RuntimeError:  # loop already closed; its timers died with it
        pass


def notify_enqueued(job_type: str, *, run_at: datetime | None = None) -> None:
    """Wake every in-process worker whose handlers include `job_type`.

    `run_at` (the job's `scheduled_for`): when in the future, the wake is
    delivered then, not now; a due/past/None value wakes immediately.
    """
    delay = 0.0
    if run_at is not None:
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        delay = (run_at - datetime.now(timezone.utc)).total_seconds()
    with _lock:
        targets = [w for w in _wakers if job_type in w.types]
    for w in targets:
        try:
            if delay > 0:
                w.loop.call_soon_threadsafe(w._arm, delay)
            else:
                w.loop.call_soon_threadsafe(w._set)
        except RuntimeError:  # that worker's loop is closed — it is gone
            unregister(w)
