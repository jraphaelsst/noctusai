"""Background scheduler primitive — APScheduler wrapper for products.

**Layer contract.** This module sits in `api/` because it's wired into the
FastAPI lifespan (`create_product_app(..., lifespan_startup=..., lifespan_shutdown=...)`).
It does NOT depend on `domain/` (per the layer rule); product job functions
import the primitive and register, not the other way around.

**Why a primitive.** Three products (mailing, personal-finance, therapy)
each authored their own `app/scheduler.py` with the same APScheduler-based
shape — module-level `AsyncIOScheduler(timezone="America/Sao_Paulo")`,
silenced verbose logging, `start_scheduler()` / `stop_scheduler()` wired
into lifespan, per-job `add_job(...)`. At N=3 the recurrence rule (per
`KB § PATTERNS/project-execution.md § 2.7`) demands formalization. This
module is that formalization.

**Adopters call this primitive instead of authoring a per-product file:**

    # products/X/backend/app/scheduler.py
    from noctusai_lib.api.scheduler import (
        register,
        start_scheduler,
        stop_scheduler,
    )
    from app.dependencies import get_admin_client
    from app.services.<your_service> import run_<your_job>

    async def my_job():
        run_<your_job>(get_admin_client())

    def configure() -> None:
        register("my_job", my_job, hours=24)

    # In main.py:
    from app.scheduler import configure
    configure()  # registers jobs at import time
    app = create_product_app(
        ...,
        lifespan_startup=start_scheduler,
        lifespan_shutdown=stop_scheduler,
    )

**Trigger surface.** `register(name, fn, hours=...|minutes=...|seconds=...|cron=...)`.
Exactly one trigger flavor per call. `cron` is a cron expression string
(`"0 6 * * *"`) — supports the personal-finance "daily at 06:00 SP" pattern.

**Replace-existing semantics.** All `add_job(..., replace_existing=True)`
so re-import / hot-reload is idempotent.

**Misfire policy.** Every job is registered with `misfire_grace_time=30,
coalesce=True, max_instances=1`. Transient blips (laptop sleep, DNS
hiccup, blocked event loop) up to 30s no longer flood logs with
"Run time of job ... was missed" warnings; stacked-up missed runs
collapse into a single replay; one job instance never overlaps itself.
Jobs that legitimately need different semantics (e.g. concurrent send
batches, no coalescing) should not use this primitive — author a
dedicated APScheduler instance instead.

**CI safety.** The FastAPI `TestClient` skips lifespan unless invoked as a
context manager, which existing product test suites don't do. So
`start_scheduler()` doesn't fire during pytest. The
`<PRODUCT>_SCHEDULER_ENABLED` env flag is a second layer of safety —
products can override per-environment.

**Timezone.** Every cron trigger and the scheduler itself run on the
PLATFORM clock — `noctusai_lib.primitives.timeutil.platform_timezone_name()`
(env `NOCTUS_TIMEZONE`, default `America/Sao_Paulo`). One setting, never a
literal per call site.

**Run ledger (2026-10-29).** Every registered job is wrapped: each run is
timed and reported to the process's `RunObserver` (wired by the seed
framework to core's `public.scheduler_runs`; see
`noctusai_lib.domain.scheduler_runs`). Status is `ok` | `error` | `skipped`:
an exception is `error` (and still propagates to APScheduler as before), a
`SkipRun` raised by the job is `skipped`, and — because most jobs here log
and swallow their own failures so the scheduler keeps running — an ERROR
log record emitted INSIDE the run (including from a worker thread the job
started via `asyncio.to_thread`) also marks it `error`. The ledger write is
best-effort: it never breaks the job, but a failed write is logged at ERROR.

**Logging.** APScheduler's verbose DEBUG output (job execution / next
wakeup chatter) is silenced to WARNING at module import. Job functions
should log meaningful events at INFO; per-tick noise stays out of prod
logs.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Protocol

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from noctusai_lib.primitives.timeutil import platform_timezone_name

# Silence APScheduler verbose DEBUG logging once at import time. Adopters
# don't have to repeat this in their wrappers.
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Module-level scheduler. Singleton-per-process matches APScheduler's
# AsyncIOScheduler design — there's only one event loop in a uvicorn
# worker.
scheduler = AsyncIOScheduler(timezone=platform_timezone_name())

#: name → how it was registered (the raw cron / interval). The run ledger's
#: job registry and the "missing run" detector need the schedule as written,
#: not APScheduler's internal trigger object.
_job_specs: dict[str, "JobSpec"] = {}


# ---------------------------------------------------------------------------
# Run ledger seam
# ---------------------------------------------------------------------------


class SkipRun(Exception):
    """Raise from a job to record the run as `skipped` (with the message as
    the reason) instead of `ok` — e.g. a feature switch is off."""


@dataclass(frozen=True)
class JobSpec:
    """A registered job's schedule as written by its product."""

    job: str
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    timezone: str = ""
    misfire_grace_time: int = 30


@dataclass(frozen=True)
class JobRun:
    """One finished run of a registered job."""

    job: str
    started_at: datetime
    finished_at: datetime
    status: str  # "ok" | "error" | "skipped"
    duration_ms: int
    error: Optional[str] = None


class RunObserver(Protocol):
    """Where finished runs go. Called from a worker thread, never the loop."""

    def record(self, run: JobRun) -> None: ...

    def register_jobs(self, specs: list[JobSpec]) -> None: ...


_run_observer: Optional[RunObserver] = None


def set_run_observer(observer: Optional[RunObserver]) -> None:
    """Install (or clear, with None) the process's run observer. The seed
    framework calls this once per app with core's ledger."""
    global _run_observer
    _run_observer = observer


def get_run_observer() -> Optional[RunObserver]:
    return _run_observer


def job_specs() -> list[JobSpec]:
    """Every registered job's schedule, sorted by name."""
    return [_job_specs[k] for k in sorted(_job_specs)]


@dataclass
class _RunCapture:
    errors: list[str] = field(default_factory=list)


_current_run: contextvars.ContextVar[Optional[_RunCapture]] = contextvars.ContextVar(
    "noctus_scheduler_current_run", default=None,
)


class _RunErrorCapture(logging.Handler):
    """Root-logger handler: an ERROR record emitted while a job run is the
    current context is attributed to that run. Inert outside a run (the
    context var is None), so it costs one lookup per ERROR record."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        capture = _current_run.get()
        if capture is None:
            return
        try:
            capture.errors.append(record.getMessage())
        except Exception:  # noqa: BLE001 — a malformed record must not break logging itself
            capture.errors.append(str(record.msg))


_capture_handler = _RunErrorCapture()
_capture_lock = threading.Lock()


def _ensure_capture_handler() -> None:
    root = logging.getLogger()
    with _capture_lock:
        if _capture_handler not in root.handlers:
            root.addHandler(_capture_handler)


async def _report(run: JobRun) -> None:
    observer = _run_observer
    if observer is None:
        logger.debug("scheduler run %s=%s not recorded: no run observer installed", run.job, run.status)
        return
    try:
        await asyncio.to_thread(observer.record, run)
    except Exception:  # noqa: BLE001 — the ledger must never break the job; loud, not silent
        logger.error(
            "scheduler run ledger write FAILED for job %r (status=%s): the run happened "
            "but public.scheduler_runs has no row for it",
            run.job, run.status, exc_info=True,
        )


def _instrument(name: str, fn: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
    """Wrap `fn` so every run is timed, classified and reported."""

    @functools.wraps(fn)
    async def _run(*args: Any, **kwargs: Any) -> Any:
        _ensure_capture_handler()
        capture = _RunCapture()
        token = _current_run.set(capture)
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        status, error = "ok", None
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except SkipRun as skip:
            status, error = "skipped", (str(skip) or None)
            return None
        except Exception as exc:
            status, error = "error", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _current_run.reset(token)
            if status == "ok" and capture.errors:
                status = "error"
                error = "; ".join(capture.errors[:3])
            run = JobRun(
                job=name,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                status=status,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
            )
            await _report(run)

    _run.__wrapped__ = fn  # type: ignore[attr-defined]
    return _run


def _drop_existing(name: str) -> None:
    """Remove every job already registered under `name`.

    A drain loop, not a single `remove_job`: on a stopped scheduler
    `_pending_jobs` is a list that tolerates repeated ids, and `remove_job`
    deletes only the FIRST match. A process that ran before this fix — or
    one that called `register` three times — is holding more than one, and
    removing a single entry would leave the rest to fire.

    Bounded by construction: each iteration removes one entry, and
    `JobLookupError` (raised when none is left) is the terminator.
    """
    removed = 0
    while True:
        try:
            scheduler.remove_job(name)
        except JobLookupError:
            break
        removed += 1

    if removed > 1:
        # Never expected in a healthy process — say so rather than
        # absorbing it, since it means duplicates were live.
        logger.warning(
            "register(%r): dropped %d duplicate registrations", name, removed,
        )


def register(
    name: str,
    fn: Callable[..., Awaitable[None]],
    *,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    seconds: Optional[int] = None,
    cron: Optional[str] = None,
    misfire_grace_time: int = 30,
) -> None:
    """Register an async job on the module-level scheduler.

    Exactly one of `hours` / `minutes` / `seconds` / `cron` must be set.
    `cron` accepts a 5-field cron expression (`"min hour day month weekday"`)
    parsed by `apscheduler.triggers.cron.CronTrigger.from_crontab`.

    `misfire_grace_time` is how late a run may still fire, in seconds. The
    30s default suits the frequent jobs it was written for; a job whose
    slot matters more than its punctuality (a nightly full pull) should
    raise it, so a process restart spanning the slot still runs rather than
    silently skipping to tomorrow. Grace alone is not a durability
    guarantee — APScheduler holds the schedule in memory, so an outage
    longer than the grace still loses the slot and the caller needs its own
    catch-up on startup.

    Re-registering with the same `name` replaces the prior job, so
    hot-reload / re-import is idempotent — on a RUNNING scheduler and on a
    stopped one alike.

    That second half needs explicit work. `replace_existing=True` is only
    consulted by the jobstore, and a stopped scheduler has no jobstore yet:
    `add_job` parks the job in `_pending_jobs` and flushes it at `start()`.
    Two `register()` calls before startup therefore produced TWO entries
    with the same id, and `start()` scheduled both — a duplicated nightly
    job, silently, with no error anywhere. Every adopting product registers
    at import time (before `start_scheduler()`), so the stopped path is the
    ONLY path any of them exercise; the docstring's idempotency claim was
    true exactly where nobody relied on it.

    `_drop_existing` closes that. It drains rather than removing once
    because a pre-fix process may already be holding duplicates, and it
    runs AFTER validation below — dropping first would let a malformed
    `register()` call unregister a working job and leave nothing behind.
    """
    flavors = {
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "cron": cron,
    }
    set_flavors = {k: v for k, v in flavors.items() if v is not None}
    if len(set_flavors) != 1:
        raise ValueError(
            f"register({name!r}): exactly one of hours/minutes/seconds/cron "
            f"must be set; got {set_flavors}"
        )

    if cron is not None:
        trigger = CronTrigger.from_crontab(cron, timezone=platform_timezone_name())
    else:
        interval_kwargs = {k: v for k, v in set_flavors.items() if k != "cron"}
        trigger = IntervalTrigger(**interval_kwargs)

    # Validation passed — only now is it safe to drop the incumbent.
    _drop_existing(name)

    interval_seconds = None
    if cron is None:
        interval_seconds = int((hours or 0) * 3600 + (minutes or 0) * 60 + (seconds or 0))
    _job_specs[name] = JobSpec(
        job=name,
        cron=cron,
        interval_seconds=interval_seconds,
        timezone=platform_timezone_name(),
        misfire_grace_time=misfire_grace_time,
    )

    scheduler.add_job(
        _instrument(name, fn),
        trigger=trigger,
        id=name,
        replace_existing=True,
        misfire_grace_time=misfire_grace_time,
        coalesce=True,
        max_instances=1,
    )


#: Env marker that authorises this process to RUN scheduled jobs.
#: Set by the prod compose `x-prod-defaults` anchor, so every deployed
#: container inherits it and nothing else does.
SCHEDULERS_ENABLED_ENV = "NOCTUS_SCHEDULERS_ENABLED"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def schedulers_enabled() -> bool:
    """Is this process authorised to run scheduled jobs?

    Deliberately NOT `is_deploy_context()`. That returns True for any
    process whose environment carries prod markers — including a laptop
    that loaded the production `.env`, which is exactly the case this
    guard exists to stop. The marker has to be something only the
    deployed container has, so it lives in the compose `environment:`
    block and NEVER in `.env`.

    🔴 Do not move this key into `.env`. The whole guarantee is that the
    file a developer copies locally does not carry it.
    """
    return os.environ.get(SCHEDULERS_ENABLED_ENV, "").strip().lower() in _TRUTHY


def start_scheduler() -> None:
    """Start the module-level scheduler. Idempotent — re-calling on a
    running scheduler is a no-op.

    Refuses to start unless `schedulers_enabled()`. Registration is
    unaffected: jobs still register at import time, they simply never
    fire. So a local run gets the real app, the real routes and zero
    background writes.

    ── Why this exists (incident, 2026-08-22) ──────────────────────────
    A social-wiring backend left running on a developer laptop against
    the production `.env` woke during a macOS DarkWake, fired the
    nightly Vista sync, wrote 50 rows to the production catalog, and
    stopped mid-run when the machine went back to sleep. Nobody
    intended it and nothing recorded it: the container logs showed only
    health checks, and the write was traced only through Supabase's
    edge logs correlated against the laptop's power log.

    The blast radius was not one job. That process was running all
    fourteen registered jobs — Meta ads sync, OLX drains, e-mail sends,
    YouTube snapshots — every one of them writing to production on a
    machine nobody was watching.

    The three log levels below are the whole contract:

      · enabled                    → INFO, business as usual.
      · not enabled, not a deploy  → INFO. This is a developer laptop
                                     behaving correctly; it must not
                                     look like a problem.
      · not enabled, IS a deploy   → ERROR. A deployed container with no
                                     marker means the compose lost it,
                                     and prod silently running zero jobs
                                     is worse than the bug this fixes.
                                     That case must be impossible to
                                     miss in the logs.
    """
    if scheduler.running:
        return

    if not schedulers_enabled():
        # Imported here, not at module scope: `deploy_config` is a config
        # module and `api/` must not bind config at import time.
        from noctusai_lib.config.deploy_config import is_deploy_context

        if is_deploy_context():
            logger.error(
                "Scheduler NOT started: %s is unset in what looks like a "
                "DEPLOY context (%d job(s) registered and idle). If this is "
                "production, the compose `x-prod-defaults` environment block "
                "has lost the marker and NOTHING scheduled is running.",
                SCHEDULERS_ENABLED_ENV, len(scheduler.get_jobs()),
            )
        else:
            logger.info(
                "Scheduler not started: %s unset (%d job(s) registered, "
                "none will fire). Expected outside a deployed container — "
                "set it only in compose if you genuinely want background "
                "jobs writing from this process.",
                SCHEDULERS_ENABLED_ENV, len(scheduler.get_jobs()),
            )
        return

    scheduler.start()
    job_names = [j.id for j in scheduler.get_jobs()]
    logger.info(
        "Scheduler started: %d job(s) registered (%s)",
        len(job_names),
        ", ".join(job_names) or "<empty>",
    )
    _publish_job_registry()


def _publish_job_registry() -> None:
    """Hand the registered schedules to the run observer (the fleet-wide
    `public.scheduler_jobs` registry) on a daemon thread, so a slow or down
    database never delays boot. A failure is logged at ERROR."""
    observer = _run_observer
    specs = job_specs()
    if observer is None or not specs:
        return

    def _publish() -> None:
        try:
            observer.register_jobs(specs)
        except Exception:  # noqa: BLE001 — boot must not depend on it; loud, not silent
            logger.error(
                "scheduler job registry publish FAILED (%d job(s)): the Operação page "
                "will not list this product's schedules", len(specs), exc_info=True,
            )

    threading.Thread(target=_publish, name="scheduler-job-registry", daemon=True).start()


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def reset_for_testing() -> None:
    """Clear all registered jobs + replace the singleton — TEST USE ONLY.

    `register(...)` is module-level state, so consecutive tests that touch
    different job sets need a clean slate. Called from `conftest.py`'s
    autouse fixture in adopting products + the seed-lib's own tests.
    """
    global scheduler, _run_observer
    if scheduler.running:
        scheduler.shutdown(wait=False)
    scheduler = AsyncIOScheduler(timezone=platform_timezone_name())
    _job_specs.clear()
    _run_observer = None
