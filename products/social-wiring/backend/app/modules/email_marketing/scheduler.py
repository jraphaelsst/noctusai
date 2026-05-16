"""``email_marketing`` module scheduler — jobs on the seed primitive.

Three jobs (ported verbatim from ``products/mailing/backend/app/scheduler``):

  1. Send loop (every 30s) — process queued ``send_logs`` via Resend Batch API
  2. Scheduled campaigns (every 60s) — campaigns with ``scheduled_at <= now``
  3. Automation processor (every 5min) — process automation enrollments

Each job body is email-marketing-specific; the registration + lifecycle is
the seed-side primitive (``noctusai_lib.api.scheduler``).

────────────────────────────────────────────────────────────────────────
LIFESPAN SEAM NOTE (for the architect — see findings)
────────────────────────────────────────────────────────────────────────
``ModuleRegistration`` only carries ``routers`` + ``standard_routers`` —
it has NO lifespan hook. The seed scheduler must be *started* inside the
asyncio event loop (``AsyncIOScheduler``), which only exists once the app
is running, so it cannot start at import time.

This module registers its jobs at import (``configure()`` runs from
``register()`` in ``__init__``) so they land before any
``start_scheduler()`` call. The actual ``start_scheduler()`` /
``stop_scheduler()`` calls must be wired into ``app/lifespan.py``
(out of this engineer's file scope — returned as a TEXT delta for the
architect to splice). ``start_scheduler`` / ``stop_scheduler`` are
idempotent, so co-existing with the W2.1 conversation-worker lifespan is
safe.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client
from app.modules.email_marketing.services.send_service import SendService

logger = logging.getLogger(__name__)

# Module-local interval defaults. social-wiring's ``SocialWiringSettings``
# does not declare the mailing scheduler-interval fields; ``getattr`` with
# the mailing defaults keeps behaviour identical while letting an operator
# override via env (add the fields to SocialWiringSettings — surfaced as a
# recommended config delta in the return).
_SEND_LOOP_SECONDS = getattr(settings, "send_loop_seconds", 30)
_AUTOMATION_CHECK_MINUTES = getattr(settings, "automation_check_minutes", 5)
_SCHEDULED_CAMPAIGN_CHECK_SECONDS = getattr(
    settings, "scheduled_campaign_check_seconds", 60
)
_MAX_BATCH_SIZE = getattr(settings, "max_batch_size", 100)


async def send_loop_job() -> None:
    """Process queued ``send_logs`` — pick up to N, send via Resend Batch."""
    try:
        db = get_admin_client()
        if db is None:
            return
        svc = SendService(db, settings)
        sent = await svc.process_queued_sends(batch_size=_MAX_BATCH_SIZE)
        if sent > 0:
            logger.info("email_marketing send loop: processed %d emails", sent)
    except Exception as e:
        logger.error("email_marketing send loop error: %s", e)


def _scheduled_campaigns_sync() -> None:
    db = get_admin_client()
    if db is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    result = (
        db.table("campaigns")
        .select("id, org_id")
        .eq("status", "agendada")
        .lte("scheduled_at", now)
        .execute()
    )
    campaigns = result.data or []
    if not campaigns:
        return
    svc = SendService(db, settings)
    for campaign in campaigns:
        cid = campaign["id"]
        org_id = campaign["org_id"]
        db.table("campaigns").update(
            {"status": "enviando", "started_at": now}
        ).eq("id", cid).execute()
        queued = svc.queue_campaign_sends(cid, org_id)
        logger.info(
            "email_marketing scheduled campaign %s started — %d sends queued",
            cid,
            queued,
        )


async def scheduled_campaigns_job() -> None:
    """Trigger sending for campaigns whose ``scheduled_at`` has passed.

    Body runs in a worker thread so a hung Supabase call doesn't freeze
    the asyncio loop and starve the other scheduled jobs.
    """
    try:
        await asyncio.to_thread(_scheduled_campaigns_sync)
    except Exception as e:
        logger.error("email_marketing scheduled campaigns job error: %s", e)


def _automation_processor_sync() -> None:
    db = get_admin_client()
    if db is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    result = (
        db.table("automation_enrollments")
        .select("*")
        .eq("status", "active")
        .lte("next_action_at", now)
        .limit(50)
        .execute()
    )
    enrollments = result.data or []
    if enrollments:
        logger.info(
            "email_marketing automation processor: %d enrollments to process",
            len(enrollments),
        )
        # Step-execution parity with mailing: full automation step
        # execution is intentionally not yet implemented (mailing carried
        # the same TODO). Enrollment scan only.


async def automation_processor_job() -> None:
    """Process automation enrollments with ``next_action_at <= now``.

    Body runs in a worker thread (see ``scheduled_campaigns_job``).
    """
    try:
        await asyncio.to_thread(_automation_processor_sync)
    except Exception as e:
        logger.error("email_marketing automation processor error: %s", e)


def configure() -> None:
    """Register the module's jobs on the seed-side scheduler.

    Called from the module ``register()`` at import time so the
    registrations land before any ``start_scheduler()`` fires in the
    FastAPI lifespan. Idempotent — re-registering replaces the prior job.
    """
    seed_scheduler.register(
        "email_marketing_send_loop",
        send_loop_job,
        seconds=_SEND_LOOP_SECONDS,
    )
    seed_scheduler.register(
        "email_marketing_scheduled_campaigns",
        scheduled_campaigns_job,
        seconds=_SCHEDULED_CAMPAIGN_CHECK_SECONDS,
    )
    seed_scheduler.register(
        "email_marketing_automation_processor",
        automation_processor_job,
        minutes=_AUTOMATION_CHECK_MINUTES,
    )
    logger.info(
        "email_marketing scheduler configured: send_loop=%ds, "
        "scheduled_campaigns=%ds, automations=%dmin",
        _SEND_LOOP_SECONDS,
        _SCHEDULED_CAMPAIGN_CHECK_SECONDS,
        _AUTOMATION_CHECK_MINUTES,
    )


# Re-export the seed scheduler lifecycle so ``app/lifespan.py`` can wire
# start/stop without importing the seed module directly.
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler

__all__ = [
    "configure",
    "send_loop_job",
    "scheduled_campaigns_job",
    "automation_processor_job",
    "start_scheduler",
    "stop_scheduler",
]
