"""`domain.jobs.Worker` idle-poll budget (W1-C, 2026-11-12).

Prod baseline: `rpc/claim_next_job` fired 56,022x/24h (~20 worker loops at a
30s idle cap). The budget is <= ~6k/day fleet-wide, so an idle worker backs off
to a 300s cap, and every in-process state change that makes a job claimable
(enqueue, retry backoff, reschedule) wakes it at the moment the job is due.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from noctusai_lib.domain.jobs import FakeJobRepository, RetryPolicy, Worker
from noctusai_lib.domain.jobs.worker import DEFAULT_MAX_IDLE_INTERVAL_SECONDS
from noctusai_lib.primitives.supabase_breaker import Breaker, BreakerConfig


class CountingRepo(FakeJobRepository):
    def __init__(self) -> None:
        super().__init__()
        self.claim_calls = 0

    async def claim_next(self, **kw):
        self.claim_calls += 1
        return await super().claim_next(**kw)


async def _noop(job) -> None:
    return None


def test_default_idle_cap_fits_daily_budget() -> None:
    # 86400 / cap claims per day per worker; ~20 workers must stay <= ~6k/day.
    assert DEFAULT_MAX_IDLE_INTERVAL_SECONDS >= 300.0
    assert 20 * (86400 / DEFAULT_MAX_IDLE_INTERVAL_SECONDS) <= 6000


def test_idle_ticks_call_count_is_bounded_by_backoff() -> None:
    """N idle ticks -> N claim calls, with sleeps 1,2,4,...,cap (never a fixed 1s)."""
    async def scenario():
        repo = CountingRepo()
        sleeps: list[float] = []
        stop = asyncio.Event()

        async def fake_sleep(delay, _stop):
            sleeps.append(delay)
            if len(sleeps) >= 12:
                stop.set()

        w = Worker(repo, worker_id="w", handlers={"t": _noop}, idle_sleep=fake_sleep)
        await w.run_forever(stop_event=stop)
        return repo.claim_calls, sleeps

    calls, sleeps = asyncio.run(scenario())
    assert calls == 12
    assert sleeps[:9] == [1, 2, 4, 8, 16, 32, 64, 128, 256]
    assert max(sleeps) == DEFAULT_MAX_IDLE_INTERVAL_SECONDS
    # 12 ticks cover 1+2+..+256+300*3 = 1411s: far fewer calls than 1411 at a fixed 1s.
    assert calls < sum(sleeps) / 100


def test_in_process_enqueue_is_picked_up_in_under_one_second() -> None:
    async def scenario() -> float:
        repo = CountingRepo()
        done = asyncio.Event()

        async def handler(job) -> None:
            done.set()

        w = Worker(repo, worker_id="w", handlers={"t": handler})
        stop = asyncio.Event()
        task = asyncio.create_task(w.run_forever(stop_event=stop))
        await asyncio.sleep(0.05)
        # Let the worker back off first so the wake (not a poll) is what picks it up.
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        await repo.enqueue(type="t", payload={})
        await asyncio.wait_for(done.wait(), timeout=1.0)
        elapsed = loop.time() - t0
        stop.set()
        await task
        return elapsed

    assert asyncio.run(scenario()) < 1.0


def test_future_scheduled_job_wakes_worker_when_due() -> None:
    async def scenario() -> float:
        repo = CountingRepo()
        done = asyncio.Event()

        async def handler(job) -> None:
            done.set()

        w = Worker(repo, worker_id="w", handlers={"t": handler}, poll_interval_seconds=50.0,
                   max_idle_interval_seconds=300.0)
        stop = asyncio.Event()
        task = asyncio.create_task(w.run_forever(stop_event=stop))
        await asyncio.sleep(0.05)
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        await repo.enqueue(
            type="t", payload={}, scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=0.3)
        )
        await asyncio.wait_for(done.wait(), timeout=2.0)
        elapsed = loop.time() - t0
        stop.set()
        await task
        return elapsed

    assert asyncio.run(scenario()) < 1.5


def test_retry_backoff_wakes_worker_when_due() -> None:
    async def scenario() -> int:
        repo = CountingRepo()
        attempts = 0
        done = asyncio.Event()

        async def handler(job) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("boom")
            done.set()

        policy = RetryPolicy(max_retries=3, backoff_seconds=0.3, backoff_multiplier=1.0, max_backoff_seconds=0.3)
        w = Worker(repo, worker_id="w", handlers={"t": handler}, retry_policy=policy,
                   poll_interval_seconds=50.0, max_idle_interval_seconds=300.0)
        stop = asyncio.Event()
        task = asyncio.create_task(w.run_forever(stop_event=stop))
        await asyncio.sleep(0.05)
        await repo.enqueue(type="t", payload={})
        await asyncio.wait_for(done.wait(), timeout=3.0)
        stop.set()
        await task
        return attempts

    assert asyncio.run(scenario()) == 2


def test_reschedule_wakes_worker_when_due() -> None:
    from noctusai_lib.domain.jobs.repo import RescheduleLater

    async def scenario() -> int:
        repo = CountingRepo()
        runs = 0
        done = asyncio.Event()

        async def handler(job) -> None:
            nonlocal runs
            runs += 1
            if runs == 1:
                raise RescheduleLater(0.3)
            done.set()

        # floor 0: the breaker clamps RescheduleLater to the platform idle-poll floor (10s); a test needs 0.3s.
        w = Worker(repo, worker_id="w", handlers={"t": handler},
                   poll_interval_seconds=50.0, max_idle_interval_seconds=300.0,
                   breaker=Breaker(config=BreakerConfig(min_idle_poll_s=0.0)))
        stop = asyncio.Event()
        task = asyncio.create_task(w.run_forever(stop_event=stop))
        await asyncio.sleep(0.05)
        await repo.enqueue(type="t", payload={})
        await asyncio.wait_for(done.wait(), timeout=3.0)
        stop.set()
        await task
        return runs

    assert asyncio.run(scenario()) == 2

