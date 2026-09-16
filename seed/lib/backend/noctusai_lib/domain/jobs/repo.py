"""Job repository — Protocol + Fake + RealSupabase + factory.

Mirrors the canonical Protocol+Fake+Real+factory shape per
`KB § PATTERNS/seed-fake-real-adapter.md`. Consumers wire
`make_job_repository(use_fake=True)` for dev/tests and
`make_job_repository(supabase_client=client, schema_name=...)` in
production.

The seed ships `migrations/jobs.sql.template` (copy into your product's
`migrations/`, substitute `{{SCHEMA_NAME}}`, renumber — same recipe as
`domain/ai/migrations/tool_call_audits.sql.template`). It creates the
`jobs` table AND the four RPCs this Real implementation calls:
`claim_next_job` / `fail_job` / `complete_job` / `extend_lease`. Every
one of those RPCs does its work in a SINGLE `UPDATE ... RETURNING *`
statement — no consumer-side read-then-write race window.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from noctusai_lib.domain.jobs.entity import (
    Job,
    JobStatus,
    with_status_transition,
)
from noctusai_lib.domain.jobs.retry_policy import (
    DEFAULT_POLICY,
    RetryPolicy,
    next_retry_at,
)


class DeadLetterError(RuntimeError):
    """Raised by handlers that want to skip retries and land directly
    on DEAD_LETTER. Worker catches this and marks the job
    `mark_failed(..., dead_letter=True)`.
    """


class LeaseLostError(RuntimeError):
    """Raised by `extend_lease` when the caller no longer holds the
    job's lease — another worker's `claim_next` already reclaimed it
    after the lease window elapsed (this worker died, hung, or was too
    slow to heartbeat). The caller MUST stop processing and discard any
    in-progress work; the reclaiming worker owns the job now.
    """


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueueStats:
    """Operator snapshot of a job table (health panels).

    `pending` counts PENDING jobs (due now or scheduled later — `due` is
    the subset claimable right now); `running` counts RUNNING jobs with a
    live lease; `lease_expired` counts RUNNING jobs whose lease lapsed (a
    worker died — the next claim reclaims them). `last_error` is the most
    recently updated job carrying an error (any status)."""

    pending: int = 0
    due: int = 0
    running: int = 0
    lease_expired: int = 0
    dead_letter: int = 0
    last_error: str | None = None
    last_error_type: str | None = None
    last_error_at: datetime | None = None
    active_workers: tuple[str, ...] = ()


@runtime_checkable
class JobRepository(Protocol):
    """Async repository surface every Job consumer depends on.

    Implementations:
    - `FakeJobRepository` — in-memory dict-of-jobs for dev + tests.
    - `RealSupabaseJobRepository` — production-shaped Supabase-client
      backed implementation. Consumer ships `migrations/jobs.sql.template`.

    Concurrency contract: `claim_next` MUST be atomic — two workers
    racing on the same pending job MUST NOT both receive it. Real
    impl uses Postgres `FOR UPDATE SKIP LOCKED` via an RPC. Fake impl
    serializes via Python's GIL + the in-memory dict (single-process
    tests).
    """

    async def claim_next(
        self,
        *,
        worker_id: str,
        job_types: list[str] | None = None,
        lease_seconds: float = 600.0,
    ) -> Job | None:
        """Atomically pick the oldest eligible job and transition/reclaim
        it to RUNNING under a fresh lease of `lease_seconds`. Returns the
        claimed Job or None if nothing is eligible.

        Eligible = (`status == PENDING` AND (`scheduled_for is None` OR
        `scheduled_for <= now`)) OR (`status == RUNNING` AND
        `lease_expires_at <= now` — a worker died mid-job without
        completing, failing, or heartbeating via `extend_lease`).
        """

    async def extend_lease(
        self, job_id: str, *, worker_id: str, lease_seconds: float = 600.0
    ) -> Job:
        """Heartbeat: push a RUNNING job's `lease_expires_at` forward by
        `lease_seconds` from now. Only succeeds while `worker_id` still
        owns the job (status RUNNING AND `worker_id` matches) —
        otherwise raises `LeaseLostError`: another worker already
        reclaimed the job and the caller must abandon its work.
        """

    async def mark_completed(self, job_id: str) -> None:
        """Transition job to COMPLETED + release the lease. Idempotent
        on COMPLETED (no-op if already terminal). Raises if job is
        missing.
        """

    async def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        policy: RetryPolicy = DEFAULT_POLICY,
        dead_letter: bool = False,
    ) -> Job:
        """Atomically decide retry-vs-dead-letter against `policy` and
        transition in ONE step — never a prior read of `retry_count`.

        `dead_letter=True` forces DEAD_LETTER unconditionally (the
        handler explicitly raised `DeadLetterError`; no retries
        wanted). Otherwise: retry while `retry_count < policy.max_retries`
        — flips back to PENDING with `retry_count` bumped and
        `scheduled_for` set via `next_retry_at(retry_count, policy,
        now)`; lands on DEAD_LETTER once exhausted. Releases the lease
        either way. Returns the updated Job.
        """

    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        max_retries: int = 3,
        scheduled_for: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> Job:
        """Insert a new PENDING job and return it.

        When `dedupe_key` is given and a job with that key already
        exists, this is a NO-OP: the pre-existing Job is returned
        unchanged and no new row is created. This is the idempotency
        contract for re-enqueueing the same logical unit of work
        (e.g. a retried upstream webhook, a duplicate submit click).
        """

    async def list_dead_letters(
        self,
        *,
        type: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """Return DEAD_LETTER jobs for operator triage."""

    async def requeue_dead_letter(self, job_id: str) -> Job:
        """Move a DEAD_LETTER job back to PENDING and reset retry_count.
        Operator escape hatch.
        """

    async def queue_stats(self, *, job_types: list[str] | None = None) -> QueueStats:
        """Counts per state + the latest error, for operator health panels.
        Read-only; never claims or mutates."""


# ---------------------------------------------------------------------------
# Fake implementation
# ---------------------------------------------------------------------------


class FakeJobRepository:
    """In-memory `JobRepository` for dev + tests.

    Deterministic:
    - `claim_next` walks jobs in insertion order (Python 3.7+ dict
      preserves insertion order).
    - `enqueue` returns a Job with a stable monotonic id
      (`fake-job-<n>`) so test assertions don't depend on uuid4.

    Single-process only. No locking — relies on Python's GIL +
    cooperative async (no `await` in the critical sections), which is
    also why every method here is a genuinely atomic transition: there
    is no `await` between reading `self._jobs[job_id]` and writing it
    back.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._next_id: int = 1
        self._dedupe_index: dict[str, str] = {}

    # --- helpers -----------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _allocate_id(self) -> str:
        ident = f"fake-job-{self._next_id}"
        self._next_id += 1
        return ident

    # --- Protocol methods --------------------------------------------

    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        max_retries: int = 3,
        scheduled_for: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> Job:
        if dedupe_key is not None:
            existing_id = self._dedupe_index.get(dedupe_key)
            if existing_id is not None:
                return self._jobs[existing_id]

        now = self._now()
        job = Job(
            id=self._allocate_id(),
            type=type,
            payload=dict(payload),
            status=JobStatus.PENDING,
            retry_count=0,
            max_retries=max_retries,
            last_error=None,
            created_at=now,
            updated_at=now,
            scheduled_for=scheduled_for,
            dedupe_key=dedupe_key,
        )
        self._jobs[job.id] = job
        if dedupe_key is not None:
            self._dedupe_index[dedupe_key] = job.id
        return job

    async def claim_next(
        self,
        *,
        worker_id: str,
        job_types: list[str] | None = None,
        lease_seconds: float = 600.0,
    ) -> Job | None:
        now = self._now()
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        for job_id, job in self._jobs.items():
            if job_types is not None and job.type not in job_types:
                continue
            eligible_pending = job.status is JobStatus.PENDING and (
                job.scheduled_for is None or job.scheduled_for <= now
            )
            eligible_reclaim = (
                job.status is JobStatus.RUNNING
                and job.lease_expires_at is not None
                and job.lease_expires_at <= now
            )
            if not (eligible_pending or eligible_reclaim):
                continue
            claimed = with_status_transition(job, JobStatus.RUNNING, now=now)
            claimed = replace(
                claimed, worker_id=worker_id, lease_expires_at=lease_expires_at
            )
            self._jobs[job_id] = claimed
            return claimed
        return None

    async def extend_lease(
        self, job_id: str, *, worker_id: str, lease_seconds: float = 600.0
    ) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job.status is not JobStatus.RUNNING or job.worker_id != worker_id:
            raise LeaseLostError(
                f"Job {job_id} is no longer held by worker {worker_id!r} "
                f"(status={job.status.value}, worker_id={job.worker_id!r})"
            )
        now = self._now()
        extended = with_status_transition(job, JobStatus.RUNNING, now=now)
        extended = replace(
            extended, lease_expires_at=now + timedelta(seconds=lease_seconds)
        )
        self._jobs[job_id] = extended
        return extended

    async def mark_completed(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job.status is JobStatus.COMPLETED:
            return  # idempotent
        completed = with_status_transition(job, JobStatus.COMPLETED, now=self._now())
        completed = replace(completed, worker_id=None, lease_expires_at=None)
        self._jobs[job_id] = completed

    async def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        policy: RetryPolicy = DEFAULT_POLICY,
        dead_letter: bool = False,
    ) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")

        now = self._now()
        # Single decision point, computed off the CURRENT (pre-write)
        # retry_count — no separate read call, no window for another
        # coroutine to interleave (no `await` between the read above
        # and the writes below).
        will_retry = (not dead_letter) and job.retry_count < policy.max_retries
        target = JobStatus.FAILED if will_retry else JobStatus.DEAD_LETTER

        transitioned = with_status_transition(job, target, error=error, now=now)

        if target is JobStatus.DEAD_LETTER:
            final = replace(transitioned, worker_id=None, lease_expires_at=None)
            self._jobs[job_id] = final
            return final

        # Retry path: FAILED → PENDING is one logical transition (no
        # observer can see the intermediate FAILED row from another
        # coroutine — same atomicity guarantee as the DEAD_LETTER arm
        # above), scheduled via the policy's backoff math.
        requeued = with_status_transition(
            transitioned, JobStatus.PENDING, now=now, increment_retry=True
        )
        requeued = replace(
            requeued,
            scheduled_for=next_retry_at(job.retry_count, policy, now),
            worker_id=None,
            lease_expires_at=None,
        )
        self._jobs[job_id] = requeued
        return requeued

    async def list_dead_letters(
        self,
        *,
        type: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        results: list[Job] = []
        for job in self._jobs.values():
            if job.status is not JobStatus.DEAD_LETTER:
                continue
            if type is not None and job.type != type:
                continue
            results.append(job)
            if len(results) >= limit:
                break
        return results

    async def requeue_dead_letter(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job.status is not JobStatus.DEAD_LETTER:
            raise ValueError(
                f"Job {job_id} is not DEAD_LETTER (status={job.status.value})"
            )
        # DEAD_LETTER → PENDING and reset retry_count for a fresh shot.
        now = self._now()
        moved = with_status_transition(job, JobStatus.PENDING, now=now)
        # `with_status_transition` doesn't reset retry_count by design;
        # we reset it explicitly here because requeue is the operator
        # "give-it-another-N-tries" surface. Lease fields are already
        # None on a DEAD_LETTER job (mark_failed clears them), but
        # reset defensively in case of a future direct-construction path.
        revived = replace(
            moved,
            retry_count=0,
            last_error=None,
            worker_id=None,
            lease_expires_at=None,
        )
        self._jobs[job_id] = revived
        return revived

    async def queue_stats(self, *, job_types: list[str] | None = None) -> QueueStats:
        return _stats_of(self._jobs.values(), job_types=job_types, now=self._now())


#: Upper bound on rows a `queue_stats` read pulls per state.
STATS_ROW_CAP = 5000


def _stats_of(jobs: Any, *, job_types: list[str] | None, now: datetime) -> QueueStats:
    pending = due = running = expired = dead = 0
    workers: set[str] = set()
    last: Job | None = None
    for job in jobs:
        if job_types is not None and job.type not in job_types:
            continue
        if job.status is JobStatus.PENDING:
            pending += 1
            if job.scheduled_for is None or job.scheduled_for <= now:
                due += 1
        elif job.status is JobStatus.RUNNING:
            if job.lease_expires_at is not None and job.lease_expires_at <= now:
                expired += 1
            else:
                running += 1
                if job.worker_id:
                    workers.add(job.worker_id)
        elif job.status is JobStatus.DEAD_LETTER:
            dead += 1
        if job.last_error and (last is None or job.updated_at > last.updated_at):
            last = job
    return QueueStats(
        pending=pending,
        due=due,
        running=running,
        lease_expired=expired,
        dead_letter=dead,
        last_error=last.last_error if last else None,
        last_error_type=last.type if last else None,
        last_error_at=last.updated_at if last else None,
        active_workers=tuple(sorted(workers)),
    )


# ---------------------------------------------------------------------------
# Real implementation (Supabase-client backed)
# ---------------------------------------------------------------------------


def _is_unique_violation(exc: Exception) -> bool:
    """True when `exc` is Postgres error 23505 (unique_violation) — the
    `dedupe_key` uniqueness constraint firing on a concurrent duplicate
    `enqueue`. Duck-typed on `.code` so it recognizes both
    `postgrest.exceptions.APIError` (the real supabase-py client's
    error shape) and a lookalike test double, without an import
    coupling to the `postgrest` package.
    """
    return getattr(exc, "code", None) == "23505"


class RealSupabaseJobRepository:
    """Supabase-client backed `JobRepository`.

    Consumer ships `migrations/jobs.sql.template` (copy into your
    product's `migrations/`, substitute `{{SCHEMA_NAME}}`, renumber —
    the shape it declares matches this class's column + RPC
    expectations 1:1):

        create table jobs (
            id uuid primary key default gen_random_uuid(),
            type text not null,
            payload jsonb not null default '{}',
            status text not null default 'pending',
            retry_count int not null default 0,
            max_retries int not null default 3,
            last_error text,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            scheduled_for timestamptz,
            dedupe_key text,               -- UNIQUE index; NULLs distinct
            worker_id text,
            lease_expires_at timestamptz
        );

    Four RPCs, each a single `UPDATE ... RETURNING *` — no
    consumer-side read-then-write race window:

    - `claim_next_job(p_worker_id, p_job_types, p_lease_seconds)` —
      `FOR UPDATE SKIP LOCKED` pick of the oldest eligible job
      (PENDING-and-due, OR RUNNING-with-an-expired-lease), transitioned
      to RUNNING under a fresh lease.
    - `fail_job(p_job_id, p_error, p_max_retries, p_backoff_seconds,
      p_backoff_multiplier, p_max_backoff_seconds, p_dead_letter)` —
      the retry-vs-dead-letter decision AND the backoff-scheduled
      requeue, computed against the row's own current `retry_count`
      inside the one UPDATE.
    - `complete_job(p_job_id)` — terminal status + lease release.
    - `extend_lease(p_job_id, p_worker_id, p_lease_seconds)` — heartbeat;
      returns zero rows (⇒ `LeaseLostError`) once another worker has
      reclaimed the job.

    The RPC functions are owned by the consumer's migration (the seed
    ships the contract + the reference SQL template, not a live
    migration against any particular product's schema).
    """

    def __init__(
        self,
        client: Any,
        *,
        schema_name: str = "public",
        table_name: str = "jobs",
        rpc_name: str = "claim_next_job",
        fail_rpc_name: str = "fail_job",
        complete_rpc_name: str = "complete_job",
        extend_lease_rpc_name: str = "extend_lease",
    ) -> None:
        self._client = client
        self._schema = schema_name
        self._table = table_name
        self._rpc = rpc_name
        self._fail_rpc = fail_rpc_name
        self._complete_rpc = complete_rpc_name
        self._extend_lease_rpc = extend_lease_rpc_name

    # --- helpers -----------------------------------------------------

    def _table_builder(self):
        # Supabase Python client: `client.schema(...).from_(name)` for
        # non-public schemas, or `client.table(name)` for public.
        if self._schema == "public":
            return self._client.table(self._table)
        return self._client.schema(self._schema).from_(self._table)

    def _row_to_job(self, row: dict[str, Any]) -> Job:
        return Job(
            id=row["id"],
            type=row["type"],
            payload=row.get("payload") or {},
            status=JobStatus(row["status"]),
            retry_count=row.get("retry_count", 0),
            max_retries=row.get("max_retries", 3),
            last_error=row.get("last_error"),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            scheduled_for=_parse_dt(row.get("scheduled_for"))
            if row.get("scheduled_for")
            else None,
            dedupe_key=row.get("dedupe_key"),
            worker_id=row.get("worker_id"),
            lease_expires_at=_parse_dt(row.get("lease_expires_at"))
            if row.get("lease_expires_at")
            else None,
        )

    def _job_to_insert_row(self, job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "type": job.type,
            "payload": job.payload,
            "status": job.status.value,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "last_error": job.last_error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "scheduled_for": job.scheduled_for.isoformat()
            if job.scheduled_for
            else None,
            "dedupe_key": job.dedupe_key,
            "worker_id": job.worker_id,
            "lease_expires_at": job.lease_expires_at.isoformat()
            if job.lease_expires_at
            else None,
        }

    async def _execute(self, builder: Any) -> Any:
        """Tiny helper so test mocks can return either a sync result
        (MockSupabaseClient.execute returns a value directly) or an
        awaitable (real async client). Both paths are covered."""
        result = builder.execute()
        if hasattr(result, "__await__"):
            return await result
        return result

    async def _find_by_dedupe_key(self, dedupe_key: str) -> Job | None:
        builder = (
            self._table_builder().select("*").eq("dedupe_key", dedupe_key).limit(1)
        )
        result = await self._execute(builder)
        rows: list[dict[str, Any]] = getattr(result, "data", None) or []
        return self._row_to_job(rows[0]) if rows else None

    # --- Protocol methods --------------------------------------------

    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        max_retries: int = 3,
        scheduled_for: datetime | None = None,
        dedupe_key: str | None = None,
    ) -> Job:
        now = datetime.now(timezone.utc)
        new_id = str(uuid.uuid4())
        job = Job(
            id=new_id,
            type=type,
            payload=dict(payload),
            status=JobStatus.PENDING,
            retry_count=0,
            max_retries=max_retries,
            last_error=None,
            created_at=now,
            updated_at=now,
            scheduled_for=scheduled_for,
            dedupe_key=dedupe_key,
        )
        builder = self._table_builder().insert(self._job_to_insert_row(job))
        try:
            result = await self._execute(builder)
        except Exception as exc:
            if dedupe_key is not None and _is_unique_violation(exc):
                # Another enqueue() already claimed this dedupe_key —
                # the idempotency contract: return the pre-existing job
                # as the no-op result instead of raising.
                existing = await self._find_by_dedupe_key(dedupe_key)
                if existing is not None:
                    return existing
            raise
        # Real Supabase returns inserted row(s) on `result.data`. We
        # trust our own `Job` instance because it's what we sent.
        _ = result  # Keep linter happy without assuming response shape.
        return job

    async def claim_next(
        self,
        *,
        worker_id: str,
        job_types: list[str] | None = None,
        lease_seconds: float = 600.0,
    ) -> Job | None:
        rpc_builder = self._client.rpc(
            self._rpc,
            {
                "p_worker_id": worker_id,
                "p_job_types": job_types,
                "p_lease_seconds": lease_seconds,
            },
        )
        result = await self._execute(rpc_builder)
        rows: list[dict[str, Any]] = getattr(result, "data", None) or []
        if not rows:
            return None
        return self._row_to_job(rows[0])

    async def extend_lease(
        self, job_id: str, *, worker_id: str, lease_seconds: float = 600.0
    ) -> Job:
        rpc_builder = self._client.rpc(
            self._extend_lease_rpc,
            {
                "p_job_id": job_id,
                "p_worker_id": worker_id,
                "p_lease_seconds": lease_seconds,
            },
        )
        result = await self._execute(rpc_builder)
        rows: list[dict[str, Any]] = getattr(result, "data", None) or []
        if not rows:
            raise LeaseLostError(
                f"Job {job_id} is no longer held by worker {worker_id!r} "
                "(lease expired and reclaimed, or job is not RUNNING)"
            )
        return self._row_to_job(rows[0])

    async def mark_completed(self, job_id: str) -> None:
        rpc_builder = self._client.rpc(self._complete_rpc, {"p_job_id": job_id})
        await self._execute(rpc_builder)

    async def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        policy: RetryPolicy = DEFAULT_POLICY,
        dead_letter: bool = False,
    ) -> Job:
        rpc_builder = self._client.rpc(
            self._fail_rpc,
            {
                "p_job_id": job_id,
                "p_error": error,
                "p_max_retries": policy.max_retries,
                "p_backoff_seconds": policy.backoff_seconds,
                "p_backoff_multiplier": policy.backoff_multiplier,
                "p_max_backoff_seconds": policy.max_backoff_seconds,
                "p_dead_letter": dead_letter,
            },
        )
        result = await self._execute(rpc_builder)
        rows: list[dict[str, Any]] = getattr(result, "data", None) or []
        if not rows:
            raise KeyError(f"Job not found: {job_id}")
        return self._row_to_job(rows[0])

    async def list_dead_letters(
        self,
        *,
        type: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        builder = (
            self._table_builder()
            .select("*")
            .eq("status", JobStatus.DEAD_LETTER.value)
            .limit(limit)
        )
        if type is not None:
            builder = builder.eq("type", type)
        result = await self._execute(builder)
        rows: list[dict[str, Any]] = getattr(result, "data", None) or []
        return [self._row_to_job(r) for r in rows]

    async def requeue_dead_letter(self, job_id: str) -> Job:
        now = datetime.now(timezone.utc)
        update_payload = {
            "status": JobStatus.PENDING.value,
            "retry_count": 0,
            "last_error": None,
            "worker_id": None,
            "lease_expires_at": None,
            "updated_at": now.isoformat(),
        }
        builder = self._table_builder().update(update_payload).eq("id", job_id)
        await self._execute(builder)
        # Re-read for the canonical Job snapshot.
        select_builder = (
            self._table_builder().select("*").eq("id", job_id).limit(1)
        )
        select_result = await self._execute(select_builder)
        rows: list[dict[str, Any]] = getattr(select_result, "data", None) or []
        if not rows:
            raise KeyError(f"Job not found after requeue: {job_id}")
        return self._row_to_job(rows[0])

    async def queue_stats(self, *, job_types: list[str] | None = None) -> QueueStats:
        # Active rows are bounded by the live queue; terminal rows are not,
        # so only DEAD_LETTER (an operator's to-do list) is read, capped.
        def scoped(builder: Any) -> Any:
            return builder.in_("type", job_types) if job_types is not None else builder

        active = await self._execute(
            scoped(
                self._table_builder()
                .select("*")
                .in_("status", [JobStatus.PENDING.value, JobStatus.RUNNING.value])
                .limit(STATS_ROW_CAP)
            )
        )
        dead = await self._execute(
            scoped(
                self._table_builder()
                .select("*")
                .eq("status", JobStatus.DEAD_LETTER.value)
                .limit(STATS_ROW_CAP)
            )
        )
        errored = await self._execute(
            scoped(
                self._table_builder()
                .select("*")
                .not_.is_("last_error", "null")
                .order("updated_at", desc=True)
                .limit(1)
            )
        )
        rows = [
            *(getattr(active, "data", None) or []),
            *(getattr(dead, "data", None) or []),
        ]
        stats = _stats_of(
            (self._row_to_job(r) for r in rows),
            job_types=job_types,
            now=datetime.now(timezone.utc),
        )
        latest = [self._row_to_job(r) for r in (getattr(errored, "data", None) or [])]
        if latest and latest[0].last_error:
            stats = replace(
                stats,
                last_error=latest[0].last_error,
                last_error_type=latest[0].type,
                last_error_at=latest[0].updated_at,
            )
        return stats


def _parse_dt(value: Any) -> datetime:
    """Parse a Supabase `timestamptz` value into a `datetime`.

    Accepts ISO strings (real client) and `datetime` instances (some
    test mocks). Naive strings are interpreted as UTC.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        raise TypeError(f"Cannot parse timestamp from {type(value).__name__}")
    # Postgres ISO format includes timezone; `fromisoformat` handles it
    # in Python 3.11+. We strip a trailing 'Z' for older fallback.
    stripped = value.rstrip("Z")
    parsed = datetime.fromisoformat(stripped)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_job_repository(
    *,
    use_fake: bool = False,
    supabase_client: Any | None = None,
    schema_name: str = "public",
    table_name: str = "jobs",
    rpc_name: str = "claim_next_job",
    fail_rpc_name: str = "fail_job",
    complete_rpc_name: str = "complete_job",
    extend_lease_rpc_name: str = "extend_lease",
) -> JobRepository:
    """Construct a `JobRepository` for a consumer.

    Args:
        use_fake: when True, return a `FakeJobRepository` regardless of
            other arguments. Use in dev / tests / when no Supabase
            client is wired yet.
        supabase_client: live Supabase Python client. Required when
            `use_fake=False`.
        schema_name: Postgres schema hosting the `jobs` table.
        table_name: table name (default `jobs`).
        rpc_name: name of the consumer-shipped `claim_next_job` RPC.
        fail_rpc_name: name of the consumer-shipped `fail_job` RPC.
        complete_rpc_name: name of the consumer-shipped `complete_job` RPC.
        extend_lease_rpc_name: name of the consumer-shipped
            `extend_lease` RPC.

    Returns:
        Concrete `JobRepository` implementation.
    """
    if use_fake:
        return FakeJobRepository()
    if supabase_client is None:
        raise RuntimeError(
            "make_job_repository: supabase_client is required when use_fake=False"
        )
    return RealSupabaseJobRepository(
        supabase_client,
        schema_name=schema_name,
        table_name=table_name,
        rpc_name=rpc_name,
        fail_rpc_name=fail_rpc_name,
        complete_rpc_name=complete_rpc_name,
        extend_lease_rpc_name=extend_lease_rpc_name,
    )


__all__ = [
    "DeadLetterError",
    "FakeJobRepository",
    "JobRepository",
    "LeaseLostError",
    "RealSupabaseJobRepository",
    "make_job_repository",
]


# Silence unused-import warnings for `asdict` (kept for downstream test
# helpers that may want to dump a Job as a dict for asserting payloads).
_ = asdict
