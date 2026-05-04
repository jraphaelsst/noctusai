"""Job entity + status state machine.

Pure-domain value object for any product needing background-job
processing — YouTube uploads, scheduling tasks, AI batches, future
long-running products. Lifted 2026-05-04 alongside the chatbot worker
generalization (§3a of `projects/seed-hardening-from-youtube-crawler`).

No IO here. The repo (`repo.py`) and worker (`worker.py`) consume this
module's frozen dataclass + pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Literal


class JobStatus(str, Enum):
    """Lifecycle states for a Job.

    PENDING → RUNNING → (COMPLETED | FAILED) → (RUNNING via retry | DEAD_LETTER)

    PENDING — enqueued, not yet picked up by a worker.
    RUNNING — claimed by a worker; processing in progress.
    COMPLETED — terminal happy path.
    FAILED — handler raised; retries remain → eligible for re-claim.
    DEAD_LETTER — retries exhausted OR fatal error; operator must intervene.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


# Outcome of a worker dispatch — the handler either succeeded, failed
# with a retryable exception, or signaled retries-exhausted.
JobOutcome = Literal["success", "retry", "exhausted"]


# Legal transitions. (current, target) → allowed?
# Anything not in the set raises in `with_status_transition`.
_LEGAL_TRANSITIONS: frozenset[tuple[JobStatus, JobStatus]] = frozenset(
    {
        (JobStatus.PENDING, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
        (JobStatus.RUNNING, JobStatus.FAILED),
        (JobStatus.RUNNING, JobStatus.DEAD_LETTER),
        # Retry path: a FAILED job becomes PENDING again so the next
        # poll picks it up via `claim_next`.
        (JobStatus.FAILED, JobStatus.PENDING),
        (JobStatus.FAILED, JobStatus.RUNNING),
        # Operator escape hatch: requeue a dead-lettered job.
        (JobStatus.DEAD_LETTER, JobStatus.PENDING),
    }
)


@dataclass(frozen=True)
class Job:
    """Background job — payload + lifecycle state.

    Frozen by design: every transition produces a new Job via
    `with_status_transition`. Repos return new instances; mutations are
    never in-place.
    """

    id: str
    type: str
    payload: dict
    status: JobStatus
    retry_count: int
    max_retries: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    scheduled_for: datetime | None = None

    # Internal: keep the dataclass hashable-friendly even with `dict`
    # field — we never hash Job; this just silences any tooling that
    # assumes frozen=True implies hashable.
    def __hash__(self) -> int:  # pragma: no cover - defensive
        return hash((self.id, self.status, self.retry_count))


def should_retry(job: Job) -> bool:
    """True iff the job has retries remaining.

    Pure predicate — no side effects, no clock read.
    """
    return job.retry_count < job.max_retries


def next_status(job: Job, outcome: JobOutcome) -> JobStatus:
    """Compute the next status for a RUNNING job given the worker outcome.

    `success` → COMPLETED.
    `retry` with retries left → FAILED (worker / repo will flip back to
        PENDING when re-enqueueing).
    `retry` with retries exhausted → DEAD_LETTER.
    `exhausted` → DEAD_LETTER (handler explicitly raised
        `ExhaustedRetriesError` or equivalent — no further retries).

    Caller is responsible for validating the input job is RUNNING; this
    function does NOT defensively check (state machine validation lives
    in `with_status_transition`).
    """
    if outcome == "success":
        return JobStatus.COMPLETED
    if outcome == "exhausted":
        return JobStatus.DEAD_LETTER
    if outcome == "retry":
        return JobStatus.FAILED if should_retry(job) else JobStatus.DEAD_LETTER
    raise ValueError(f"Unknown JobOutcome: {outcome!r}")


def with_status_transition(
    job: Job,
    new_status: JobStatus,
    *,
    error: str | None = None,
    now: datetime | None = None,
    increment_retry: bool = False,
) -> Job:
    """Return a new Job with `status = new_status` and `updated_at` bumped.

    Validates that (job.status, new_status) is in the legal-transitions
    set; otherwise raises `ValueError`. The original Job is never
    mutated.

    Args:
        job: source Job (immutable input).
        new_status: target status.
        error: optional error message — stored on `last_error` when
            transitioning into FAILED / DEAD_LETTER (anything else
            preserves the prior `last_error`).
        now: clock injection seam for deterministic tests; defaults to
            `datetime.now(timezone.utc)`.
        increment_retry: when True, bump `retry_count` by 1. Caller-driven
            so the worker can decide retry-counting semantics (typically
            on FAILED→PENDING re-enqueue).

    Raises:
        ValueError: if the transition is not in the legal set.
    """
    if (job.status, new_status) not in _LEGAL_TRANSITIONS:
        raise ValueError(
            f"Illegal Job status transition: {job.status.value} → {new_status.value}"
        )

    stamp = now or datetime.now(timezone.utc)

    # Persist `error` only when entering an error-bearing state. On
    # success / requeue we keep the prior message untouched (operator
    # diagnostics).
    if new_status in (JobStatus.FAILED, JobStatus.DEAD_LETTER):
        last_error = error if error is not None else job.last_error
    else:
        last_error = job.last_error

    return replace(
        job,
        status=new_status,
        updated_at=stamp,
        last_error=last_error,
        retry_count=job.retry_count + 1 if increment_retry else job.retry_count,
    )


__all__ = [
    "Job",
    "JobOutcome",
    "JobStatus",
    "next_status",
    "should_retry",
    "with_status_transition",
]
