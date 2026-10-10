"""WorkerHandle -- start/stop/is_running over a seed Worker."""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository, Worker, WorkerHandle


def _worker(handlers=None) -> Worker:
    return Worker(
        FakeJobRepository(),
        worker_id="w-handle",
        handlers=handlers or {},
        poll_interval_seconds=0.01,
    )


class _Stubborn:
    """A worker that ignores the stop event (what a wedged handler looks like)."""

    def __init__(self) -> None:
        self.cancelled = False

    async def run_forever(self, *, stop_event=None) -> None:
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _Crashing:
    async def run_forever(self, *, stop_event=None) -> None:
        raise RuntimeError("boom")


def test_start_runs_and_stop_stops_cleanly():
    async def go():
        handle = WorkerHandle(_worker(), name="t")
        assert not handle.is_running()
        assert handle.start() is True
        assert handle.is_running()
        await handle.stop()
        assert not handle.is_running()

    asyncio.run(go())


def test_start_is_idempotent():
    async def go():
        handle = WorkerHandle(_worker())
        handle.start()
        first = handle._task
        handle.start()
        assert handle._task is first
        await handle.stop()

    asyncio.run(go())


def test_stop_without_start_is_a_noop():
    asyncio.run(WorkerHandle(_worker()).stop())


def test_restart_after_stop():
    async def go():
        handle = WorkerHandle(_worker())
        handle.start()
        await handle.stop()
        handle.start()
        assert handle.is_running()
        await handle.stop()

    asyncio.run(go())


def test_stop_timeout_cancels_a_worker_that_ignores_the_stop_event():
    async def go():
        stubborn = _Stubborn()
        handle = WorkerHandle(stubborn, stop_timeout=0.05)  # type: ignore[arg-type]
        handle.start()
        await asyncio.sleep(0)  # let the task enter run_forever
        await handle.stop()
        assert stubborn.cancelled is True
        assert not handle.is_running()

    asyncio.run(go())


def test_worker_processes_a_job_while_handled():
    async def go():
        repo = FakeJobRepository()
        seen: list[str] = []

        async def handler(job) -> None:
            seen.append(job.type)

        await repo.enqueue(type="x", payload={})
        worker = Worker(repo, worker_id="w", handlers={"x": handler}, poll_interval_seconds=0.01)
        handle = WorkerHandle(worker)
        handle.start()
        for _ in range(100):
            if seen:
                break
            await asyncio.sleep(0.01)
        await handle.stop()
        assert seen == ["x"]

    asyncio.run(go())


def test_crashed_worker_does_not_make_stop_raise_and_reports_not_running():
    async def go():
        handle = WorkerHandle(_Crashing())  # type: ignore[arg-type]
        handle.start()
        await asyncio.sleep(0.01)
        assert not handle.is_running()
        await handle.stop()

    asyncio.run(go())


def test_rejects_non_positive_stop_timeout():
    with pytest.raises(ValueError):
        WorkerHandle(_worker(), stop_timeout=0)
