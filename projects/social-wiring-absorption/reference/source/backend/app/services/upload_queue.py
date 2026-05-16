"""Global single-flight upload queue.

Backs YouTube uploads with a Redis-backed FIFO queue + one-in-flight
semantics. The head of the queue is considered "in flight"; everyone
else waits their turn. Position 1 == about to run.

Why global single-flight (not per-conversation, not bounded-parallel):

  - YouTube's per-channel concurrent-upload limit is small (~3) and
    exhaustion of the daily quota (100 units / upload, 10k daily) is
    the dominant failure mode. Serializing protects against quota
    bursts and gives the operator predictable scheduling.
  - Per-conversation single-flight is the wrong unit — different team
    members triggering uploads from different numbers would still
    contend for the same YT channel quota.
  - Bounded parallel (e.g. N=3) is the obvious upgrade once usage
    grows. Swap the lock semantics here and the rest of the pipeline
    stays unchanged.

Design:

  - Single Redis LIST: ``upload:queue`` (FIFO, RPUSH/LPOP-ish ops).
  - ``enqueue(job_id)`` RPUSHes the job, returns the 1-based position.
  - ``wait_for_turn(job_id, on_position_change)`` polls every N seconds
    until the job is at the head; fires the callback on every position
    transition so the bot can ping "🕐 Posição 2 → 1".
  - ``release(job_id)`` LREMs the entry (head or otherwise).

Idempotency: ``enqueue`` checks for an existing entry before pushing
(prevents double-queue on bot retry). ``release`` is safe to call when
the entry doesn't exist (a no-op LREM).

Stale-detection: a head entry that's been there longer than
``stale_after_seconds`` (default 30 min) is auto-released by the next
caller's poll loop. Crude but works for the low-traffic single-operator
case; replace with a heartbeat/lease if multi-instance grows.

This module is NOT the seed pattern (`noctusai_lib` ships
``ConversationBufferService`` but no upload queue). If a second product
ever needs the same shape, lift into seed-lib at that point per the
recurrence rule (N=2 → triage).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)


_QUEUE_KEY = "upload:queue"

# Stale-head detection: if the head entry has been at position 1 for
# longer than this, assume the holder crashed and auto-LPOP it. Generous
# default since real uploads can take 5-10 min for large files.
STALE_AFTER_SECONDS = 30 * 60


class QueueError(Exception):
    """Queue-side failure — usually "job not in queue" or "Redis down"."""


class _RedisLike(Protocol):
    """Tiny subset of redis-py we use. ``redis.Redis`` satisfies this
    naturally; tests can pass an in-memory fake."""

    def rpush(self, name: str, *values: str) -> int: ...

    def lrange(self, name: str, start: int, end: int) -> list[Any]: ...

    def lrem(self, name: str, count: int, value: str) -> int: ...

    def lpop(self, name: str) -> Any: ...


class UploadQueue:
    """Redis-backed single-flight queue.

    Pass an existing Redis client (``redis.from_url(...)`` shape) to
    the constructor. The queue does NOT manage its own Redis lifecycle —
    callers share the connection used by the conversation buffer +
    intake state machine.

    Thread-safety: Redis ops are atomic; the queue is safe to use from
    multiple asyncio tasks. Multi-process safety: also fine (Redis is
    the single source of truth).
    """

    def __init__(self, redis_client: _RedisLike, queue_key: str = _QUEUE_KEY):
        self._redis = redis_client
        self._queue_key = queue_key

    # ─── Public API ────────────────────────────────────────────────────

    def enqueue(self, job_id: str) -> int:
        """Add ``job_id`` to the queue (idempotent). Returns 1-based
        position. Position 1 means the job is at the head — ready to run.

        Idempotency: re-enqueueing a job_id already present returns its
        existing position instead of pushing a duplicate. Important
        because ``_run_upload`` can be re-entered (e.g. after
        ``_handle_video_choice``).
        """
        existing = self._position_of(job_id)
        if existing > 0:
            logger.debug(
                "enqueue: job %s already in queue at position %d", job_id, existing
            )
            return existing

        entry = json.dumps({"job_id": job_id, "enqueued_at": time.time()})
        self._redis.rpush(self._queue_key, entry)
        return self._position_of(job_id) or 1  # fall back to 1 on race

    def release(self, job_id: str) -> None:
        """Remove ``job_id`` from the queue. Safe to call when absent."""
        entries = self._entries()
        for raw in entries:
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if parsed.get("job_id") == job_id:
                self._redis.lrem(self._queue_key, 1, raw)
                return

    def position(self, job_id: str) -> int:
        """Public 1-based position lookup; 0 == not queued."""
        return self._position_of(job_id)

    async def wait_for_turn(
        self,
        job_id: str,
        *,
        max_concurrent: int = 1,
        on_position_change: Callable[[int], Awaitable[None]] | None = None,
        poll_seconds: float = 3.0,
    ) -> None:
        """Block until ``job_id`` is within the first ``max_concurrent`` slots.

        With ``max_concurrent=1`` (default), behaves as single-flight:
        wait until the job is at position 1 (head). With ``max_concurrent=3``,
        wait until position ≤ 3 — the queue acts as a bounded-parallel
        semaphore.

        Args:
            job_id: the job to wait for.
            max_concurrent: max simultaneous jobs that can run; positions
                1..N are "running", N+1..∞ are "waiting".
            on_position_change: optional async callback fired whenever
                the job's WAITING position changes (suppressed once the
                job enters the run band — at that point the caller is
                about to start work and a "position 1" ping is noise).
            poll_seconds: how often to re-check Redis. 3s is the empirical
                sweet spot — frequent enough that head-of-queue transitions
                feel responsive, infrequent enough that Redis stays cool.

        Raises:
            QueueError: ``job_id`` isn't in the queue (caller forgot
                to enqueue).
        """
        max_concurrent = max(1, max_concurrent)
        last_position: int | None = None
        while True:
            self._maybe_release_stale_head()
            pos = self._position_of(job_id)
            if pos == 0:
                raise QueueError(
                    f"job {job_id} not in queue — caller forgot to enqueue?"
                )
            if pos <= max_concurrent:
                return  # within the run band — caller runs the upload
            if on_position_change is not None and pos != last_position:
                try:
                    await on_position_change(pos)
                except Exception:
                    logger.exception(
                        "wait_for_turn: on_position_change callback failed (pos=%d)", pos
                    )
            last_position = pos
            await asyncio.sleep(poll_seconds)

    # ─── Internals ─────────────────────────────────────────────────────

    def _entries(self) -> list[str]:
        """Read the full queue list, decoding bytes→str where needed."""
        raw = self._redis.lrange(self._queue_key, 0, -1) or []
        return [r.decode("utf-8") if isinstance(r, bytes) else str(r) for r in raw]

    def _position_of(self, job_id: str) -> int:
        """1-based position of ``job_id``; 0 == not in queue."""
        for idx, raw in enumerate(self._entries(), start=1):
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if parsed.get("job_id") == job_id:
                return idx
        return 0

    def _maybe_release_stale_head(self) -> None:
        """Auto-release the head if it's been there past the stale threshold.

        Cheap to call before every poll — does nothing in the steady
        state where heads turn over normally. Only kicks in when the
        process holding the head crashed or hung.
        """
        entries = self._entries()
        if not entries:
            return
        try:
            head = json.loads(entries[0])
        except Exception:
            # Corrupt entry at head — LREM via raw value works.
            self._redis.lrem(self._queue_key, 1, entries[0])
            return
        enqueued_at = head.get("enqueued_at") or 0
        age = time.time() - float(enqueued_at)
        if age > STALE_AFTER_SECONDS:
            logger.warning(
                "upload_queue: releasing stale head job=%s (age=%.0fs > %ds)",
                head.get("job_id"),
                age,
                STALE_AFTER_SECONDS,
            )
            self._redis.lrem(self._queue_key, 1, entries[0])


__all__ = ["QueueError", "STALE_AFTER_SECONDS", "UploadQueue"]
