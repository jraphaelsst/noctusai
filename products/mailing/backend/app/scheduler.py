"""Mailing backend scheduler — migrated to `noctusai_lib.api.scheduler`.

Three jobs:
  1. Send loop (every 30s) — process queued send_logs via Resend Batch API
  2. Scheduled campaigns (every 60s) — check for campaigns with scheduled_at <= now
  3. Automation processor (every 5min) — process automation enrollments

Each job's body is mailing-specific; the registration + lifecycle is the
seed-side primitive (`noctusai_lib.api.scheduler`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.database import get_admin_client
from app.services.send_service import SendService

logger = logging.getLogger(__name__)


async def send_loop_job():
    """Process queued send_logs — pick up to 100, send via Resend Batch API."""
    try:
        db = get_admin_client()
        svc = SendService(db, settings)
        sent = await svc.process_queued_sends(batch_size=settings.max_batch_size)
        if sent > 0:
            logger.info("Send loop: processed %d emails", sent)
    except Exception as e:
        logger.error("Send loop error: %s", e)


def _scheduled_campaigns_sync():
    db = get_admin_client()
    now = datetime.now(timezone.utc).isoformat()
    result = (db.table("campaigns").select("id, org_id")
              .eq("status", "agendada")
              .lte("scheduled_at", now)
              .execute())

    campaigns = result.data or []
    if not campaigns:
        return

    svc = SendService(db, settings)
    for campaign in campaigns:
        cid = campaign["id"]
        org_id = campaign["org_id"]
        db.table("campaigns").update({
            "status": "enviando",
            "started_at": now,
        }).eq("id", cid).execute()
        queued = svc.queue_campaign_sends(cid, org_id)
        logger.info("Scheduled campaign %s started — %d sends queued", cid, queued)


async def scheduled_campaigns_job():
    """Check for campaigns with scheduled_at <= now and trigger sending.

    Body runs in a worker thread so a hung Supabase call (network blip,
    DNS failure, dropped keep-alive) does not freeze the asyncio loop and
    starve the other scheduled jobs.
    """
    try:
        await asyncio.to_thread(_scheduled_campaigns_sync)
    except Exception as e:
        logger.error("Scheduled campaigns job error: %s", e)


def _automation_processor_sync():
    db = get_admin_client()
    now = datetime.now(timezone.utc).isoformat()
    result = (db.table("automation_enrollments").select("*")
              .eq("status", "active")
              .lte("next_action_at", now)
              .limit(50)
              .execute())

    enrollments = result.data or []
    if enrollments:
        logger.info("Automation processor: %d enrollments to process", len(enrollments))
        # TODO: implement step execution when automation_service is built


async def automation_processor_job():
    """Process automation enrollments with next_action_at <= now.

    Body runs in a worker thread (see `scheduled_campaigns_job`).
    Placeholder — full automation step execution will be implemented
    when the automation service is complete.
    """
    try:
        await asyncio.to_thread(_automation_processor_sync)
    except Exception as e:
        logger.error("Automation processor error: %s", e)


def configure() -> None:
    """Register mailing's jobs on the seed-side scheduler.

    Called from `main.py` at import time so the registrations land before
    `start_scheduler()` fires in the FastAPI lifespan.
    """
    seed_scheduler.register(
        "mailing_send_loop",
        send_loop_job,
        seconds=settings.send_loop_seconds,
    )
    seed_scheduler.register(
        "mailing_scheduled_campaigns",
        scheduled_campaigns_job,
        seconds=settings.scheduled_campaign_check_seconds,
    )
    seed_scheduler.register(
        "mailing_automation_processor",
        automation_processor_job,
        minutes=settings.automation_check_minutes,
    )
    logger.info(
        "Mailing scheduler configured: send_loop=%ds, scheduled_campaigns=%ds, automations=%dmin",
        settings.send_loop_seconds,
        settings.scheduled_campaign_check_seconds,
        settings.automation_check_minutes,
    )


# Re-export so `main.py`'s lifespan_startup / lifespan_shutdown wiring is
# unchanged across the migration.
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler
