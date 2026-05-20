"""Unit tests for the global single-flight upload queue.

In-memory fake Redis driver — exercises the queue's contract without
touching a real Redis instance.
"""
from __future__ import annotations

import json
import time

import pytest

from app.modules.youtube.services.upload_queue import (
    QueueError,
    STALE_AFTER_SECONDS,
    UploadQueue,
)


class FakeRedis:
    """Minimal redis-py subset the queue uses. Backed by a list."""

    def __init__(self):
        self._lists: dict[str, list[str]] = {}

    def rpush(self, name: str, *values: str) -> int:
        bucket = self._lists.setdefault(name, [])
        bucket.extend(values)
        return len(bucket)

    def lrange(self, name: str, start: int, end: int):
        bucket = self._lists.get(name, [])
        if end == -1:
            return list(bucket[start:])
        return list(bucket[start : end + 1])

    def lrem(self, name: str, count: int, value: str) -> int:
        bucket = self._lists.get(name, [])
        try:
            bucket.remove(value)
            return 1
        except ValueError:
            return 0

    def lpop(self, name: str):
        bucket = self._lists.get(name, [])
        if not bucket:
            return None
        return bucket.pop(0)


@pytest.fixture
def queue() -> UploadQueue:
    return UploadQueue(FakeRedis())


def test_enqueue_returns_position_1_on_first_job(queue: UploadQueue):
    assert queue.enqueue("job-a") == 1


def test_enqueue_returns_increasing_positions(queue: UploadQueue):
    assert queue.enqueue("job-a") == 1
    assert queue.enqueue("job-b") == 2
    assert queue.enqueue("job-c") == 3


def test_enqueue_is_idempotent(queue: UploadQueue):
    """Re-enqueueing an existing job must return its current position
    without pushing a duplicate (otherwise the queue gets corrupted)."""
    queue.enqueue("job-a")
    queue.enqueue("job-b")
    assert queue.enqueue("job-a") == 1  # unchanged
    # Confirm only ONE entry for job-a
    positions = [queue.position(j) for j in ("job-a", "job-b")]
    assert positions == [1, 2]


def test_position_returns_zero_for_unknown_job(queue: UploadQueue):
    queue.enqueue("job-a")
    assert queue.position("nonexistent") == 0


def test_release_drops_entry_by_job_id(queue: UploadQueue):
    queue.enqueue("job-a")
    queue.enqueue("job-b")
    queue.release("job-a")
    assert queue.position("job-a") == 0
    assert queue.position("job-b") == 1  # promoted to head


def test_release_is_safe_when_absent(queue: UploadQueue):
    """Calling release for a job that isn't in the queue must NOT raise.
    Retry path relies on this idempotency."""
    queue.release("never-existed")  # would raise if not safe


def test_stale_head_is_auto_released(queue: UploadQueue):
    """A head entry older than STALE_AFTER_SECONDS gets evicted on the
    next position check. Models the "process holding the head crashed"
    case so a stuck head doesn't permanently block the queue."""
    redis = FakeRedis()
    # Manually craft a stale head entry.
    stale_entry = json.dumps(
        {"job_id": "stale-job", "enqueued_at": time.time() - STALE_AFTER_SECONDS - 60}
    )
    fresh_entry = json.dumps({"job_id": "fresh-job", "enqueued_at": time.time()})
    redis.rpush("upload:queue", stale_entry, fresh_entry)

    queue = UploadQueue(redis)
    # The next position call should sweep the stale head.
    queue._maybe_release_stale_head()
    assert queue.position("stale-job") == 0
    assert queue.position("fresh-job") == 1


def test_corrupt_entry_at_head_is_evicted(queue: UploadQueue):
    """A non-JSON entry at the head should be dropped so the queue can
    recover; otherwise one bad write could permanently block."""
    redis = FakeRedis()
    redis.rpush("upload:queue", "this-is-not-json", json.dumps({"job_id": "good"}))

    q = UploadQueue(redis)
    q._maybe_release_stale_head()
    assert q.position("good") == 1


@pytest.mark.asyncio
async def test_wait_for_turn_returns_immediately_when_at_head(queue: UploadQueue):
    """Most common case: caller enqueues, hits head, returns. No sleeps."""
    queue.enqueue("job-a")
    # Should resolve without any callback firing.
    fired = []

    async def cb(pos):  # pragma: no cover — must not be called
        fired.append(pos)

    await queue.wait_for_turn(
        "job-a", on_position_change=cb, poll_seconds=0.01
    )
    assert fired == []


@pytest.mark.asyncio
async def test_wait_for_turn_raises_when_not_in_queue(queue: UploadQueue):
    with pytest.raises(QueueError):
        await queue.wait_for_turn("nonexistent", poll_seconds=0.01)


@pytest.mark.asyncio
async def test_wait_for_turn_honors_max_concurrent_band(queue: UploadQueue):
    """With max_concurrent=2, positions 1 and 2 both proceed immediately;
    position 3 blocks (would loop). We verify the band by checking
    positions 1-2 return without callback firing."""
    queue.enqueue("job-a")  # position 1
    queue.enqueue("job-b")  # position 2

    fired = []

    async def cb(pos):
        fired.append(pos)

    await queue.wait_for_turn(
        "job-b", max_concurrent=2, on_position_change=cb, poll_seconds=0.01
    )
    assert fired == []  # position 2 ≤ 2 → in run band → no waiting ping
