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
