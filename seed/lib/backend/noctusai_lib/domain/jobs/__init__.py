"""Jobs primitive — Job entity + status state machine + repo + worker.

Lifted 2026-05-04 by `projects/seed-hardening-from-youtube-crawler/`
Phase 2.1 + 2.2 from the chatbot-coupled `domain/chatbot/worker.py`
shape into a domain-agnostic surface. N=3+ trigger documented in §3a:
YouTube uploads, scheduling tasks, AI batches, and any future
long-running products consume one shape.

**What ships:**
- `Job` frozen dataclass + `JobStatus` enum + pure-function state
  machine (`next_status`, `should_retry`, `with_status_transition`).
- `RetryPolicy` + `next_retry_at` exponential-backoff helper.
- `JobRepository` Protocol + `FakeJobRepository` (in-memory, dev/tests)
  + `RealSupabaseJobRepository` (shape-only — consumer ships the
  migration that creates the `jobs` table + the `claim_next_job` RPC
  for atomic FOR UPDATE SKIP LOCKED claim).
- `make_job_repository(*, use_fake=False, supabase_client=None, ...)`
  factory mirroring the canonical Protocol+Fake+Real+factory pattern
  per `KB § PATTERNS/seed-fake-real-adapter.md`.
- `Worker` async polling worker — claims one job, dispatches to the
  matching handler, translates outcome to repo calls. `run_once` for
  test harnesses; `run_forever(stop_event=...)` for production.
- `DeadLetterError` — handler-side escape hatch for non-retryable
  failures.

**Wiring recipe:**

    from noctusai_lib.domain.jobs import (
        Worker, make_job_repository, RetryPolicy
    )

    repo = make_job_repository(
        use_fake=False,
        supabase_client=supabase,
        schema_name="my_product",
    )
    worker = Worker(
        repo,
        worker_id="upload-worker-1",
        handlers={
            "youtube.upload": handle_upload,
            "youtube.metadata_refresh": handle_metadata,
        },
        retry_policy=RetryPolicy(max_retries=5, backoff_seconds=2.0),
    )
    await worker.run_forever(stop_event=stop_event)

The chatbot worker (`domain/chatbot/worker.py`) is untouched — chatbot
consumers continue against `ConversationWorker`. New consumers (and
chatbot at its next refactor) target `Worker` + `JobRepository`.
"""

from noctusai_lib.domain.jobs.entity import (
    Job,
    JobOutcome,
    JobStatus,
    next_status,
    should_retry,
    with_status_transition,
)
from noctusai_lib.domain.jobs.repo import (
    DeadLetterError,
    FakeJobRepository,
    JobRepository,
    RealSupabaseJobRepository,
    make_job_repository,
)
from noctusai_lib.domain.jobs.retry_policy import (
    DEFAULT_POLICY,
    RetryPolicy,
    next_retry_at,
)
from noctusai_lib.domain.jobs.worker import (
    JobHandler,
    Worker,
)

__all__ = [
    "DEFAULT_POLICY",
    "DeadLetterError",
    "FakeJobRepository",
    "Job",
    "JobHandler",
    "JobOutcome",
    "JobRepository",
    "JobStatus",
    "RealSupabaseJobRepository",
    "RetryPolicy",
    "Worker",
    "make_job_repository",
    "next_retry_at",
    "next_status",
    "should_retry",
    "with_status_transition",
]
