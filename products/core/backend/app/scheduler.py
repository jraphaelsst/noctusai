"""
Background scheduler for the Core product.

Mirrors the mailing/personal-finance/erp pattern: single in-process
APScheduler (`AsyncIOScheduler`) wired via seed's `lifespan_startup` /
`lifespan_shutdown` seams on `create_product_app()`.

Phase 1 jobs:
  1. `webhook_retention_sweep` — daily at 03:00 America/Sao_Paulo.
     Purges `webhook_deliveries` rows past `retention_until`. Implements
     LGPD Art. 16 (data retention limits) for webhook payloads carrying PII
     (e.g., `team.invite_sent` with email).

Future jobs go through `start_scheduler()` below — one `add_job()` each,
keyed by a stable `id` with `replace_existing=True`. Follow-up projects
(e.g., invitation-cleanup, stale-api-key-audit) add their registrations
here rather than spawning per-feature schedulers.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import get_admin_client
from app.services.webhook_retention_service import run_retention_sweep

logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


async def webhook_retention_sweep_job() -> None:
    """Daily purge of expired webhook deliveries.

    Idempotent — `run_retention_sweep` no-ops when nothing is expired.
    Errors are logged, not raised, so a transient DB blip doesn't crash
    the scheduler loop.
    """
    try:
        db = get_admin_client()
        result = run_retention_sweep(db)
        if result.get("purged", 0) > 0:
            logger.info("Webhook retention sweep: %d deliveries purged", result["purged"])
    except Exception as e:
        logger.error("Webhook retention sweep error: %s", e)


def start_scheduler() -> None:
    """Register jobs and start the scheduler.

    Called from seed's `lifespan_startup`. No-op if the scheduler is
    already running (idempotent across test-reloads).
    """
    if scheduler.running:
        return

    webhook_cron = getattr(settings, "webhook_retention_cron", "0 3 * * *")

    scheduler.add_job(
        webhook_retention_sweep_job,
        trigger=CronTrigger.from_crontab(webhook_cron, timezone="America/Sao_Paulo"),
        id="core_webhook_retention_sweep",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Core scheduler started: webhook_retention_sweep cron=%r", webhook_cron)


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Core scheduler stopped")
