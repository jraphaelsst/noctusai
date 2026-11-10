"""``email_marketing`` module scheduler — jobs on the seed primitive.

Three jobs (ported verbatim from the retired ``mailing`` product's
scheduler, consolidated into ``social-wiring`` 2026-05-16):

  1. Send loop (every 30s) — process queued ``send_logs`` via Resend Batch API
  2. Scheduled campaigns (every 60s) — campaigns with ``scheduled_at <= now``
  3. Automation processor (every 5min) — enqueue due automation enrollments as jobs

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
from noctusai_lib.primitives.ttl_cache import IdleGate

from app.config import settings
from app.dependencies import get_admin_client
from app.modules.email_marketing.services.send_service import SendService
from app.modules.email_marketing.wake import CAMPAIGNS_GATE, SEND_GATE

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


async def send_loop_job(*, db=None, gate: IdleGate | None = None) -> None:
    """Process queued ``send_logs`` — pick up to N, send via Resend Batch.

    Idle-gated: an empty queue backs the loop off to ``SEND_FALLBACK_S`` (a producer in this process wakes it at
    once — ``wake.wake_send_loop``). A full batch keeps it busy so a backlog drains at the tick rate."""
    gate = gate or SEND_GATE
    if not gate.due():
        return
    try:
        db = db if db is not None else get_admin_client()
        if db is None:
            gate.idle()
            return
        svc = SendService(db, settings)
        sent = await svc.process_queued_sends(batch_size=_MAX_BATCH_SIZE)
        if sent > 0:
            logger.info("email_marketing send loop: processed %d emails", sent)
        if svc.last_picked:
            gate.busy()  # real work (a full batch means more may be queued behind it): look again at the next tick
        else:
            gate.idle()
    except Exception as e:
        gate.failed(base_s=30)  # bounded exponential backoff (30 s .. SEND_FALLBACK_S): an outage is not hammered
        logger.error("email_marketing send loop error: %s", e)


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# NOC-REMEDIATE[poller-head-of-line]: one failing campaign aborts the rest of this tick (and `process_queued_sends` has the
# same shape: one bad send group stops the batch behind it). Destination: per-item try/except with a named failure
# status so a single poison item cannot starve the others — 2026-11-10.
def _scheduled_campaigns_sync(db=None, gate: IdleGate | None = None) -> None:
    gate = gate or CAMPAIGNS_GATE
    db = db if db is not None else get_admin_client()
    if db is None:
        gate.idle()
        return
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    result = (
        db.table("campaigns")
        .select("id, org_id, scheduled_at")
        .eq("status", "agendada")
        .order("scheduled_at")
        .limit(100)
        .execute()
    )
    scheduled = result.data or []
    due = [c for c in scheduled if c.get("scheduled_at") and _parse_ts(c["scheduled_at"]) <= now_dt]
    if not due:
        future = [_parse_ts(c["scheduled_at"]) for c in scheduled if c.get("scheduled_at")]
        # Nothing scheduled -> sleep to the fallback; a campaign scheduled for later -> sleep until it is due.
        gate.idle(next_due_in_s=(min(future) - now_dt).total_seconds() if future else None)
        return
    svc = SendService(db, settings)
    for campaign in due:
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
    gate.busy()  # after the work (a failure above reaches the job's `failed()` backoff instead)


async def scheduled_campaigns_job() -> None:
    """Trigger sending for campaigns whose ``scheduled_at`` has passed.

    Idle-gated: it sleeps until the next known ``scheduled_at`` (or ``CAMPAIGNS_FALLBACK_S`` when nothing is
    scheduled); scheduling or rescheduling a campaign wakes it (``wake.wake_campaigns_check``).

    Body runs in a worker thread so a hung Supabase call doesn't freeze
    the asyncio loop and starve the other scheduled jobs.
    """
    if not CAMPAIGNS_GATE.due():
        return
    try:
        await asyncio.to_thread(_scheduled_campaigns_sync)
    except Exception as e:
        CAMPAIGNS_GATE.failed(base_s=60)  # bounded exponential backoff, not tick-rate hammering
        logger.error("email_marketing scheduled campaigns job error: %s", e)


async def automation_processor_job() -> None:
    """Enqueue one ``email_marketing.automation_step`` job per due enrollment (idempotent on
    ``enrollment_id:step_id``). The step itself runs in the seed ``Worker``
    (``services/automation_worker.py``), never here."""
    try:
        db = get_admin_client()
        if db is None:
            return
        from app.modules.email_marketing.services.automation_executor import enqueue_due
        from app.modules.email_marketing.services.automation_worker import make_jobs_repository

        seen = await enqueue_due(db, make_jobs_repository(db))
        if seen:
            logger.info("email_marketing automation processor: %d due enrollment(s) enqueued", seen)
    except Exception as e:
        logger.error("email_marketing automation processor error: %s", e)


def configure() -> None:
    """Register the module's jobs on the seed-side scheduler.

    Called from the module ``register()`` at import time so the
    registrations land before any ``start_scheduler()`` fires in the
    FastAPI lifespan. Idempotent — re-registering replaces the prior job.
    """
    # poll-budget: 30s ticks; 0 calls/tick idle (gate), 1 send_logs read when probing; worst 288/day idle (probe every 5 min, a producer wakes it), 2880/day only while a backlog drains, errors back off 30s..5min; max added delay 0 for an in-process producer (wake), 300s for any other; idle=event
    seed_scheduler.register(
        "email_marketing_send_loop",
        send_loop_job,
        seconds=_SEND_LOOP_SECONDS,
    )
    # poll-budget: 60s ticks; 0 calls/tick idle (gate), 1 campaigns read when probing; worst 144/day (probe every 10 min or at the next scheduled_at, scheduling wakes it), errors back off 60s..10min; max added delay 0 (wake / next scheduled_at), 600s for an out-of-process change; idle=event
    seed_scheduler.register(
        "email_marketing_scheduled_campaigns",
        scheduled_campaigns_job,
        seconds=_SCHEDULED_CAMPAIGN_CHECK_SECONDS,
    )
    # poll-budget: 5min ticks; 1 call/tick (scan_due_enrollments, named columns, limit 50); worst 288/day; max added delay 0 over the cadence; idle=fixed
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
