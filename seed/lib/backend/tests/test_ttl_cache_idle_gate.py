"""TTLCache + IdleGate: the call COUNT is what these assert (KB § PATTERNS/backend/polling-request-budget.md)."""
from __future__ import annotations

import pytest

from noctusai_lib.primitives.ttl_cache import IdleGate, TTLCache


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_ttl_cache_loads_once_per_window_and_reloads_after_ttl():
    clock = _Clock()
    cache: TTLCache[str, int] = TTLCache(30, clock=clock)
    calls = []
    for _ in range(100):
        cache.get("k", lambda: calls.append(1) or 7)
    assert len(calls) == 1
    clock.t += 31
    cache.get("k", lambda: calls.append(1) or 8)
    assert len(calls) == 2


def test_ttl_cache_invalidate_forces_reload_and_failures_are_not_cached():
    cache: TTLCache[str, int] = TTLCache(30, clock=_Clock())
    cache.get("k", lambda: 1)
    cache.invalidate("k")
    assert cache.get("k", lambda: 2) == 2

    def boom() -> int:
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        cache.get("other", boom)
    assert cache.get("other", lambda: 5) == 5  # the failure was not remembered


def test_ttl_cache_is_bounded():
    cache: TTLCache[int, int] = TTLCache(30, max_entries=2, clock=_Clock())
    for i in range(5):
        cache.get(i, lambda i=i: i)
    assert len(cache) == 2


def test_idle_gate_probes_once_per_fallback_window_not_per_tick():
    clock = _Clock()
    gate = IdleGate(300, clock=clock)
    for _ in range(600):  # 600 ticks, 30 s apart = 5 h
        if gate.due():
            gate.idle()
        clock.t += 30
    assert gate.probes <= 61  # one look per 5 min (60 in 5 h + the first), never one per 30 s (600)


def test_idle_gate_wake_makes_the_next_tick_look_and_next_due_shortens_the_wait():
    clock = _Clock()
    gate = IdleGate(300, clock=clock)
    assert gate.due()
    gate.idle()
    assert not gate.due()
    gate.wake()
    assert gate.due()
    gate.idle(next_due_in_s=40)
    clock.t += 39
    assert not gate.due()
    clock.t += 2
    assert gate.due()
    gate.idle(next_due_in_s=9999)  # never later than the fallback
    clock.t += 301
    assert gate.due()


def test_idle_gate_a_wake_during_an_in_flight_probe_is_not_lost():
    clock = _Clock()
    gate = IdleGate(300, clock=clock)
    assert gate.due()  # the probe starts (reads an empty queue) ...
    gate.wake()  # ... a producer queues work and wakes the gate while it runs ...
    gate.idle()  # ... then the probe reports "empty": that must not put the wake back to sleep
    assert gate.due()  # the very next tick looks (was: up to 300 s late)


def test_ttl_cache_a_load_in_flight_across_an_invalidate_does_not_write_back_the_stale_value():
    cache: TTLCache[str, str] = TTLCache(30, clock=_Clock())

    def slow_loader() -> str:
        cache.invalidate("k")  # the write path invalidates while this (pre-write) read is running
        return "stale"

    assert cache.get("k", slow_loader) == "stale"  # the caller still gets its answer ...
    assert cache.get("k", lambda: "fresh") == "fresh"  # ... but it is not served to the next one


def test_ttl_cache_put_with_a_stale_epoch_is_dropped():
    cache: TTLCache[str, int] = TTLCache(30, clock=_Clock())
    epoch = cache.epoch
    cache.invalidate()
    assert cache.put("k", 1, epoch=epoch) is False
    assert cache.peek("k") is None
    assert cache.put("k", 2, epoch=cache.epoch) is True


def test_idle_gate_failures_back_off_exponentially_up_to_the_fallback_and_success_resets():
    clock = _Clock()
    gate = IdleGate(300, clock=clock)
    waits = []
    for _ in range(6):
        assert gate.due()
        gate.failed(base_s=30)
        t0 = clock.t
        while not gate.due():
            clock.t += 1
        waits.append(clock.t - t0)
    assert waits == [30, 60, 120, 240, 300, 300]
    gate.idle()
    gate.failed(base_s=30)  # idle() reset the counter
    clock.t += 31
    assert gate.due()
