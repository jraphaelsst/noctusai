"""
Background scheduler for the Mailing product.

Three jobs:
  1. Send loop (every 30s) — process queued send_logs via Resend Batch API
  2. Scheduled campaigns (every 60s) — check for campaigns with scheduled_at <= now
  3. Automation processor (every 5min) — process automation enrollments

Uses APScheduler's AsyncIOScheduler, same pattern as Personal Finance.
"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import get_admin_client
from app.services.send_service import SendService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")


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


async def scheduled_campaigns_job():
    """Check for campaigns with scheduled_at <= now and trigger sending."""
    try:
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

    except Exception as e:
        logger.error("Scheduled campaigns job error: %s", e)


async def automation_processor_job():
    """Process automation enrollments with next_action_at <= now.

    Placeholder — full automation step execution will be implemented
    when the automation service is complete.
    """
    try:
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

    except Exception as e:
        logger.error("Automation processor error: %s", e)


def start_scheduler():
    """Register jobs and start the scheduler."""
    scheduler.add_job(
        send_loop_job,
        trigger=IntervalTrigger(seconds=settings.send_loop_seconds),
        id="mailing_send_loop",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_campaigns_job,
        trigger=IntervalTrigger(seconds=settings.scheduled_campaign_check_seconds),
        id="mailing_scheduled_campaigns",
        replace_existing=True,
    )
    scheduler.add_job(
        automation_processor_job,
        trigger=IntervalTrigger(minutes=settings.automation_check_minutes),
        id="mailing_automation_processor",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Mailing scheduler started: send_loop=%ds, scheduled_campaigns=%ds, automations=%dmin",
        settings.send_loop_seconds,
        settings.scheduled_campaign_check_seconds,
        settings.automation_check_minutes,
    )


def stop_scheduler():
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Mailing scheduler stopped")
