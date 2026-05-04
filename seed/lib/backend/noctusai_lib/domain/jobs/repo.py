"""Job repository — Protocol + Fake + RealSupabase + factory.

Mirrors the canonical Protocol+Fake+Real+factory shape per
`KB § PATTERNS/seed-fake-real-adapter.md`. Consumers wire
`make_job_repository(use_fake=True)` for dev/tests and
`make_job_repository(supabase_client=client, schema_name=...)` in
production.

The Real implementation is **shape-only at this phase**: it exercises
the canonical Supabase Python-client query-builder calls (table /
filter / update / rpc), but the consumer ships the migration that
creates the `jobs` table. Per-product wiring (which schema, which
worker_id allocation, which RPC name) is consumer-side and out of scope
for the seed.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from noctusai_lib.domain.jobs.entity import (
    Job,
    JobStatus,
    next_status,
    with_status_transition,
)


class DeadLetterError(RuntimeError):
    """Raised by handlers that want to skip retries and land directly
    on DEAD_LETTER. Worker catches this and marks the job
    `mark_failed(retry=False)`.
    """


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class JobRepository(Protocol):
    """Async repository surface every Job consumer depends on.

    Implementations:
    - `FakeJobRepository` — in-memory dict-of-jobs for dev + tests.
    - `RealSupabaseJobRepository` — production-shaped Supabase-client
      backed implementation. Consumer ships a `jobs` table migration.

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
    ) -> Job | None:
        """Atomically pick the oldest eligible PENDING job and transition
        it to RUNNING. Returns the claimed Job or None if the queue
        is empty / nothing matches `job_types`.

        Eligible = `status == PENDING` AND
        (`scheduled_for is None` OR `scheduled_for <= now`).
        """

    async def mark_completed(self, job_id: str) -> None:
        """Transition job to COMPLETED. Idempotent on COMPLETED (no-op
        if already terminal). Raises if job is missing.
        """

    async def mark_failed(self, job_id: str, error: str, *, retry: bool) -> None:
        """Transition job to FAILED (when `retry=True` AND retries
        remain) or DEAD_LETTER (otherwise).

        `retry=True` increments `retry_count` and flips status back to
        PENDING so the next `claim_next` picks it up. `retry=False`
        lands on DEAD_LETTER unconditionally — operator escape hatch.
        """

    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        max_retries: int = 3,
        scheduled_for: datetime | None = None,
    ) -> Job:
        """Insert a new PENDING job and return it."""

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
    cooperative async (no `await` in the critical sections).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._next_id: int = 1

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
    ) -> Job:
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
        )
        self._jobs[job.id] = job
        return job

    async def claim_next(
        self,
        *,
        worker_id: str,
        job_types: list[str] | None = None,
    ) -> Job | None:
        now = self._now()
        for job_id, job in self._jobs.items():
            if job.status is not JobStatus.PENDING:
                continue
            if job_types is not None and job.type not in job_types:
                continue
            if job.scheduled_for is not None and job.scheduled_for > now:
                continue
            claimed = with_status_transition(job, JobStatus.RUNNING, now=now)
            self._jobs[job_id] = claimed
            return claimed
        return None

    async def mark_completed(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job.status is JobStatus.COMPLETED:
            return  # idempotent
        completed = with_status_transition(job, JobStatus.COMPLETED, now=self._now())
        self._jobs[job_id] = completed

    async def mark_failed(self, job_id: str, error: str, *, retry: bool) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        outcome = "retry" if retry else "exhausted"
        target = next_status(job, outcome)
        now = self._now()
        # Transition RUNNING → FAILED / DEAD_LETTER (records error).
        transitioned = with_status_transition(
            job, target, error=error, now=now
        )
        self._jobs[job_id] = transitioned
        # When the policy says "retry" AND retries remain (target ==
        # FAILED), flip back to PENDING and bump retry_count. This
        # keeps the FSM as RUNNING → FAILED → PENDING, which mirrors
        # the operator-visible state machine and exposes a FAILED
        # snapshot for diagnostics.
        if target is JobStatus.FAILED:
            requeued = with_status_transition(
                transitioned,
                JobStatus.PENDING,
                now=now,
                increment_retry=True,
            )
            self._jobs[job_id] = requeued

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
        # "give-it-another-N-tries" surface.
        from dataclasses import replace as _replace

        revived = _replace(moved, retry_count=0, last_error=None)
        self._jobs[job_id] = revived
        return revived


# ---------------------------------------------------------------------------
# Real implementation (Supabase-client backed)
# ---------------------------------------------------------------------------


class RealSupabaseJobRepository:
    """Supabase-client backed `JobRepository`.

    **Shape-only at this phase.** Consumer ships a `jobs` table
    migration matching this implementation's column expectations:

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
            scheduled_for timestamptz
        );

    `claim_next` calls a Postgres function `claim_next_job(p_worker_id,
    p_job_types)` that runs `SELECT ... FROM jobs WHERE status='pending'
    AND (scheduled_for IS NULL OR scheduled_for <= now()) AND (p_job_types
    IS NULL OR type = ANY(p_job_types)) ORDER BY created_at FOR UPDATE
    SKIP LOCKED LIMIT 1` then transitions the picked row to RUNNING in a
    single transaction. The function is owned by the consumer's
    migration (the seed ships the contract, not the SQL).
    """

    def __init__(
        self,
        client: Any,
        *,
        schema_name: str = "public",
        table_name: str = "jobs",
        rpc_name: str = "claim_next_job",
    ) -> None:
        self._client = client
        self._schema = schema_name
        self._table = table_name
        self._rpc = rpc_name

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
        }

    async def _execute(self, builder: Any) -> Any:
        """Tiny helper so test mocks can return either a sync result
        (MockSupabaseClient.execute returns a value directly) or an
        awaitable (real async client). Both paths are covered."""
        result = builder.execute()
        if hasattr(result, "__await__"):
            return await result
        return result

    # --- Protocol methods --------------------------------------------

    async def enqueue(
        self,
        *,
        type: str,
        payload: dict,
        max_retries: int = 3,
        scheduled_for: datetime | None = None,
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
        )
        builder = self._table_builder().insert(self._job_to_insert_row(job))
        result = await self._execute(builder)
        # Real Supabase returns inserted row(s) on `result.data`. We
        # trust our own `Job` instance because it's what we sent.
        _ = result  # Keep linter happy without assuming response shape.
        return job

    async def claim_next(
        self,
        *,
        worker_id: str,
        job_types: list[str] | None = None,
    ) -> Job | None:
        # Use the consumer-shipped RPC for atomic FOR UPDATE SKIP LOCKED.
        rpc_builder = self._client.rpc(
            self._rpc,
            {"p_worker_id": worker_id, "p_job_types": job_types},
        )
        result = await self._execute(rpc_builder)
        rows: list[dict[str, Any]] = getattr(result, "data", None) or []
        if not rows:
            return None
        return self._row_to_job(rows[0])

    async def mark_completed(self, job_id: str) -> None:
        now = datetime.now(timezone.utc)
        builder = (
            self._table_builder()
            .update(
                {
                    "status": JobStatus.COMPLETED.value,
                    "updated_at": now.isoformat(),
                }
            )
            .eq("id", job_id)
        )
        await self._execute(builder)

    async def mark_failed(self, job_id: str, error: str, *, retry: bool) -> None:
        # Two-step in the Real impl: read current row to compute retry
        # math (consumer can replace with an RPC for true atomicity at
        # their wiring boundary). The shape-only contract is: hits the
        # right table with the right update.
        select_builder = (
            self._table_builder().select("*").eq("id", job_id).limit(1)
        )
        select_result = await self._execute(select_builder)
        rows: list[dict[str, Any]] = getattr(select_result, "data", None) or []
        if not rows:
            raise KeyError(f"Job not found: {job_id}")
        job = self._row_to_job(rows[0])

        outcome = "retry" if retry else "exhausted"
        target = next_status(job, outcome)
        now = datetime.now(timezone.utc)
        update_payload: dict[str, Any] = {
            "status": target.value,
            "updated_at": now.isoformat(),
            "last_error": error,
        }
        if target is JobStatus.FAILED:
            # Bump retry count + flip back to PENDING in a single update
            # (the FAILED snapshot is observable via `updated_at` if the
            # consumer wants it; the seed contract focuses on the
            # observable terminal-or-eligible state).
            update_payload["status"] = JobStatus.PENDING.value
            update_payload["retry_count"] = job.retry_count + 1

        builder = self._table_builder().update(update_payload).eq("id", job_id)
        await self._execute(builder)

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
        rpc_name: name of the consumer-shipped `claim_next_job` RPC
            function.

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
    )


__all__ = [
    "DeadLetterError",
    "FakeJobRepository",
    "JobRepository",
    "RealSupabaseJobRepository",
    "make_job_repository",
]


# Silence unused-import warnings for `asdict` (kept for downstream test
# helpers that may want to dump a Job as a dict for asserting payloads).
_ = asdict
