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
import time
from collections.abc import Awaitable, Callable
from typing import Any

from noctusai_lib.domain.jobs.entity import Job
from noctusai_lib.domain.jobs.repo import (
    DeadLetterError,
    JobRepository,
    LeaseLostError,
    RescheduleLater,
)
from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.domain.jobs import wake as _wake
from noctusai_lib.primitives.supabase_breaker import (
    DEFAULT_JOB_CALL_CAP,
    Breaker,
    BreakerOpen,
    JobBudgetExceeded,
    call_tally,
    get_breaker,
    job_scope,
    source_scope,
)
from noctusai_lib.domain.jobs.retry_policy import (
    DEFAULT_POLICY,
    RetryPolicy,
)

logger = logging.getLogger(__name__)

# Idle-poll cap. 86400 / 300 = 288 claim RPCs/day per idle worker; ~20 worker
# loops fleet-wide ~= 5.8k/day (was 56k/day at the old 30s cap, W1-C 2026-11-12).
# Do not lower it per product: in-process enqueue/retry/reschedule wake the
# worker (`jobs/wake.py`); only cross-process producers wait the full cap.
DEFAULT_MAX_IDLE_INTERVAL_SECONDS = 300.0


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
        max_idle_interval_seconds: float = DEFAULT_MAX_IDLE_INTERVAL_SECONDS,
        idle_backoff_multiplier: float = 2.0,
        idle_sleep: Callable[[float, asyncio.Event | None], Awaitable[None]] | None = None,
        breaker: Breaker | None = None,
        held_poll_seconds: float = 15.0,
        job_call_cap: int = DEFAULT_JOB_CALL_CAP,
        job_call_caps: dict[str, int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        # Supabase request breaker (2026-11-10; PLATFORM-floor billing, round 7). Two separate things are watched:
        #  (a) LOOP CADENCE against a PLATFORM floor (`NOCTUS_MIN_IDLE_POLL_S`, default 10 s) — not the Worker's own
        #      declared cadence (a loop declaring poll=max_idle=1 s would otherwise always be "on cadence"). Every
        #      consecutive EMPTY poll whose gap from the previous empty poll is below the floor is billed (to the holdable
        #      `worker:<job types>`), EXCEPT: the first empty poll after a processed job; the first RAMP_FREE sub-floor
        #      polls of a backoff ramp; wake-followed empty polls, at most `max_free_wake_polls` per 5 min (so a producer
        #      that keeps waking the loop with nothing claimable cannot launder it); and failed claims while the loop
        #      applies its error backoff. Idle at >= the floor is never billed, and job-arrival volume (1-2 jobs/s) is
        #      free: each poll after work claims a job or is the free first empty. A loop that polls faster than the
        #      floor for long (no backoff, or max_idle below the floor) trips at 300 billed polls / 5 min or 2,000 / h
        #      and PARKS until a human re-arms. In a DEPLOY context a `max_idle_interval_seconds` below the floor is
        #      clamped to it (loudly) at construction.
        #  (b) JOB CALLS: per-job cap (`job_call_cap`, per-type `job_call_caps`): in OBSERVE mode (default) the cap
        #      only alerts and the job is dead-lettered at MAX_BUDGET_CALLS; `breaker.job_cap_enforce` flips it.
        # All other attribution (claim phase, handlers, bookkeeping) is alert-only. `breaker=None` -> process breaker.
        # KB § PATTERNS/backend/supabase-request-breaker.md
        self._breaker = breaker
        self._job_call_cap = job_call_cap
        self._job_call_caps = dict(job_call_caps or {})
        self._clock = clock
        self._last_empty_at: float | None = None
        self._poll_free = True  # the first poll (boot) and any poll after work / an error backoff is free
        self._woke_before_poll = False  # the idle sleep that preceded the next poll ended on an enqueue wake
        self._ramp = 0  # consecutive sub-floor empty polls since the last reset (the backoff ramp's free allowance)
        self._free_wakes: list[float] = []  # timestamps of wake-followed empty polls that were let through free
        self._last_poll_calls = 0
        self._last_claim_attempted = True  # False when the claim gate was closed: no claim, nothing to bill
        self._custom_idle_sleep = idle_sleep is not None
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
        # 300s cap that is 12 claim calls/hour PER worker (W1-C: the 30s cap still
        # cost 56k calls/day fleet-wide). In-process enqueues, retry backoffs and
        # reschedules wake the worker when due (`jobs/wake.py`). The breaker's
        # platform floor below only clamps a cap that is TOO LOW.
        _floor = (breaker or get_breaker())._config.min_idle_poll_s
        if max_idle_interval_seconds < _floor and is_deploy_context():
            logger.warning(
                "worker %s: max_idle_interval_seconds=%.1f is below the platform idle-poll floor %.1f s "
                "(NOCTUS_MIN_IDLE_POLL_S) — clamped to the floor in a deploy context",
                worker_id, max_idle_interval_seconds, _floor,
            )
            max_idle_interval_seconds = _floor
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
        job = None
        self._last_claim_attempted = False
        with call_tally() as tally, source_scope("claim:" + ",".join(self._job_types)):
            try:
                if await self.claim_allowed():
                    self._last_claim_attempted = True
                    job = await self._repo.claim_next(
                        worker_id=self._worker_id,
                        job_types=self._job_types,
                        lease_seconds=self._lease_seconds,
                    )
            finally:
                self._last_poll_calls = tally.n  # `run_forever` bills a cadence-violating empty poll from this
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
        """The loop's HOLDABLE breaker source: ``worker:<sorted job types>`` (empty polls only)."""
        return "worker:" + ",".join(self._job_types)

    @property
    def breaker_sources(self) -> list[str]:
        return [self.breaker_source]

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
        err_delay: float | None = None
        # In-process enqueues of a type this worker serves cut the idle
        # sleep (see `jobs/wake.py`); cross-process producers wait <= cap.
        loop = asyncio.get_running_loop()
        self._waker = _wake.register(loop, self._job_types)
        breaker = self._breaker or get_breaker()
        source = self.breaker_source
        self._breaker_wake = bk_wake = asyncio.Event()
        unsubscribes = [
            breaker.subscribe(src, lambda: loop.call_soon_threadsafe(bk_wake.set)) for src in self.breaker_sources
        ]
        try:
            with source_scope("loop:" + ",".join(self._job_types)):
                # A held source does NOT start on boot: the check below reads Redis (force) before the first claim.
                hold = await self._hold(breaker, force=True)
                while True:
                    if stop_event is not None and stop_event.is_set():
                        break
                    bk_wake.clear()
                    if hold:
                        if not await self._park(breaker, hold, stop_event):
                            break
                        delay = self._poll_interval
                    # A wake that lands before this claim is covered by the claim
                    # itself; one that lands after it ends the next idle sleep.
                    if self._waker is not None:
                        self._waker.event.clear()
                    try:
                        processed = await self.run_once()
                        err_delay = None
                    except BreakerOpen:
                        processed = False  # the claim itself was refused: the source is held now
                    except Exception:  # noqa: BLE001 -- an outage must back off, never kill the loop nor bill the breaker
                        err_delay = (
                            self._poll_interval if err_delay is None
                            else min(err_delay * self._idle_multiplier, self._max_idle_interval)
                        )
                        logger.exception("worker.claim_failed worker_id=%s backing off %.1fs", self._worker_id, err_delay)
                        self._poll_free = True  # the backoff IS the cadence: the next empty poll is free
                        self._last_empty_at = None
                        await self._error_sleep(err_delay, stop_event)
                        continue
                    hold = await self._hold(breaker)
                    if hold:
                        continue  # tripped (or fleet-held) while that job ran: it finished; now stop claiming
                    if processed:
                        delay = self._poll_interval
                        self._poll_free = True  # the first empty poll after work is free
                        continue
                    if not self._last_claim_attempted:
                        # PAUSED (claim gate closed): ignore job wakes and back off toward max_idle, like an outage —
                        # an enqueue stream must not turn a paused Worker into a gate-reading hot loop.
                        await self._error_sleep(delay, stop_event)
                        self._woke_before_poll = False
                        delay = min(delay * self._idle_multiplier, self._max_idle_interval)
                        continue
                    self._bill_empty_poll(breaker)
                    await self._idle_sleep(delay, stop_event)
                    if self._waker is not None and self._waker.event.is_set():
                        delay = self._poll_interval
                        self._woke_before_poll = True  # woken by an enqueue: the next empty poll may be free (capped)
                    else:
                        delay = min(delay * self._idle_multiplier, self._max_idle_interval)
        finally:
            for off in unsubscribes:
                off()
            self._breaker_wake = None
            if self._waker is not None:
                _wake.unregister(self._waker)
                self._waker = None
            logger.info("worker.stop worker_id=%s", self._worker_id)

    RAMP_FREE = 6  # a backoff ramp from 1 s doubles to >= the floor in ~4 steps: those sub-floor polls are not abuse
    WAKE_WINDOW_S = 300.0

    def _bill_empty_poll(self, breaker: Breaker) -> None:
        """Bill this empty poll to the loop when it is below the PLATFORM floor (see `__init__`)."""
        if not self._last_claim_attempted:
            return  # a paused Worker (claim gate closed) attempted no claim: there is nothing to bill, whatever the wakes
        now = self._clock()
        floor = breaker._config.min_idle_poll_s
        free_after_work, self._poll_free = self._poll_free, False
        woke, self._woke_before_poll = self._woke_before_poll, False
        last, self._last_empty_at = self._last_empty_at, now
        if free_after_work or last is None:
            self._ramp = 0
            return
        if now - last >= floor:  # honouring the floor: not billed, and the ramp starts over
            self._ramp = 0
            return
        self._ramp += 1
        if woke:
            self._free_wakes = [t for t in self._free_wakes if now - t < self.WAKE_WINDOW_S]
            if len(self._free_wakes) < breaker._config.max_free_wake_polls:
                self._free_wakes.append(now)
                return
        elif self._ramp <= self.RAMP_FREE:
            return
        if self._last_poll_calls > 0:  # bill what the poll REALLY cost (claim + gate Supabase calls), never a floor of 1
            breaker.record_call(self.breaker_source, n=self._last_poll_calls)

    async def _hold(self, breaker: Breaker, *, force: bool = False) -> dict | None:
        """The first hold among the loop's source and every job-type source it serves (a held TYPE parks the loop:
        claiming a job whose every Supabase call would be refused only churns claims)."""
        found = None
        for src in self.breaker_sources:
            breaker.register_source(src)  # all registered BEFORE the first (forced) read so one MGET covers them
        for src in self.breaker_sources:
            hold = await breaker.check(src, force=force)
            force = False  # one Redis read covers every registered source
            if hold is not None and found is None:
                found = hold
        return found

    async def _park(
        self, breaker: Breaker, hold: dict, stop_event: asyncio.Event | None
    ) -> bool:
        """The breaker holds this source: claim NOTHING (zero Supabase calls) until it is re-armed. Re-checks Redis
        every `held_poll_seconds` (one cached MGET, never Supabase). Returns False if asked to stop meanwhile."""
        logger.critical(
            "worker.held_by_breaker worker_id=%s source=%s scope=%s reason=%s — NOT claiming jobs until a human "
            "re-arms (noctus.dev.supabase_breaker / the platform-admin route)",
            self._worker_id, hold.get("source") or self.breaker_source, hold.get("scope"), hold.get("reason"),
        )
        while True:
            if stop_event is not None and stop_event.is_set():
                return False
            assert self._breaker_wake is not None
            self._breaker_wake.clear()
            await self._idle_sleep_held(stop_event)
            if stop_event is not None and stop_event.is_set():
                return False
            hold = await self._hold(breaker, force=True)
            if hold is None:
                logger.warning("worker.released_by_breaker worker_id=%s — resuming", self._worker_id)
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

    async def _error_sleep(self, delay: float, stop_event: asyncio.Event | None) -> None:
        """The error-backoff sleep: it ignores the in-process JOB waker (an enqueue must not cut an outage backoff short and
        turn it into a tight retry loop); it ends only on stop or a breaker event. An injected `idle_sleep` (tests) is used."""
        if self._custom_idle_sleep:
            await self._idle_sleep(delay, stop_event)
            return
        events = [e for e in (stop_event, self._breaker_wake) if e]
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
                except BreakerOpen:
                    logger.error(
                        "worker.heartbeat_refused job_id=%s worker_id=%s: breaker holds the loop; the lease will "
                        "expire and the job be reclaimed", job_id, self._worker_id,
                    )
                    return
        except asyncio.CancelledError:
            raise

    async def _dead_letter_over_cap(self, job: Job, budget: Any) -> bool:
        """The job made more Supabase calls than its hard limit, however its handler ended: dead-letter it."""
        logger.error("worker.job_call_cap job_id=%s type=%s calls=%d hard=%d", job.id, job.type, budget.count, budget.hard)
        await self._repo.mark_failed(
            job.id, f"supabase call cap exceeded: {budget.count} calls >= {budget.hard}", dead_letter=True
        )
        return False

    async def _dispatch(self, job: Job, handler: JobHandler) -> bool:
        """Run the handler (with a background lease-heartbeat) and
        translate its outcome into repo calls.

        Failure modes (in order of catch):
        - `DeadLetterError`: handler explicitly signaled "give up" →
          mark_failed(dead_letter=True) → DEAD_LETTER.
        - `Exception` (anything else): retryable failure →
          mark_failed(policy=self._retry_policy) → FAILED → PENDING
          (if retries remain under the policy) or DEAD_LETTER
          (if exhausted).
        - `BreakerOpen` (the Supabase breaker holds this job type, F4): the job is
          RELEASED (rescheduled, retry budget untouched) — never failed or
          dead-lettered. If even the release is refused (fleet hold) the job
          keeps its lease and is reclaimed after it expires.
        - `BaseException` (KeyboardInterrupt, SystemExit,
          asyncio.CancelledError): mark_failed(...) so the job isn't
          lost on shutdown, then re-raise so the loop unwinds.
        """
        heartbeat_task = asyncio.ensure_future(self._heartbeat_loop(job.id))
        budget = None
        try:
            try:
                # Each job runs under an alert-only `job:<type>` source and its own ABSOLUTE call cap; the bookkeeping
                # calls below run outside the job scope, so finishing a job is never refused by its own cap.
                cap = self._job_call_caps.get(job.type, self._job_call_cap)
                hard = (self._breaker or get_breaker()).job_hard_limit(cap)
                with source_scope(f"job:{job.type}"), job_scope(cap, hard=hard) as budget:
                    await handler(job)
            except JobBudgetExceeded as exc:
                logger.error("worker.job_call_cap job_id=%s type=%s %s", job.id, job.type, exc)
                await self._repo.mark_failed(job.id, f"supabase call cap exceeded: {exc}", dead_letter=True)
                return False
            except BreakerOpen as exc:
                logger.warning(
                    "worker.released_by_breaker job_id=%s type=%s source=%s",
                    job.id, job.type, exc.source,
                )
                try:
                    await self._repo.reschedule(job.id, delay_s=self._held_poll)
                except BreakerOpen:
                    logger.error(
                        "worker.release_refused job_id=%s: the breaker holds the loop too; the job keeps its lease "
                        "and is reclaimed when it expires",
                        job.id,
                    )
                return False
            except DeadLetterError as exc:
                logger.warning(
                    "worker.dead_letter job_id=%s type=%s reason=%s",
                    job.id,
                    job.type,
                    exc,
                )
                await self._repo.mark_failed(job.id, str(exc), dead_letter=True)
                return False
            except RescheduleLater as exc:
                # Not a failure: back to PENDING after the delay, retry
                # budget untouched.
                logger.info(
                    "worker.reschedule job_id=%s type=%s delay_s=%s",
                    job.id,
                    job.type,
                    exc.delay_s,
                )
                floor = (self._breaker or get_breaker())._config.min_idle_poll_s
                delay_s = max(exc.delay_s, floor)  # a handler cannot turn RescheduleLater(0) into a hot claim loop
                if delay_s != exc.delay_s:
                    logger.info("worker.reschedule_clamped job_id=%s %.1fs -> floor %.1fs", job.id, exc.delay_s, floor)
                await self._repo.reschedule(job.id, delay_s=delay_s)
                return True
            except Exception as exc:
                if budget is not None and budget.over:  # a handler's own `except` can swallow JobBudgetExceeded: not here
                    return await self._dead_letter_over_cap(job, budget)
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
                return False
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

            # Success path — unless the handler ran past its HARD call limit and swallowed the refusal itself.
            if budget is not None and budget.over:
                return await self._dead_letter_over_cap(job, budget)
            await self._repo.mark_completed(job.id)
            return True
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task


__all__ = [
    "DEFAULT_MAX_IDLE_INTERVAL_SECONDS",
    "JobHandler",
    "Worker",
]


# Re-export DeadLetterError for convenience: handlers commonly want to
# raise it without importing from `repo.py`.
_ = (DeadLetterError, Any)
