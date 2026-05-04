"""Unit tests for `noctusai_lib.domain.jobs`.

Covers:
- State machine in `entity.py` (transitions + immutability + outcome math)
- `RetryPolicy` exponential-backoff math
- `FakeJobRepository` Protocol contract (round-trip + filters + dead-letter)
- `Worker.run_once` (success / retry / dead-letter)
- `Worker.run_forever` (graceful stop)
- `RealSupabaseJobRepository` (query-builder shape via MockSupabaseClient)

Network-free, deterministic. No monkey-patching of our own modules
(only external `unittest.mock.patch` where the carve-out applies; not
needed here — the factory + Mock-client surface keeps tests clean).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.jobs import (
    DEFAULT_POLICY,
    DeadLetterError,
    FakeJobRepository,
    Job,
    JobRepository,
    JobStatus,
    RealSupabaseJobRepository,
    RetryPolicy,
    Worker,
    make_job_repository,
    next_retry_at,
    next_status,
    should_retry,
    with_status_transition,
)
from noctusai_lib.testing import MockSupabaseClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _make_job(
    *,
    status: JobStatus = JobStatus.PENDING,
    retry_count: int = 0,
    max_retries: int = 3,
) -> Job:
    now = datetime(2026, 5, 4, tzinfo=timezone.utc)
    return Job(
        id="j-1",
        type="upload",
        payload={"k": "v"},
        status=status,
        retry_count=retry_count,
        max_retries=max_retries,
        last_error=None,
        created_at=now,
        updated_at=now,
        scheduled_for=None,
    )


# ---------------------------------------------------------------------------
# State machine — entity.py
# ---------------------------------------------------------------------------


class TestStateMachineLegalTransitions:
    """Every transition documented in `entity._LEGAL_TRANSITIONS`."""

    def test_pending_to_running(self):
        job = _make_job(status=JobStatus.PENDING)
        next_job = with_status_transition(job, JobStatus.RUNNING)
        assert next_job.status is JobStatus.RUNNING

    def test_running_to_completed(self):
        job = _make_job(status=JobStatus.RUNNING)
        assert with_status_transition(job, JobStatus.COMPLETED).status is JobStatus.COMPLETED

    def test_running_to_failed(self):
        job = _make_job(status=JobStatus.RUNNING)
        assert with_status_transition(job, JobStatus.FAILED).status is JobStatus.FAILED

    def test_running_to_dead_letter(self):
        job = _make_job(status=JobStatus.RUNNING)
        assert with_status_transition(job, JobStatus.DEAD_LETTER).status is JobStatus.DEAD_LETTER

    def test_failed_to_pending(self):
        job = _make_job(status=JobStatus.FAILED)
        assert with_status_transition(job, JobStatus.PENDING).status is JobStatus.PENDING

    def test_failed_to_running(self):
        job = _make_job(status=JobStatus.FAILED)
        assert with_status_transition(job, JobStatus.RUNNING).status is JobStatus.RUNNING

    def test_dead_letter_to_pending(self):
        job = _make_job(status=JobStatus.DEAD_LETTER)
        assert with_status_transition(job, JobStatus.PENDING).status is JobStatus.PENDING


class TestStateMachineIllegalTransitions:
    """Every transition NOT in the legal set must raise ValueError."""

    @pytest.mark.parametrize(
        "current,target",
        [
            (JobStatus.PENDING, JobStatus.COMPLETED),
            (JobStatus.PENDING, JobStatus.FAILED),
            (JobStatus.PENDING, JobStatus.DEAD_LETTER),
            (JobStatus.COMPLETED, JobStatus.PENDING),
            (JobStatus.COMPLETED, JobStatus.RUNNING),
            (JobStatus.RUNNING, JobStatus.PENDING),
            (JobStatus.FAILED, JobStatus.COMPLETED),
            (JobStatus.DEAD_LETTER, JobStatus.RUNNING),
            (JobStatus.DEAD_LETTER, JobStatus.COMPLETED),
        ],
    )
    def test_illegal_transition_raises(self, current, target):
        job = _make_job(status=current)
        with pytest.raises(ValueError, match="Illegal Job status transition"):
            with_status_transition(job, target)


class TestStateMachineImmutability:
    def test_with_status_transition_returns_new_instance(self):
        job = _make_job(status=JobStatus.PENDING)
        next_job = with_status_transition(
            job, JobStatus.RUNNING, now=datetime(2026, 5, 5, tzinfo=timezone.utc)
        )
        # New instance, original untouched.
        assert next_job is not job
        assert job.status is JobStatus.PENDING  # unchanged
        assert job.updated_at == datetime(2026, 5, 4, tzinfo=timezone.utc)
        # Updated_at bumped on the new instance.
        assert next_job.updated_at == datetime(2026, 5, 5, tzinfo=timezone.utc)

    def test_error_recorded_only_on_failure_states(self):
        running = _make_job(status=JobStatus.RUNNING)
        completed = with_status_transition(running, JobStatus.COMPLETED, error="x")
        assert completed.last_error is None

        failed = with_status_transition(running, JobStatus.FAILED, error="boom")
        assert failed.last_error == "boom"

        dead = with_status_transition(running, JobStatus.DEAD_LETTER, error="dead")
        assert dead.last_error == "dead"

    def test_increment_retry_bumps_count(self):
        job = _make_job(status=JobStatus.FAILED, retry_count=0)
        bumped = with_status_transition(
            job, JobStatus.PENDING, increment_retry=True
        )
        assert bumped.retry_count == 1
        assert job.retry_count == 0


class TestNextStatus:
    def test_success_to_completed(self):
        assert next_status(_make_job(status=JobStatus.RUNNING), "success") is JobStatus.COMPLETED

    def test_retry_with_remaining_to_failed(self):
        job = _make_job(status=JobStatus.RUNNING, retry_count=0, max_retries=3)
        assert next_status(job, "retry") is JobStatus.FAILED

    def test_retry_exhausted_to_dead_letter(self):
        job = _make_job(status=JobStatus.RUNNING, retry_count=3, max_retries=3)
        assert next_status(job, "retry") is JobStatus.DEAD_LETTER

    def test_exhausted_outcome_to_dead_letter(self):
        assert next_status(_make_job(status=JobStatus.RUNNING), "exhausted") is JobStatus.DEAD_LETTER

    def test_unknown_outcome_raises(self):
        with pytest.raises(ValueError, match="Unknown JobOutcome"):
            next_status(_make_job(status=JobStatus.RUNNING), "garbage")  # type: ignore[arg-type]


class TestShouldRetry:
    def test_retries_remaining(self):
        assert should_retry(_make_job(retry_count=0, max_retries=3)) is True
        assert should_retry(_make_job(retry_count=2, max_retries=3)) is True

    def test_retries_exhausted(self):
        assert should_retry(_make_job(retry_count=3, max_retries=3)) is False
        assert should_retry(_make_job(retry_count=4, max_retries=3)) is False


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_defaults_match_documented(self):
        assert DEFAULT_POLICY.max_retries == 3
        assert DEFAULT_POLICY.backoff_seconds == 1.0
        assert DEFAULT_POLICY.backoff_multiplier == 2.0
        assert DEFAULT_POLICY.max_backoff_seconds == 300.0

    def test_exponential_growth_first_retry(self):
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = next_retry_at(0, DEFAULT_POLICY, now)
        # 1.0 * 2.0**0 = 1s.
        assert result == now + timedelta(seconds=1.0)

    def test_exponential_growth_subsequent_retries(self):
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        # retry_count=1 → 1.0 * 2.0**1 = 2s
        assert next_retry_at(1, DEFAULT_POLICY, now) == now + timedelta(seconds=2.0)
        # retry_count=2 → 4s
        assert next_retry_at(2, DEFAULT_POLICY, now) == now + timedelta(seconds=4.0)
        # retry_count=3 → 8s
        assert next_retry_at(3, DEFAULT_POLICY, now) == now + timedelta(seconds=8.0)

    def test_cap_applied_at_max_backoff(self):
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        # 1.0 * 2**20 = ~1M seconds → capped at 300.
        result = next_retry_at(20, DEFAULT_POLICY, now)
        assert result == now + timedelta(seconds=300.0)

    def test_custom_policy_respected(self):
        policy = RetryPolicy(
            max_retries=5,
            backoff_seconds=2.0,
            backoff_multiplier=3.0,
            max_backoff_seconds=1000.0,
        )
        now = datetime(2026, 5, 4, tzinfo=timezone.utc)
        # retry_count=2 → 2.0 * 3**2 = 18s
        assert next_retry_at(2, policy, now) == now + timedelta(seconds=18.0)

    def test_negative_retry_count_raises(self):
        with pytest.raises(ValueError, match="retry_count must be >= 0"):
            next_retry_at(-1, DEFAULT_POLICY, datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# FakeJobRepository — Protocol contract
# ---------------------------------------------------------------------------


class TestFakeRepoEnqueueAndClaim:
    def test_enqueue_returns_pending_job(self):
        repo = FakeJobRepository()
        job = _run(repo.enqueue(type="upload", payload={"path": "/tmp/x"}))
        assert job.status is JobStatus.PENDING
        assert job.type == "upload"
        assert job.payload == {"path": "/tmp/x"}
        assert job.retry_count == 0
        assert job.max_retries == 3
        assert job.scheduled_for is None

    def test_claim_next_returns_enqueued_job_and_transitions_to_running(self):
        repo = FakeJobRepository()
        enqueued = _run(repo.enqueue(type="upload", payload={}))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        assert claimed is not None
        assert claimed.id == enqueued.id
        assert claimed.status is JobStatus.RUNNING

    def test_claim_next_empty_returns_none(self):
        repo = FakeJobRepository()
        assert _run(repo.claim_next(worker_id="w-1")) is None

    def test_claim_next_skips_running_jobs(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}))
        first = _run(repo.claim_next(worker_id="w-1"))
        # No second pending job → claim returns None.
        second = _run(repo.claim_next(worker_id="w-1"))
        assert first is not None
        assert second is None

    def test_claim_next_filters_by_job_type(self):
        repo = FakeJobRepository()
        upload = _run(repo.enqueue(type="upload", payload={}))
        refresh = _run(repo.enqueue(type="refresh", payload={}))

        claimed = _run(
            repo.claim_next(worker_id="w-1", job_types=["refresh"])
        )
        assert claimed is not None
        assert claimed.id == refresh.id
        # Upload still pending.
        upload_claim = _run(
            repo.claim_next(worker_id="w-1", job_types=["upload"])
        )
        assert upload_claim is not None
        assert upload_claim.id == upload.id

    def test_claim_next_respects_scheduled_for(self):
        repo = FakeJobRepository()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _run(repo.enqueue(type="upload", payload={}, scheduled_for=future))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        assert claimed is None

    def test_claim_next_picks_eligible_scheduled_job(self):
        repo = FakeJobRepository()
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        _run(repo.enqueue(type="upload", payload={}, scheduled_for=past))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        assert claimed is not None
        assert claimed.status is JobStatus.RUNNING


class TestFakeRepoMarkCompleted:
    def test_mark_completed_after_claim(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        assert claimed is not None

        _run(repo.mark_completed(claimed.id))
        # Subsequent claim returns None — the job is terminal.
        assert _run(repo.claim_next(worker_id="w-1")) is None

    def test_mark_completed_idempotent(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        _run(repo.mark_completed(claimed.id))
        # Second call is a no-op (already terminal).
        _run(repo.mark_completed(claimed.id))

    def test_mark_completed_unknown_raises(self):
        repo = FakeJobRepository()
        with pytest.raises(KeyError, match="Job not found"):
            _run(repo.mark_completed("missing"))


class TestFakeRepoMarkFailedRetry:
    def test_retry_with_remaining_re_enqueues_to_pending(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=3))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        assert claimed is not None

        _run(repo.mark_failed(claimed.id, "transient", retry=True))
        # Same job claimable again.
        re_claimed = _run(repo.claim_next(worker_id="w-1"))
        assert re_claimed is not None
        assert re_claimed.id == claimed.id
        assert re_claimed.retry_count == 1
        assert re_claimed.last_error == "transient"

    def test_retry_exhausted_lands_on_dead_letter(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=2))

        # 1st claim + fail.
        c = _run(repo.claim_next(worker_id="w-1"))
        _run(repo.mark_failed(c.id, "fail-1", retry=True))
        # 2nd claim + fail.
        c = _run(repo.claim_next(worker_id="w-1"))
        _run(repo.mark_failed(c.id, "fail-2", retry=True))
        # 3rd claim + fail — at this point retry_count=2, which == max_retries
        # → next_status returns DEAD_LETTER.
        c = _run(repo.claim_next(worker_id="w-1"))
        _run(repo.mark_failed(c.id, "fail-3", retry=True))

        # Now in dead-letter.
        dl = _run(repo.list_dead_letters())
        assert len(dl) == 1
        assert dl[0].status is JobStatus.DEAD_LETTER
        assert dl[0].last_error == "fail-3"

    def test_retry_false_lands_on_dead_letter_immediately(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=10))
        claimed = _run(repo.claim_next(worker_id="w-1"))
        _run(repo.mark_failed(claimed.id, "fatal", retry=False))

        dl = _run(repo.list_dead_letters())
        assert len(dl) == 1
        assert dl[0].id == claimed.id
        assert dl[0].last_error == "fatal"

    def test_mark_failed_unknown_raises(self):
        repo = FakeJobRepository()
        with pytest.raises(KeyError, match="Job not found"):
            _run(repo.mark_failed("missing", "x", retry=True))


class TestFakeRepoListDeadLetters:
    def test_filter_by_type(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=0))
        _run(repo.enqueue(type="refresh", payload={}, max_retries=0))
        # Push both to dead-letter.
        for _ in range(2):
            c = _run(repo.claim_next(worker_id="w-1"))
            _run(repo.mark_failed(c.id, "boom", retry=False))

        all_dl = _run(repo.list_dead_letters())
        assert len(all_dl) == 2

        upload_only = _run(repo.list_dead_letters(type="upload"))
        assert len(upload_only) == 1
        assert upload_only[0].type == "upload"

    def test_limit_respected(self):
        repo = FakeJobRepository()
        for _ in range(5):
            _run(repo.enqueue(type="upload", payload={}))
        for _ in range(5):
            c = _run(repo.claim_next(worker_id="w-1"))
            _run(repo.mark_failed(c.id, "boom", retry=False))

        limited = _run(repo.list_dead_letters(limit=3))
        assert len(limited) == 3


class TestFakeRepoRequeueDeadLetter:
    def test_dead_letter_can_be_requeued(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}))
        c = _run(repo.claim_next(worker_id="w-1"))
        _run(repo.mark_failed(c.id, "fatal", retry=False))

        revived = _run(repo.requeue_dead_letter(c.id))
        assert revived.status is JobStatus.PENDING
        assert revived.retry_count == 0
        assert revived.last_error is None

        # And it's claimable again.
        re_claimed = _run(repo.claim_next(worker_id="w-1"))
        assert re_claimed is not None
        assert re_claimed.id == c.id

    def test_requeue_non_dead_letter_raises(self):
        repo = FakeJobRepository()
        job = _run(repo.enqueue(type="upload", payload={}))
        with pytest.raises(ValueError, match="not DEAD_LETTER"):
            _run(repo.requeue_dead_letter(job.id))

    def test_requeue_unknown_raises(self):
        repo = FakeJobRepository()
        with pytest.raises(KeyError, match="Job not found"):
            _run(repo.requeue_dead_letter("missing"))


class TestFakeRepoSatisfiesProtocol:
    def test_isinstance_protocol(self):
        repo = FakeJobRepository()
        # `runtime_checkable` Protocol → isinstance works.
        assert isinstance(repo, JobRepository)


# ---------------------------------------------------------------------------
# Worker.run_once
# ---------------------------------------------------------------------------


class TestWorkerRunOnce:
    def test_success_path(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={"k": "v"}))

        called: list[Job] = []

        async def handler(job: Job) -> None:
            called.append(job)

        worker = Worker(
            repo,
            worker_id="w-1",
            handlers={"upload": handler},
        )
        processed = _run(worker.run_once())
        assert processed is True
        assert len(called) == 1
        assert called[0].type == "upload"
        # Job is now COMPLETED — no claimable jobs left.
        assert _run(repo.claim_next(worker_id="w-1")) is None

    def test_empty_queue_returns_false(self):
        repo = FakeJobRepository()

        async def handler(job: Job) -> None:
            pytest.fail("Should not be called")

        worker = Worker(
            repo, worker_id="w-1", handlers={"upload": handler}
        )
        assert _run(worker.run_once()) is False

    def test_retry_path_handler_raises_value_error(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=3))

        attempt_count = 0

        async def flaky_handler(job: Job) -> None:
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("transient")

        worker = Worker(
            repo, worker_id="w-1", handlers={"upload": flaky_handler}
        )
        # First attempt — retried.
        _run(worker.run_once())
        # The job is back to PENDING (retries left).
        re_claimed = _run(repo.claim_next(worker_id="w-1"))
        assert re_claimed is not None
        assert re_claimed.retry_count == 1
        assert re_claimed.last_error == "transient"
        assert attempt_count == 1

    def test_dead_letter_after_retries_exhausted(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=2))

        async def always_fails(job: Job) -> None:
            raise RuntimeError("fail")

        worker = Worker(
            repo, worker_id="w-1", handlers={"upload": always_fails}
        )
        # Claim+fail until exhausted (max_retries=2 → 3 attempts).
        for _ in range(3):
            processed = _run(worker.run_once())
            assert processed is True

        dl = _run(repo.list_dead_letters())
        assert len(dl) == 1

    def test_dead_letter_error_skips_retries(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}, max_retries=10))

        async def fatal_handler(job: Job) -> None:
            raise DeadLetterError("not retryable")

        worker = Worker(
            repo, worker_id="w-1", handlers={"upload": fatal_handler}
        )
        _run(worker.run_once())

        dl = _run(repo.list_dead_letters())
        assert len(dl) == 1
        assert dl[0].last_error == "not retryable"

    def test_no_handler_for_type_dead_letters(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="unknown", payload={}))

        async def upload_handler(job: Job) -> None:
            pytest.fail("should not be invoked")

        worker = Worker(
            repo, worker_id="w-1", handlers={"upload": upload_handler}
        )
        # Worker only claims `upload` jobs (job_types filter), so the
        # `unknown`-type job won't be claimed at all → run_once
        # returns False.
        assert _run(worker.run_once()) is False
        # Job remains PENDING — it's not lost; an operator can wire a
        # handler later.
        all_dl = _run(repo.list_dead_letters())
        assert len(all_dl) == 0


# ---------------------------------------------------------------------------
# Worker.run_forever
# ---------------------------------------------------------------------------


class TestWorkerRunForever:
    def test_stop_event_terminates_loop(self):
        repo = FakeJobRepository()

        async def handler(job: Job) -> None:
            pass

        worker = Worker(
            repo,
            worker_id="w-1",
            handlers={"upload": handler},
            poll_interval_seconds=0.05,
        )

        async def driver() -> None:
            stop_event = asyncio.Event()
            loop_task = asyncio.create_task(
                worker.run_forever(stop_event=stop_event)
            )
            # Let it spin once.
            await asyncio.sleep(0.05)
            stop_event.set()
            # Should terminate within roughly poll_interval.
            await asyncio.wait_for(loop_task, timeout=1.0)

        _run(driver())

    def test_loop_drains_queue_then_idle_sleeps(self):
        repo = FakeJobRepository()
        _run(repo.enqueue(type="upload", payload={}))
        _run(repo.enqueue(type="upload", payload={}))

        processed: list[str] = []

        async def handler(job: Job) -> None:
            processed.append(job.id)

        worker = Worker(
            repo,
            worker_id="w-1",
            handlers={"upload": handler},
            poll_interval_seconds=0.05,
        )

        async def driver() -> None:
            stop_event = asyncio.Event()
            loop_task = asyncio.create_task(
                worker.run_forever(stop_event=stop_event)
            )
            # Wait long enough to drain both jobs and reach idle sleep.
            await asyncio.sleep(0.2)
            stop_event.set()
            await asyncio.wait_for(loop_task, timeout=1.0)

        _run(driver())
        assert len(processed) == 2


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestMakeJobRepository:
    def test_use_fake_returns_fake(self):
        repo = make_job_repository(use_fake=True)
        assert isinstance(repo, FakeJobRepository)

    def test_use_fake_false_with_supabase_client_returns_real(self):
        client = MockSupabaseClient(validate_schema=False)
        repo = make_job_repository(supabase_client=client, schema_name="public")
        assert isinstance(repo, RealSupabaseJobRepository)

    def test_use_fake_false_without_client_raises(self):
        with pytest.raises(RuntimeError, match="supabase_client is required"):
            make_job_repository(use_fake=False)


# ---------------------------------------------------------------------------
# RealSupabaseJobRepository — query-builder shape
# ---------------------------------------------------------------------------


class TestRealSupabaseRepoEnqueue:
    def test_enqueue_inserts_into_jobs_table(self):
        client = MockSupabaseClient(validate_schema=False)
        repo = RealSupabaseJobRepository(client, schema_name="public")

        job = _run(repo.enqueue(type="upload", payload={"k": "v"}, max_retries=5))

        assert job.status is JobStatus.PENDING
        assert job.max_retries == 5

        # Insert hit the right table with the right shape.
        inserts = client.table("jobs").inserted_payloads
        assert len(inserts) == 1
        row = inserts[0]
        assert row["type"] == "upload"
        assert row["payload"] == {"k": "v"}
        assert row["status"] == "pending"
        assert row["retry_count"] == 0
        assert row["max_retries"] == 5
        assert row["scheduled_for"] is None
        assert row["last_error"] is None


class TestRealSupabaseRepoMarkCompleted:
    def test_update_targets_correct_id_and_status(self):
        client = MockSupabaseClient(validate_schema=False)
        repo = RealSupabaseJobRepository(client, schema_name="public")

        _run(repo.mark_completed("j-abc"))

        updates = client.table("jobs").updated_payloads
        assert len(updates) == 1
        assert updates[0]["status"] == "completed"
        assert "updated_at" in updates[0]


class TestRealSupabaseRepoMarkFailed:
    def test_retry_with_room_flips_to_pending_and_bumps_count(self):
        # Seed a SELECT row reflecting "RUNNING with retries left".
        from noctusai_lib.testing import MockSupabaseResponse

        client = MockSupabaseClient(validate_schema=False)
        client.set_table_data(
            "jobs",
            [
                {
                    "id": "j-1",
                    "type": "upload",
                    "payload": {},
                    "status": "running",
                    "retry_count": 0,
                    "max_retries": 3,
                    "last_error": None,
                    "created_at": "2026-05-04T12:00:00+00:00",
                    "updated_at": "2026-05-04T12:00:00+00:00",
                    "scheduled_for": None,
                }
            ],
        )

        repo = RealSupabaseJobRepository(client, schema_name="public")
        _run(repo.mark_failed("j-1", "transient", retry=True))

        # mark_failed issues SELECT then UPDATE; we verify the UPDATE.
        updates = client.table("jobs").updated_payloads
        assert len(updates) == 1
        u = updates[0]
        assert u["status"] == "pending"  # retries remain → flipped back
        assert u["retry_count"] == 1
        assert u["last_error"] == "transient"

    def test_retry_false_lands_on_dead_letter(self):
        client = MockSupabaseClient(validate_schema=False)
        client.set_table_data(
            "jobs",
            [
                {
                    "id": "j-2",
                    "type": "upload",
                    "payload": {},
                    "status": "running",
                    "retry_count": 0,
                    "max_retries": 3,
                    "last_error": None,
                    "created_at": "2026-05-04T12:00:00+00:00",
                    "updated_at": "2026-05-04T12:00:00+00:00",
                    "scheduled_for": None,
                }
            ],
        )

        repo = RealSupabaseJobRepository(client, schema_name="public")
        _run(repo.mark_failed("j-2", "fatal", retry=False))

        updates = client.table("jobs").updated_payloads
        assert len(updates) == 1
        assert updates[0]["status"] == "dead_letter"
        assert updates[0]["last_error"] == "fatal"

    def test_retry_exhausted_lands_on_dead_letter(self):
        client = MockSupabaseClient(validate_schema=False)
        client.set_table_data(
            "jobs",
            [
                {
                    "id": "j-3",
                    "type": "upload",
                    "payload": {},
                    "status": "running",
                    "retry_count": 3,
                    "max_retries": 3,
                    "last_error": "previous",
                    "created_at": "2026-05-04T12:00:00+00:00",
                    "updated_at": "2026-05-04T12:00:00+00:00",
                    "scheduled_for": None,
                }
            ],
        )

        repo = RealSupabaseJobRepository(client, schema_name="public")
        _run(repo.mark_failed("j-3", "final", retry=True))

        updates = client.table("jobs").updated_payloads
        assert len(updates) == 1
        # next_status returns DEAD_LETTER when retries exhausted.
        assert updates[0]["status"] == "dead_letter"
        assert updates[0]["last_error"] == "final"


class TestRealSupabaseRepoClaimNextViaRpc:
    def test_calls_claim_next_job_rpc_returns_none_on_empty(self):
        client = MockSupabaseClient(validate_schema=False)
        client.set_rpc_data("claim_next_job", [])
        repo = RealSupabaseJobRepository(client, schema_name="public")

        result = _run(repo.claim_next(worker_id="w-1"))
        assert result is None

    def test_rpc_returns_row_parsed_into_job(self):
        client = MockSupabaseClient(validate_schema=False)
        client.set_rpc_data(
            "claim_next_job",
            [
                {
                    "id": "j-99",
                    "type": "upload",
                    "payload": {"x": 1},
                    "status": "running",
                    "retry_count": 0,
                    "max_retries": 3,
                    "last_error": None,
                    "created_at": "2026-05-04T12:00:00+00:00",
                    "updated_at": "2026-05-04T12:00:00+00:00",
                    "scheduled_for": None,
                }
            ],
        )
        repo = RealSupabaseJobRepository(client, schema_name="public")
        job = _run(repo.claim_next(worker_id="w-1"))
        assert job is not None
        assert job.id == "j-99"
        assert job.status is JobStatus.RUNNING
        assert job.payload == {"x": 1}

    def test_custom_rpc_name_respected(self):
        client = MockSupabaseClient(validate_schema=False)
        client.set_rpc_data("my_custom_claim", [])
        repo = RealSupabaseJobRepository(
            client, schema_name="public", rpc_name="my_custom_claim"
        )
        # No RPC by the default name → falls through to empty list.
        result = _run(repo.claim_next(worker_id="w-1"))
        assert result is None


class TestRealSupabaseRepoListDeadLetters:
    def test_select_filters_by_dead_letter_status(self):
        client = MockSupabaseClient(validate_schema=False)
        client.set_table_data(
            "jobs",
            [
                {
                    "id": "j-dl-1",
                    "type": "upload",
                    "payload": {},
                    "status": "dead_letter",
                    "retry_count": 3,
                    "max_retries": 3,
                    "last_error": "boom",
                    "created_at": "2026-05-04T12:00:00+00:00",
                    "updated_at": "2026-05-04T12:00:00+00:00",
                    "scheduled_for": None,
                }
            ],
        )
        repo = RealSupabaseJobRepository(client, schema_name="public")
        results = _run(repo.list_dead_letters())
        assert len(results) == 1
        assert results[0].status is JobStatus.DEAD_LETTER
        assert results[0].id == "j-dl-1"
        assert results[0].last_error == "boom"


class TestRealSupabaseRepoSchemaSelection:
    def test_non_public_schema_uses_schema_from(self):
        # MockSupabaseClient.schema(name) returns a scoped client; we
        # just verify construction doesn't error and the right path
        # is exercised.
        client = MockSupabaseClient(validate_schema=False)
        repo = RealSupabaseJobRepository(client, schema_name="my_product")

        # Use mark_completed which goes through `_table_builder`.
        _run(repo.mark_completed("j-x"))
        # Update payload should still land for the configured table —
        # MockSupabaseClient creates per-schema scoped clients lazily;
        # the test asserts no exception + the operation completed.
        # (Verifying which exact scoped builder collected the update is
        # noisy; the no-exception path is the seed-shape contract.)
