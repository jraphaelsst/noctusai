"""YouTube module scheduler — daily snapshot jobs.

Registers one job on the seed-side scheduler:
  - youtube_daily_snapshot: cron ``0 5 * * *`` (05:00 BRT = 08:00 UTC)
    Iterates all validated YouTube integration_accounts and runs
    SnapshotService.run_for_account per account. Errors per-account are
    logged at WARNING + continue (one bad account does not kill the run).

Pattern mirrors ``app/modules/email_marketing/scheduler.py`` exactly:
  - ``configure()`` registers jobs at import (called from ``__init__.py``
    ``register()``).
  - ``app/lifespan.py`` calls ``start_scheduler()`` / ``stop_scheduler()``
    (same re-exported handles as email_marketing).
"""
from __future__ import annotations

import asyncio
import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)


def _snapshot_job_sync() -> None:
    """Body of the daily snapshot job. Runs in a worker thread (asyncio.to_thread)
    so a hung Supabase call doesn't freeze the event loop."""
    admin = get_admin_client()
    if admin is None:
        logger.warning("youtube scheduler: no admin client — skipping snapshot run")
        return

    cfg = settings
    from app.services.integration_account_service import build_integration_account_service
    from app.modules.youtube.services.snapshot_service import SnapshotService, SnapshotServiceError

    try:
        ia_svc = build_integration_account_service(
            admin, encryption_key=cfg.encryption_key
        )
    except Exception as exc:
        logger.error("youtube scheduler: failed to build ia_svc: %s", exc)
        return

    # List all validated YouTube accounts across all orgs.
    # service_role client — no org_id filter needed at this level.
    try:
        resp = (
            admin
            .schema("social_wiring")
            .table("integration_accounts")
            .select("id, org_id")
            .eq("provider", "youtube")
            .eq("status", "validated")
            .execute()
        )
        accounts = resp.data or []
    except Exception as exc:
        logger.error("youtube scheduler: failed to list accounts: %s", exc)
        return

    if not accounts:
        logger.info("youtube scheduler: no validated YouTube accounts found")
        return

    svc = SnapshotService(admin_supabase=admin, cfg=cfg)
    from uuid import UUID

    logger.info("youtube scheduler: running snapshot for %d account(s)", len(accounts))
    for row in accounts:
        account_id = UUID(str(row["id"]))
        org_id = UUID(str(row["org_id"]))
        try:
            outcome = svc.run_for_account(org_id=org_id, account_id=account_id)
            if outcome.skipped:
                logger.info(
                    "youtube scheduler: account=%s skipped (already done today)", account_id
                )
            else:
                logger.info(
                    "youtube scheduler: account=%s done — videos=%d shorts=%d snapshots=%d",
                    account_id,
                    outcome.videos_upserted,
                    outcome.shorts_upserted,
                    outcome.video_snapshots_upserted,
                )
        except SnapshotServiceError as exc:
            # Per-account failure: log + continue (never silent).
            logger.warning(
                "youtube scheduler: snapshot FAILED for account=%s: %s",
                account_id, exc,
            )
        except Exception as exc:
            logger.warning(
                "youtube scheduler: unexpected error for account=%s: %s",
                account_id, exc,
                exc_info=True,
            )


async def youtube_daily_snapshot_job() -> None:
    """Async wrapper — runs the sync body in a thread to avoid loop starvation."""
    try:
        await asyncio.to_thread(_snapshot_job_sync)
    except Exception as exc:
        logger.error("youtube scheduler: job wrapper error: %s", exc, exc_info=True)


def configure() -> None:
    """Register the youtube daily snapshot job on the seed-side scheduler.

    Called from ``app/modules/youtube/__init__.py``'s ``register()`` at
    import time — same pattern as email_marketing. Idempotent.
    """
    seed_scheduler.register(
        "youtube_daily_snapshot",
        youtube_daily_snapshot_job,
        cron="0 5 * * *",
    )
    logger.info("youtube scheduler configured: daily snapshot at 05:00 BRT (cron '0 5 * * *')")


# Re-export seed lifecycle handles (same pattern as email_marketing.scheduler).
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler

__all__ = [
    "configure",
    "youtube_daily_snapshot_job",
    "start_scheduler",
    "stop_scheduler",
]
