"""Therapy backend scheduler — thin wrapper around `noctusai_lib.api.scheduler`.

Job functions live here (audio-retention sweep + future therapy retention
jobs); registration + lifecycle is the seed-side primitive. The
`KB § PATTERNS/accept-with-rationale.md` entry that captured the per-product
N=3 recurrence has been flipped to FORMALIZED — this file is the migration's
therapy adopter.
"""
from __future__ import annotations

import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client
from app.services.audio_retention_service import run_retention_sweep

logger = logging.getLogger(__name__)


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


def configure() -> None:
    """Register therapy's jobs on the seed-side scheduler.

    Gated by `THERAPY_SCHEDULER_ENABLED` (default True). Called from
    `main.py` at import time so the registration happens before
    `start_scheduler()` fires in the FastAPI lifespan.
    """
    if not settings.therapy_scheduler_enabled:
        logger.info(
            "Therapy scheduler disabled (THERAPY_SCHEDULER_ENABLED=false); "
            "skipping registration"
        )
        return
    seed_scheduler.register(
        "therapy_audio_retention",
        audio_retention_job,
        hours=settings.therapy_audio_retention_sweep_interval_hours,
    )
    logger.info(
        "Therapy scheduler configured: audio_retention every %dh",
        settings.therapy_audio_retention_sweep_interval_hours,
    )


# Re-export the seed-side primitives so `main.py`'s
# `lifespan_startup=start_scheduler, lifespan_shutdown=stop_scheduler`
# wiring works unchanged.
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler
