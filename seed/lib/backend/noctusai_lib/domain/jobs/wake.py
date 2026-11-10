"""Per-process wake registry: an in-process enqueue cuts an idle worker's sleep.

`Worker` backs its idle poll off to ~30s (egress incident, 2026-11-09: a fixed
1s poll of an empty queue made ~10 workers fire ~15k claim RPCs/hour; at the
30s cap that is ~120 calls/hour PER worker, ~1.2k/hour for ~10 workers). Workers
run in the API process next to the routes that enqueue for them, so a producer
in the SAME process calls `notify_enqueued(job_type)` and every registered
worker handling that type wakes at once and resets to its base poll interval.
Producers in another process/container cannot reach this registry; their jobs
wait at most `max_idle_interval_seconds`.

Thread-safe: `notify_enqueued` may run off the event-loop thread (to_thread /
run_blocking callers); the wake is delivered with `loop.call_soon_threadsafe`,
never by setting an asyncio.Event from a foreign thread.
"""
from __future__ import annotations

import asyncio
import threading
import weakref

_lock = threading.Lock()
_wakers: "weakref.WeakSet[Waker]" = weakref.WeakSet()


class Waker:
    """One registered worker: its loop, its wake event, the job types it serves."""

    def __init__(self, loop: asyncio.AbstractEventLoop, types: frozenset[str]) -> None:
        self.loop = loop
        self.types = types
        self.event = asyncio.Event()

    def _set(self) -> None:
        self.event.set()


def register(loop: asyncio.AbstractEventLoop, types: list[str]) -> Waker:
    waker = Waker(loop, frozenset(types))
    with _lock:
        _wakers.add(waker)
    return waker


def unregister(waker: Waker) -> None:
    with _lock:
        _wakers.discard(waker)


def notify_enqueued(job_type: str) -> None:
    """Wake every in-process worker whose handlers include `job_type`."""
    with _lock:
        targets = [w for w in _wakers if job_type in w.types]
    for w in targets:
        try:
            w.loop.call_soon_threadsafe(w._set)
        except RuntimeError:  # that worker's loop is closed — it is gone
            unregister(w)
