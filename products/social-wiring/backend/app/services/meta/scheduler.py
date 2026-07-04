"""Instagram metric-snapshot daily automation — seed scheduler job.

Registers ONE daily job (``meta_ig_snapshot_daily``) that walks every org
with a stored Meta credential row (``social_wiring.credentials`` WHERE
``provider='meta'``) and calls
:func:`app.services.meta.snapshots.capture_all_ig_snapshots` for each.
The manual ``POST /api/meta/instagram/{ig_user_id}/snapshot`` endpoint
covers the gap for an org between connecting Meta and the next daily run.

Registration mirrors ``app.modules.email_marketing.scheduler`` (the
seed-side ``noctusai_lib.api.scheduler`` primitive) — see that module's
docstring for the two-call contract: jobs register at import time via
:func:`configure`; ``start_scheduler`` / ``stop_scheduler`` are already
wired into ``app/lifespan.py`` (idempotent — co-existing with the W2.2
email_marketing jobs on the same seed scheduler singleton is safe).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client
from app.services.meta import META_PROVIDER
from app.services.meta.snapshots import capture_all_ig_snapshots

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"


def _orgs_with_meta_credential(admin: Any) -> list[str]:
    """Distinct org_ids with a stored Meta credential row.

    Scheduler-only discovery — the manual endpoint doesn't need this
    (it's already scoped to one org via the ``org_id`` query param)."""
    resp = (
        admin
        .schema(_SCHEMA)
        .table("credentials")
        .select("org_id")
        .eq("provider", META_PROVIDER)
        .execute()
    )
    rows = resp.data or []
    return sorted({row["org_id"] for row in rows if row.get("org_id")})


def _daily_ig_snapshot_sync() -> None:
    admin = get_admin_client()
    if admin is None:
        return
    for org_id in _orgs_with_meta_credential(admin):
        try:
            rows = capture_all_ig_snapshots(admin, org_id)
            logger.info(
                "meta ig snapshot daily job: org=%s captured %d account(s)",
                org_id, len(rows),
            )
        except Exception as exc:
            logger.error(
                "meta ig snapshot daily job: org=%s failed: %s",
                org_id, exc, exc_info=True,
            )


async def daily_ig_snapshot_job() -> None:
    """Body runs in a worker thread (mirrors ``scheduled_campaigns_job``)
    so a hung Supabase/Graph call never freezes the asyncio loop."""
    try:
        await asyncio.to_thread(_daily_ig_snapshot_sync)
    except Exception as exc:
        logger.error("meta ig snapshot daily job error: %s", exc)


def configure() -> None:
    """Register the daily IG-snapshot job on the seed scheduler.

    Idempotent (``register`` replaces-existing); called from
    ``app.main._register_media_wiring`` at import time, before any
    ``start_scheduler()`` fires."""
    seed_scheduler.register(
        "meta_ig_snapshot_daily",
        daily_ig_snapshot_job,
        cron="0 6 * * *",  # 06:00 America/Sao_Paulo daily
    )
    logger.info("meta ig snapshot scheduler configured: daily at 06:00")


__all__ = ["configure", "daily_ig_snapshot_job"]
