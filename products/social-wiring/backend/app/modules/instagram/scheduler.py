"""Instagram module scheduler — the daily catalog + snapshot job.

Registers ``instagram_daily_snapshot`` on the seed scheduler at cron
``30 5 * * *`` (05:30 BRT — 30 min after ``youtube_daily_snapshot`` so the
two daily walks don't contend for the same worker minute). Walks every
``integration_accounts`` row with ``provider='instagram'`` and
``status='validated'`` and runs :class:`IgSyncService` per account; one bad
account is logged and the walk continues (never silent, never fatal).

Same shape as ``app/modules/youtube/scheduler.py``: ``configure()`` is called
from the module's ``register()``; ``app/lifespan.py`` starts the scheduler.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

JOB_NAME = "instagram_daily_snapshot"
JOB_CRON = "30 5 * * *"


def run_daily_sync(repo: Any = None, adapter_builder: Any = None) -> dict[str, int]:
    """Body of the daily job (sync; runs in a worker thread). Returns a
    tally ``{accounts, done, partial, skipped, failed, missing_scope}`` —
    the DI params exist for tests; production passes neither."""
    from app.modules.instagram.repository import IgInsightsRepository
    from app.modules.instagram.sync_service import (
        IgSyncError,
        IgSyncService,
        missing_insights_scope,
    )

    tally = {"accounts": 0, "done": 0, "partial": 0, "skipped": 0, "failed": 0, "missing_scope": 0}
    if repo is None:
        admin = get_admin_client()
        if admin is None:
            logger.error("instagram scheduler: no admin client — daily sync NOT run")
            return tally
        repo = IgInsightsRepository(admin)
    if adapter_builder is None:
        from app.services.meta import get_instagram_login_adapter_for_account

        adapter_builder = get_instagram_login_adapter_for_account

    accounts = repo.list_validated_accounts()
    tally["accounts"] = len(accounts)
    if not accounts:
        logger.info("instagram scheduler: no validated Instagram accounts")
        return tally

    svc = IgSyncService(repo=repo, adapter_builder=adapter_builder)
    for row in accounts:
        account_id = UUID(str(row["id"]))
        org_id = UUID(str(row["org_id"]))
        if missing_insights_scope(row):
            tally["missing_scope"] += 1
            logger.warning(
                "instagram scheduler: account=%s lacks instagram_business_manage_insights "
                "— skipped until the account is reconnected",
                account_id,
            )
            continue
        try:
            outcome = svc.run_for_account(org_id=org_id, account_id=account_id)
            tally[outcome.status] = tally.get(outcome.status, 0) + 1
        except IgSyncError as exc:
            tally["failed"] += 1
            logger.warning("instagram scheduler: account=%s FAILED: %s", account_id, exc)
        except Exception as exc:  # one account never kills the walk — logged loud
            tally["failed"] += 1
            logger.error(
                "instagram scheduler: unexpected error for account=%s: %s",
                account_id, exc, exc_info=True,
            )
    logger.info("instagram scheduler: daily sync tally %s", tally)
    return tally


async def instagram_daily_snapshot_job() -> None:
    try:
        await asyncio.to_thread(run_daily_sync)
    except Exception as exc:
        logger.error("instagram scheduler: job wrapper error: %s", exc, exc_info=True)


def configure() -> None:
    seed_scheduler.register(JOB_NAME, instagram_daily_snapshot_job, cron=JOB_CRON)
    logger.info("instagram scheduler configured: %s at cron %r", JOB_NAME, JOB_CRON)


__all__ = ["configure", "instagram_daily_snapshot_job", "run_daily_sync", "JOB_NAME", "JOB_CRON"]
