"""`domain.jobs` — the operator surfaces added for edicao-fotos W8:
`JobRepository.queue_stats` (Fake + Real) and the `Worker` claim gate."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from noctusai_lib.domain.jobs import (
    FakeJobRepository,
    QueueStats,
    RealSupabaseJobRepository,
    Worker,
)
from noctusai_lib.testing import MockSupabaseClient


def run(coro):
    return asyncio.run(coro)


def test_fake_queue_stats_counts_every_state() -> None:
    async def scenario() -> QueueStats:
        repo = FakeJobRepository()
        await repo.enqueue(type="a", payload={})
        await repo.enqueue(
            type="a", payload={}, scheduled_for=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        await repo.enqueue(type="b", payload={})
        claimed = await repo.claim_next(worker_id="w1", job_types=["a"])
        assert claimed is not None
        doomed = await repo.enqueue(type="a", payload={})
        await repo.claim_next(worker_id="w2", job_types=["a"])
        await repo.mark_failed(doomed.id, "boom: 429", dead_letter=True)
        return await repo.queue_stats(job_types=["a"])

    stats = run(scenario())
    assert (stats.pending, stats.due, stats.running, stats.dead_letter) == (1, 0, 1, 1)
    assert stats.active_workers == ("w1",)
    assert stats.last_error == "boom: 429" and stats.last_error_type == "a"


def test_real_queue_stats_reads_active_dead_and_latest_error() -> None:
    now = datetime.now(timezone.utc)

    def row(**k):
        base = {
            "id": k.pop("id"), "type": "fotos.edit", "payload": {}, "status": "pending",
            "retry_count": 0, "max_retries": 1, "last_error": None,
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
            "scheduled_for": None, "dedupe_key": None, "worker_id": None, "lease_expires_at": None,
        }
        base.update(k)
        return base

    client = MockSupabaseClient()
    client.set_table_data("jobs", [
        row(id="1"),
        row(id="2", status="running", worker_id="w",
            lease_expires_at=(now + timedelta(minutes=5)).isoformat()),
        row(id="3", status="running", worker_id="dead",
            lease_expires_at=(now - timedelta(minutes=5)).isoformat()),
        row(id="4", status="dead_letter", last_error="insufficient_quota"),
    ])
    stats = run(RealSupabaseJobRepository(client).queue_stats())
    assert (stats.pending, stats.due, stats.running, stats.lease_expired, stats.dead_letter) == (
        1, 1, 1, 1, 1
    )
    assert stats.active_workers == ("w",)
    assert stats.last_error == "insufficient_quota"


def test_worker_claim_gate_blocks_and_releases_claims() -> None:
    async def scenario() -> None:
        repo = FakeJobRepository()
        await repo.enqueue(type="t", payload={})
        seen: list[str] = []

        async def handler(job):
            seen.append(job.id)

        state = {"open": False}

        async def gate() -> bool:
            return state["open"]

        worker = Worker(repo, worker_id="w", handlers={"t": handler}, claim_gate=gate)
        assert await worker.run_once() is False and seen == []
        state["open"] = True
        assert await worker.run_once() is True and len(seen) == 1

    run(scenario())


def test_worker_without_gate_is_unchanged() -> None:
    async def scenario() -> bool:
        worker = Worker(FakeJobRepository(), worker_id="w", handlers={})
        return await worker.claim_allowed()

    assert run(scenario()) is True


def test_reschedule_later_keeps_retry_budget_and_delays_claim() -> None:
    from noctusai_lib.domain.jobs.repo import RescheduleLater

    async def scenario():
        repo = FakeJobRepository()
        job = await repo.enqueue(type="t", payload={})

        async def busy(_job):
            raise RescheduleLater(30)

        w = Worker(repo, worker_id="w", handlers={"t": busy})
        assert await w.run_once() is True
        after = repo._jobs[job.id]
        again = await repo.claim_next(worker_id="w", job_types=["t"])
        return after, again

    after, again = run(scenario())
    assert after.status.value == "pending"
    assert after.retry_count == 0
    assert after.worker_id is None and after.lease_expires_at is None
    assert after.scheduled_for is not None and after.scheduled_for > datetime.now(timezone.utc)
    assert again is None


# --- egress incident (2026-11-09): idle backoff, count-only stats, cache ----------


def test_worker_idle_backoff_grows_to_cap_and_resets_after_a_claim() -> None:
    delays: list[float] = []

    async def scenario() -> None:
        repo = FakeJobRepository()
        stop = asyncio.Event()

        async def fake_sleep(delay: float, _stop) -> None:
            delays.append(delay)
            if len(delays) == 5:
                await repo.enqueue(type="a", payload={})  # claimed on the next poll
            if len(delays) == 7:
                stop.set()

        async def handler(_job) -> None:
            return None

        worker = Worker(
            repo, worker_id="w", handlers={"a": handler}, poll_interval_seconds=1.0,
            max_idle_interval_seconds=10.0, idle_sleep=fake_sleep,
        )
        await worker.run_forever(stop_event=stop)

    run(scenario())
    assert delays == [1.0, 2.0, 4.0, 8.0, 10.0, 1.0, 2.0]


def test_real_queue_stats_uses_count_queries_not_row_dumps_and_caches() -> None:
    now = datetime.now(timezone.utc)
    client = MockSupabaseClient()
    client.set_table_data("jobs", [
        {"id": str(i), "type": "t", "payload": {}, "status": "pending", "retry_count": 0,
         "max_retries": 1, "last_error": None, "created_at": now.isoformat(),
         "updated_at": now.isoformat(), "scheduled_for": None, "dedupe_key": None,
         "worker_id": None, "lease_expires_at": None}
        for i in range(7)
    ])
    selects: list[tuple] = []
    real_table = client.table

    def spy_table(name):
        builder = real_table(name)
        orig = builder.select

        def select(cols="*", *a, **k):
            selects.append((cols, k.get("count")))
            return orig(cols, *a, **k)

        builder.select = select
        return builder

    client.table = spy_table  # observation only; the repo's own code is untouched
    repo = RealSupabaseJobRepository(client)
    stats = run(repo.queue_stats(job_types=["t"]))
    assert stats.pending == 7 and stats.due == 7
    assert not any(cols == "*" for cols, _ in selects), selects
    assert sum(1 for _, c in selects if c == "exact") >= 3
    before = len(selects)
    run(repo.queue_stats(job_types=["t"]))  # within the TTL: zero DB calls
    assert len(selects) == before


def test_in_process_enqueue_wakes_an_idle_backed_off_worker() -> None:
    """A job enqueued in this process is claimed at once, not after the
    (up to 30s) idle sleep; works from another thread too."""
    import threading
    import time

    async def scenario() -> list[float]:
        repo = FakeJobRepository()
        stop = asyncio.Event()
        done: list[float] = []

        async def handler(_job) -> None:
            done.append(time.monotonic())

        worker = Worker(
            repo, worker_id="w", handlers={"a": handler}, poll_interval_seconds=0.05,
            max_idle_interval_seconds=30.0,
        )
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        await asyncio.sleep(0.8)  # idle sleeps have grown well past 0.2s
        t0 = time.monotonic()
        await repo.enqueue(type="a", payload={})
        await asyncio.sleep(0.2)
        t1 = time.monotonic()
        # off-loop producer (run_blocking / to_thread shape)
        th = threading.Thread(target=lambda: asyncio.run(repo.enqueue(type="a", payload={})))
        th.start()
        th.join()
        await asyncio.sleep(0.2)
        stop.set()
        await task
        return [done[0] - t0, done[1] - t1]

    first, second = run(scenario())
    assert first < 0.15 and second < 0.15, (first, second)


def test_real_enqueue_drops_the_queue_stats_cache() -> None:
    client = MockSupabaseClient()
    client.set_table_data("jobs", [])
    repo = RealSupabaseJobRepository(client)
    run(repo.queue_stats(job_types=["t"]))
    assert repo._stats_cache
    run(repo.enqueue(type="t", payload={}))
    assert not repo._stats_cache


def test_real_future_dated_enqueue_drops_the_stats_cache_but_does_not_wake_the_worker() -> None:
    """The queue COUNT changed (a claim gate must see it) even though nothing is claimable yet; but a future-dated job
    must not cut an idle worker's sleep."""
    from noctusai_lib.domain.jobs import wake

    client = MockSupabaseClient()
    client.set_table_data("jobs", [])
    repo = RealSupabaseJobRepository(client)

    async def drive() -> tuple[bool, bool, bool, bool]:
        w = wake.register(asyncio.get_running_loop(), ["t"])
        await repo.queue_stats(job_types=["t"])
        warmed = bool(repo._stats_cache)
        await repo.enqueue(type="t", payload={}, scheduled_for=datetime.now(timezone.utc) + timedelta(hours=1))
        await asyncio.sleep(0.01)
        dropped, woke_future = not repo._stats_cache, w.event.is_set()
        await repo.queue_stats(job_types=["t"])
        await repo.enqueue(type="t", payload={})
        await asyncio.sleep(0.01)
        woke_now = w.event.is_set()
        wake.unregister(w)
        return warmed, dropped, woke_future, woke_now

    warmed, dropped, woke_future, woke_now = asyncio.run(drive())
    assert warmed and dropped, "a future-dated enqueue must still invalidate the stats cache"
    assert woke_future is False and woke_now is True
