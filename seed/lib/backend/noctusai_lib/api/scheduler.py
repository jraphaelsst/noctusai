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

**CI safety.** The FastAPI `TestClient` skips lifespan unless invoked as a
context manager, which existing product test suites don't do. So
`start_scheduler()` doesn't fire during pytest. The
`<PRODUCT>_SCHEDULER_ENABLED` env flag is a second layer of safety —
products can override per-environment.

**Logging.** APScheduler's verbose DEBUG output (job execution / next
wakeup chatter) is silenced to WARNING at module import. Job functions
should log meaningful events at INFO; per-tick noise stays out of prod
logs.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Silence APScheduler verbose DEBUG logging once at import time. Adopters
# don't have to repeat this in their wrappers.
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Module-level scheduler. Singleton-per-process matches APScheduler's
# AsyncIOScheduler design — there's only one event loop in a uvicorn
# worker.
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


def register(
    name: str,
    fn: Callable[..., Awaitable[None]],
    *,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    seconds: Optional[int] = None,
    cron: Optional[str] = None,
) -> None:
    """Register an async job on the module-level scheduler.

    Exactly one of `hours` / `minutes` / `seconds` / `cron` must be set.
    `cron` accepts a 5-field cron expression (`"min hour day month weekday"`)
    parsed by `apscheduler.triggers.cron.CronTrigger.from_crontab`.

    Re-registering with the same `name` replaces the prior job
    (`replace_existing=True`), so hot-reload / re-import is idempotent.
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
        trigger = CronTrigger.from_crontab(cron, timezone="America/Sao_Paulo")
    else:
        interval_kwargs = {k: v for k, v in set_flavors.items() if k != "cron"}
        trigger = IntervalTrigger(**interval_kwargs)

    scheduler.add_job(
        fn,
        trigger=trigger,
        id=name,
        replace_existing=True,
    )


def start_scheduler() -> None:
    """Start the module-level scheduler. Idempotent — re-calling on a
    running scheduler is a no-op."""
    if scheduler.running:
        return
    scheduler.start()
    job_names = [j.id for j in scheduler.get_jobs()]
    logger.info(
        "Scheduler started: %d job(s) registered (%s)",
        len(job_names),
        ", ".join(job_names) or "<empty>",
    )


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
    global scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
