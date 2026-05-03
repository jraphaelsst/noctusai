"""Therapy backend scheduler.

Houses the audio-retention sweep + a generic
`register(name, fn, hours=..., minutes=..., seconds=...)` surface so future
therapy retention jobs (transcription cleanup, journal archive, etc.) slot in
without re-architecting.

Recurrence-rule note. This is the 3rd per-product `app/scheduler.py` (mailing,
personal-finance, now therapy). Reaching N=3 trips the recurrence rule's
`MUST formalize` action — the seed-side primitive `noctusai_lib.api.scheduler`
is filed as a follow-up project (`projects/seed-side-scheduler-primitive/`).
When that primitive lands, this file collapses to a one-liner that registers
the audio-retention job against the seed-side scheduler, and mailing/PF migrate
to the same primitive. Until then this file accepts the technical debt with
rationale (`KB § PATTERNS/accept-with-rationale.md` entry).

CI/test safety. The FastAPI `TestClient` used in therapy tests does NOT fire
lifespan events unless invoked as `with TestClient(app) as client:`. The
existing `tests/conftest.py` uses the simple form, so `start_scheduler()`
never runs during the test suite. The `THERAPY_SCHEDULER_ENABLED` env flag
adds a second layer of safety (set it to `false` in any environment that
shouldn't sweep — e.g. local dev pointed at the live DB).
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Silence APScheduler verbose DEBUG logging (job execution / next wakeup chatter).
logging.getLogger("apscheduler").setLevel(logging.WARNING)

from app.config import settings
from app.dependencies import get_admin_client
from app.services.audio_retention_service import run_retention_sweep

logger = logging.getLogger(__name__)

# accept-with-rationale: Per-product app/scheduler.py at N=3 (mailing/PF/therapy) — pending seed-side primitive in KB § PATTERNS/accept-with-rationale.md
scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


def register(
    name: str,
    fn: Callable[..., Awaitable[None]],
    *,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    seconds: Optional[int] = None,
) -> None:
    """Register an async job on the module-level scheduler.

    Exactly one of `hours` / `minutes` / `seconds` must be provided. The job
    runs on an `IntervalTrigger` with `replace_existing=True` so re-registration
    (e.g. across hot-reloads) is idempotent.
    """
    interval_kwargs = {
        k: v
        for k, v in {"hours": hours, "minutes": minutes, "seconds": seconds}.items()
        if v is not None
    }
    if len(interval_kwargs) != 1:
        raise ValueError(
            f"register({name!r}): exactly one of hours/minutes/seconds must be set; "
            f"got {interval_kwargs}"
        )
    scheduler.add_job(
        fn,
        trigger=IntervalTrigger(**interval_kwargs),
        id=name,
        replace_existing=True,
    )


async def audio_retention_job() -> None:
    """Run the audio-retention sweep using the admin client."""
    try:
        db = get_admin_client()
        summary = run_retention_sweep(db)
        if isinstance(summary, dict):
            expired = summary.get("expired", 0)
            deleted = summary.get("deleted", 0)
            if expired or deleted:
                logger.info(
                    "Therapy audio-retention sweep: expired=%d deleted=%d",
                    expired,
                    deleted,
                )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Therapy audio-retention sweep failed: %s", exc, exc_info=True
        )


def start_scheduler() -> None:
    """Register the built-in jobs and start the scheduler.

    Gated by `THERAPY_SCHEDULER_ENABLED` (default True). Additional jobs can
    call `register(...)` before this function runs (e.g. from another startup
    hook); they will be registered on the same scheduler instance.
    """
    if not settings.therapy_scheduler_enabled:
        logger.info(
            "Therapy scheduler disabled (THERAPY_SCHEDULER_ENABLED=false); "
            "skipping startup"
        )
        return

    register(
        "therapy_audio_retention",
        audio_retention_job,
        hours=settings.therapy_audio_retention_sweep_interval_hours,
    )
    scheduler.start()
    logger.info(
        "Therapy scheduler started: audio_retention every %dh",
        settings.therapy_audio_retention_sweep_interval_hours,
    )


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Therapy scheduler stopped")
