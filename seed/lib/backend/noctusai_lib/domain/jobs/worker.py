"""Generic job worker — domain-agnostic poll loop + dispatch.

Lifts the lifecycle/loop/sleep shape from
`noctusai_lib.domain.chatbot.worker.ConversationWorker` (chatbot-coupled
today) into a generic surface that any product with background work
can consume — YouTube uploads, scheduling tasks, AI batches, future
long-running products. The chatbot worker is left INTACT for chatbot
consumers; this is a sibling module.

Wiring recipe (consumer-side):

    from noctusai_lib.primitives.tasks import schedule_coro

    repo = make_job_repository(use_fake=False, supabase_client=client)
    worker = Worker(
        repo,
        worker_id="upload-worker-1",
        handlers={
            "youtube.upload": handle_upload,
            "youtube.metadata_refresh": handle_metadata_refresh,
        },
    )
    schedule_coro(
        worker.run_forever(stop_event=app_state.stop_event),
        name="job-worker-1",
    )

Differences from `ConversationWorker`:
- async (asyncio) instead of sync (`time.sleep`) — fits FastAPI lifespans
  + multiple workers in one event loop.
- dispatch via `handlers: dict[str, Callable[[Job], Awaitable[None]]]`
  instead of fixed `processor` / `idle_processor` callables.
- failure semantics are typed (DeadLetterError vs other exceptions)
  rather than chatbot-specific empty-memory / clear-conversation logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from noctusai_lib.domain.jobs.entity import Job
from noctusai_lib.domain.jobs.repo import (
    DeadLetterError,
    JobRepository,
    LeaseLostError,
    RescheduleLater,
)
from noctusai_lib.domain.jobs import wake as _wake
from noctusai_lib.primitives.supabase_breaker import Breaker, get_breaker, source_scope
from noctusai_lib.domain.jobs.retry_policy import (
    DEFAULT_POLICY,
    RetryPolicy,
)

logger = logging.getLogger(__name__)


# A handler takes a Job and returns when its work is done. Raising any
# exception triggers a retry; raising DeadLetterError lands directly on
# DEAD_LETTER (skip retries).
JobHandler = Callable[[Job], Awaitable[None]]


class Worker:
    """Async polling worker that drains a `JobRepository`.

    Lifecycle:
        worker = Worker(repo, worker_id="w-1", handlers={...})
        await worker.run_forever(stop_event=stop_event)

    Single worker is single-threaded by design (one event-loop task);
    horizontal scale = run multiple Worker instances in different
    processes / pods. The repo's `claim_next` keeps them from
    fighting over the same job.
    """

    def __init__(
        self,
        repo: JobRepository,
        *,
        worker_id: str,
        handlers: dict[str, JobHandler],
        retry_policy: RetryPolicy = DEFAULT_POLICY,
        poll_interval_seconds: float = 1.0,
        lease_seconds: float = 600.0,
        heartbeat_interval_seconds: float | None = None,
        claim_gate: Callable[[], Awaitable[bool]] | None = None,
        max_idle_interval_seconds: float = 30.0,
        idle_backoff_multiplier: float = 2.0,
        idle_sleep: Callable[[float, asyncio.Event | None], Awaitable[None]] | None = None,
        breaker: Breaker | None = None,
        held_poll_seconds: float = 15.0,
    ) -> None:
        self._repo = repo
        # Supabase request breaker (2026-11-10): every Supabase call this worker's loop and handlers make is counted
        # under `worker:<job types>`; a runaway rate trips it and the loop PARKS (zero Supabase calls) until a human
        # re-arms. `breaker=None` -> the process breaker. KB § PATTERNS/backend/supabase-request-breaker.md
        self._breaker = breaker
        self._held_poll = held_poll_seconds
        self._breaker_wake: asyncio.Event | None = None
        # Pause switch, consulted before EVERY claim: `False` ⇒ claim
        # nothing this cycle (jobs stay queued, the loop idles). Lets an
        # operator pause/resume a live worker from data (a settings row)
        # without restarting the process. A gate that RAISES counts as
        # closed — failing open would run paid work nobody authorized.
        self._claim_gate = claim_gate
        self.last_gate_error: str | None = None
        self._worker_id = worker_id
        self._handlers = dict(handlers)
        self._retry_policy = retry_policy
        self._poll_interval = poll_interval_seconds
        # Idle backoff (egress incident, 2026-11-09): a fixed 1s idle poll
        # against an EMPTY queue made ~10 product workers fire ~15k
        # `claim_next_job` RPCs per hour and exhausted the Supabase egress
        # quota (every REST call then returned 402). Each consecutive idle
        # poll now doubles the sleep up to `max_idle_interval_seconds`, and
        # the first claimed job resets it to `poll_interval_seconds`. At the
        # 30s cap that is ~120 claim calls/hour PER worker (~1.2k/hour for ~10
        # workers). In-process enqueues wake the worker at once (`jobs/wake.py`).
        self._max_idle_interval = max(max_idle_interval_seconds, poll_interval_seconds)
        self._idle_multiplier = max(idle_backoff_multiplier, 1.0)
        self._idle_sleep = idle_sleep or self._default_idle_sleep
        self._waker: _wake.Waker | None = None
        self._job_types: list[str] = sorted(self._handlers.keys())
        # Lease + heartbeat: a claimed job is reclaimable by another
        # worker once `lease_seconds` elapses without a heartbeat — the
        # crash-recovery path for a worker that dies mid-photo. The
        # heartbeat fires at half the lease window by default, so two
        # missed heartbeats (not one) are needed before a live worker's
        # job gets stolen.
        self._lease_seconds = lease_seconds
        self._heartbeat_interval = (
            heartbeat_interval_seconds
            if heartbeat_interval_seconds is not None
            else lease_seconds / 2
        )

    # --- public surface ----------------------------------------------

    async def run_once(self) -> bool:
        """Claim one job and dispatch it. Returns True if a job was
        processed (regardless of success/failure), False if the queue
        was empty (or the claim gate is closed)."""
        if not await self.claim_allowed():
            return False
        job = await self._repo.claim_next(
            worker_id=self._worker_id,
            job_types=self._job_types,
            lease_seconds=self._lease_seconds,
        )
        if job is None:
            return False

        handler = self._handlers.get(job.type)
        if handler is None:
            # No handler for this type → dead-letter (no retry, this
            # worker won't suddenly grow a handler). Operator should
            # reroute or requeue manually after wiring.
            error = (
                f"No handler registered for job type {job.type!r}; "
                f"available={self._job_types}"
            )
            logger.error("worker.no_handler job_id=%s type=%s", job.id, job.type)
            await self._repo.mark_failed(job.id, error, dead_letter=True)
            return True

        await self._dispatch(job, handler)
        return True

    @property
    def breaker_source(self) -> str:
        """The breaker source name: ``worker:<sorted job types>``."""
        return "worker:" + ",".join(self._job_types)

    async def claim_allowed(self) -> bool:
        """The claim gate's current answer (`True` when there is no gate)."""
        if self._claim_gate is None:
            return True
        try:
            allowed = bool(await self._claim_gate())
        except Exception as exc:
            if self.last_gate_error is None:
                logger.exception("worker.claim_gate_failed worker_id=%s", self._worker_id)
            self.last_gate_error = f"{type(exc).__name__}: {exc}"
            return False
        self.last_gate_error = None
        return allowed

    async def run_forever(
        self,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Loop run_once; when idle, sleep with exponential backoff.

        Only sleeps when the queue is empty (steady-state load does not
        accumulate poll latency). The idle sleep starts at
        `poll_interval_seconds`, multiplies by `idle_backoff_multiplier`
        per consecutive empty poll up to `max_idle_interval_seconds`, and
        resets the moment a job is processed. `stop_event` still wakes
        the sleep immediately. Why: see `__init__` (2026-11-09 egress
        incident: fixed 1s polling of an empty queue).
        """
        logger.info("worker.start worker_id=%s", self._worker_id)
        delay = self._poll_interval
        # In-process enqueues of a type this worker serves cut the idle
        # sleep (see `jobs/wake.py`); cross-process producers wait <= cap.
        loop = asyncio.get_running_loop()
        self._waker = _wake.register(loop, self._job_types)
        breaker = self._breaker or get_breaker()
        source = self.breaker_source
        self._breaker_wake = bk_wake = asyncio.Event()
        unsubscribe = breaker.subscribe(source, lambda: loop.call_soon_threadsafe(bk_wake.set))
        try:
            with source_scope(source):
                # A held source does NOT start on boot: the check below reads Redis (force) before the first claim.
                hold = await breaker.check(source, force=True)
                while True:
                    if stop_event is not None and stop_event.is_set():
                        break
                    bk_wake.clear()
                    if hold:
                        if not await self._park(breaker, source, hold, stop_event):
                            break
                        delay = self._poll_interval
                    # A wake that lands before this claim is covered by the claim
                    # itself; one that lands after it ends the next idle sleep.
                    if self._waker is not None:
                        self._waker.event.clear()
                    processed = await self.run_once()
                    hold = await breaker.check(source)
                    if hold:
                        continue  # tripped (or fleet-held) while that job ran: it finished; now stop claiming
                    if processed:
                        delay = self._poll_interval
                        continue
                    await self._idle_sleep(delay, stop_event)
                    if self._waker is not None and self._waker.event.is_set():
                        delay = self._poll_interval
                    else:
                        delay = min(delay * self._idle_multiplier, self._max_idle_interval)
        finally:
            unsubscribe()
            self._breaker_wake = None
            if self._waker is not None:
                _wake.unregister(self._waker)
                self._waker = None
            logger.info("worker.stop worker_id=%s", self._worker_id)

    async def _park(
        self, breaker: Breaker, source: str, hold: dict, stop_event: asyncio.Event | None
    ) -> bool:
        """The breaker holds this source: claim NOTHING (zero Supabase calls) until it is re-armed. Re-checks Redis
        every `held_poll_seconds` (one cached MGET, never Supabase). Returns False if asked to stop meanwhile."""
        logger.critical(
            "worker.held_by_breaker worker_id=%s source=%s scope=%s reason=%s — NOT claiming jobs until a human "
            "re-arms (noctus.dev.supabase_breaker / the platform-admin route)",
            self._worker_id, source, hold.get("scope"), hold.get("reason"),
        )
        while True:
            if stop_event is not None and stop_event.is_set():
                return False
            assert self._breaker_wake is not None
            self._breaker_wake.clear()
            await self._idle_sleep_held(stop_event)
            if stop_event is not None and stop_event.is_set():
                return False
            hold = await breaker.check(source, force=True)
            if hold is None:
                logger.warning("worker.released_by_breaker worker_id=%s source=%s — resuming", self._worker_id, source)
                return True

    async def _idle_sleep_held(self, stop_event: asyncio.Event | None) -> None:
        events = [e for e in (stop_event, self._breaker_wake) if e]
        tasks = [asyncio.ensure_future(e.wait()) for e in events]
        try:
            await asyncio.wait(tasks, timeout=self._held_poll, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # --- internals ---------------------------------------------------

    async def _default_idle_sleep(self, delay: float, stop_event: asyncio.Event | None) -> None:
        """Sleep up to `delay`; return early on stop_event or an in-process wake."""
        events = [
            e
            for e in (stop_event, self._waker.event if self._waker else None, self._breaker_wake)
            if e
        ]
        if not events:
            await asyncio.sleep(delay)
            return
        tasks = [asyncio.ensure_future(e.wait()) for e in events]
        try:
            await asyncio.wait(tasks, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _heartbeat_loop(self, job_id: str) -> None:
        """Extend the claimed job's lease at `_heartbeat_interval` while
        the handler runs, so a legitimately slow (but alive) worker
        never loses its job to another worker's `claim_next` reclaim.
        Cancelled by `_dispatch` once the handler returns.

        If `extend_lease` reports `LeaseLostError` (another worker has
        already reclaimed the job — this worker was too slow, or hung
        long enough for two missed heartbeats), the loop stops; the
        in-flight handler's eventual `mark_completed`/`mark_failed`
        call is still made (see `_dispatch`) but is now a race against
        the reclaiming worker, which the repo's own atomicity resolves
        (e.g. `complete_job` is a no-op once already COMPLETED).
        """
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                try:
                    await self._repo.extend_lease(
                        job_id,
                        worker_id=self._worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                except LeaseLostError:
                    logger.warning(
                        "worker.lease_lost job_id=%s worker_id=%s",
                        job_id,
                        self._worker_id,
                    )
                    return
        except asyncio.CancelledError:
            raise

    async def _dispatch(self, job: Job, handler: JobHandler) -> None:
        """Run the handler (with a background lease-heartbeat) and
        translate its outcome into repo calls.

        Failure modes (in order of catch):
        - `DeadLetterError`: handler explicitly signaled "give up" →
          mark_failed(dead_letter=True) → DEAD_LETTER.
        - `Exception` (anything else): retryable failure →
          mark_failed(policy=self._retry_policy) → FAILED → PENDING
          (if retries remain under the policy) or DEAD_LETTER
          (if exhausted).
        - `BaseException` (KeyboardInterrupt, SystemExit,
          asyncio.CancelledError): mark_failed(...) so the job isn't
          lost on shutdown, then re-raise so the loop unwinds.
        """
        heartbeat_task = asyncio.ensure_future(self._heartbeat_loop(job.id))
        try:
            try:
                await handler(job)
            except DeadLetterError as exc:
                logger.warning(
                    "worker.dead_letter job_id=%s type=%s reason=%s",
                    job.id,
                    job.type,
                    exc,
                )
                await self._repo.mark_failed(job.id, str(exc), dead_letter=True)
                return
            except RescheduleLater as exc:
                # Not a failure: back to PENDING after the delay, retry
                # budget untouched.
                logger.info(
                    "worker.reschedule job_id=%s type=%s delay_s=%s",
                    job.id,
                    job.type,
                    exc.delay_s,
                )
                await self._repo.reschedule(job.id, delay_s=exc.delay_s)
                return
            except Exception as exc:
                logger.warning(
                    "worker.retry job_id=%s type=%s retry_count=%d error=%s",
                    job.id,
                    job.type,
                    job.retry_count,
                    exc,
                )
                await self._repo.mark_failed(
                    job.id, str(exc), policy=self._retry_policy
                )
                return
            except BaseException as exc:
                # Shutdown signals — surface the failure for diagnostics
                # but DO NOT swallow; let the loop unwind cleanly.
                logger.warning(
                    "worker.interrupted job_id=%s type=%s exc=%s",
                    job.id,
                    job.type,
                    type(exc).__name__,
                )
                try:
                    await self._repo.mark_failed(
                        job.id, str(exc), policy=self._retry_policy
                    )
                except Exception:
                    logger.exception(
                        "worker.mark_failed_after_interrupt_failed job_id=%s",
                        job.id,
                    )
                raise

            # Success path.
            await self._repo.mark_completed(job.id)
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task


__all__ = [
    "JobHandler",
    "Worker",
]


# Re-export DeadLetterError for convenience: handlers commonly want to
# raise it without importing from `repo.py`.
_ = (DeadLetterError, Any)
