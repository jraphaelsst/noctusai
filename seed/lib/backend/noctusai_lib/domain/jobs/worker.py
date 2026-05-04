"""Generic job worker — domain-agnostic poll loop + dispatch.

Lifts the lifecycle/loop/sleep shape from
`noctusai_lib.domain.chatbot.worker.ConversationWorker` (chatbot-coupled
today) into a generic surface that any product with background work
can consume — YouTube uploads, scheduling tasks, AI batches, future
long-running products. The chatbot worker is left INTACT for chatbot
consumers; this is a sibling module.

Wiring recipe (consumer-side):

    repo = make_job_repository(use_fake=False, supabase_client=client)
    worker = Worker(
        repo,
        worker_id="upload-worker-1",
        handlers={
            "youtube.upload": handle_upload,
            "youtube.metadata_refresh": handle_metadata_refresh,
        },
    )
    asyncio.create_task(worker.run_forever(stop_event=app_state.stop_event))

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
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from noctusai_lib.domain.jobs.entity import Job
from noctusai_lib.domain.jobs.repo import (
    DeadLetterError,
    JobRepository,
)
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
    ) -> None:
        self._repo = repo
        self._worker_id = worker_id
        self._handlers = dict(handlers)
        self._retry_policy = retry_policy
        self._poll_interval = poll_interval_seconds
        self._job_types: list[str] = sorted(self._handlers.keys())

    # --- public surface ----------------------------------------------

    async def run_once(self) -> bool:
        """Claim one job and dispatch it. Returns True if a job was
        processed (regardless of success/failure), False if the queue
        was empty."""
        job = await self._repo.claim_next(
            worker_id=self._worker_id,
            job_types=self._job_types,
        )
        if job is None:
            return False

        handler = self._handlers.get(job.type)
        if handler is None:
            # No handler for this type → mark failed (no retry, this
            # worker won't suddenly grow a handler). Operator should
            # reroute or requeue manually after wiring.
            error = (
                f"No handler registered for job type {job.type!r}; "
                f"available={self._job_types}"
            )
            logger.error("worker.no_handler job_id=%s type=%s", job.id, job.type)
            await self._repo.mark_failed(job.id, error, retry=False)
            return True

        await self._dispatch(job, handler)
        return True

    async def run_forever(
        self,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Loop run_once + sleep poll_interval. Honors stop_event.

        Pattern mirrors the chatbot worker: only sleep when the queue
        is empty, so steady-state load doesn't accumulate poll latency.
        """
        logger.info("worker.start worker_id=%s", self._worker_id)
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                processed = await self.run_once()
                if not processed:
                    # Queue empty — sleep up to poll_interval but wake
                    # immediately if stop_event fires.
                    if stop_event is None:
                        await asyncio.sleep(self._poll_interval)
                    else:
                        try:
                            await asyncio.wait_for(
                                stop_event.wait(),
                                timeout=self._poll_interval,
                            )
                        except asyncio.TimeoutError:
                            # Normal idle wakeup; loop back.
                            pass
        finally:
            logger.info("worker.stop worker_id=%s", self._worker_id)

    # --- internals ---------------------------------------------------

    async def _dispatch(self, job: Job, handler: JobHandler) -> None:
        """Run the handler and translate its outcome into repo calls.

        Failure modes (in order of catch):
        - `DeadLetterError`: handler explicitly signaled "give up" →
          mark_failed(retry=False) → DEAD_LETTER.
        - `Exception` (anything else): retryable failure →
          mark_failed(retry=True) → FAILED → PENDING (if retries left)
          or DEAD_LETTER (if exhausted).
        - `BaseException` (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
          mark_failed(retry=True) so the job isn't lost on shutdown,
          then re-raise so the loop unwinds.
        """
        try:
            await handler(job)
        except DeadLetterError as exc:
            logger.warning(
                "worker.dead_letter job_id=%s type=%s reason=%s",
                job.id,
                job.type,
                exc,
            )
            await self._repo.mark_failed(job.id, str(exc), retry=False)
            return
        except Exception as exc:
            logger.warning(
                "worker.retry job_id=%s type=%s retry_count=%d/%d error=%s",
                job.id,
                job.type,
                job.retry_count,
                job.max_retries,
                exc,
            )
            await self._repo.mark_failed(job.id, str(exc), retry=True)
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
                await self._repo.mark_failed(job.id, str(exc), retry=True)
            except Exception:
                logger.exception(
                    "worker.mark_failed_after_interrupt_failed job_id=%s",
                    job.id,
                )
            raise

        # Success path.
        await self._repo.mark_completed(job.id)


__all__ = [
    "JobHandler",
    "Worker",
]


# Re-export DeadLetterError for convenience: handlers commonly want to
# raise it without importing from `repo.py`.
_ = (DeadLetterError, Any)
