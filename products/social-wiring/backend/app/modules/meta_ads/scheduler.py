"""Meta Ads console module scheduler — daily sync job (W2.4).

Registers one job on the seed-side scheduler:
  - ``meta_ads_daily_sync``: cron ``0 6 * * *`` (one hour after the
    YouTube snapshot job's ``0 5 * * *`` slot, avoiding contention on
    the same admin-client connection pool at the same minute).
    Skips entirely (logged once, not per-org) when
    ``settings.meta_ad_account_id`` / ``settings.meta_system_user_token``
    are not configured — the operator-actionable "not wired yet" state,
    never a silent no-op that looks like a healthy empty run.

Org iteration
─────────────
Unlike ``youtube``'s per-``integration_accounts``-row iteration, the
Meta Ads console has NO per-org connection row (roadmap: "System User
token... workspace-global; no org/store" — Priority 1 in
``app.services.meta.get_meta_adapter``). The single configured ad
account is synced into EVERY org present in ``public.noctus_users`` —
correct for this initiative's v1 single-operator-account model (roadmap
Phase 4, multi-org ad accounts, is explicitly deferred and described as
"additive, no refactor" on top of today's org-keyed data model). A
per-org failure is logged at WARNING and the loop continues — one bad
org's write does not kill the run for the others (mirrors
``youtube_daily_snapshot_job``'s per-account error handling).

Pattern mirrors ``app/modules/youtube/scheduler.py``:
  - ``configure()`` registers jobs at import (called from
    ``meta_ads/__init__.py``'s ``register()``).
  - ``app/lifespan.py`` calls ``start_scheduler()``/``stop_scheduler()``
    (same re-exported handles as youtube/email_marketing — idempotent,
    safe to coexist).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)


def _target_org_id() -> UUID | None:
    """The SINGLE org the workspace-global ad account syncs into —
    ``settings.meta_ads_org_id``.

    🔴 Safe-by-default: the token + ``meta_ad_account_id`` are workspace-
    global (ONE Business-Portfolio account) but the ``ads_*`` tables are
    org-scoped by RLS. Fanning the sync across every org in
    ``noctus_users`` (the pre-2026-07-23 behavior) wrote the operator's
    private ad spend into EVERY tenant's rows — a financial-data leak the
    moment more than one org exists. So the daily job targets exactly the
    one configured org; unset ⇒ return ``None`` ⇒ the job skips (never a
    fan-out). Phase 4 (multi-org ad accounts) replaces this single value
    with a per-org ``integration_accounts`` mapping — additive, no
    behavior change for the single-account case."""
    raw = getattr(settings, "meta_ads_org_id", "") or ""
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        logger.warning(
            "meta_ads scheduler: meta_ads_org_id=%r is not a valid UUID — skipping",
            raw,
        )
        return None


def _sync_job_sync() -> None:
    """Body of the daily sync job. Runs in a worker thread
    (``asyncio.to_thread``) so a hung Supabase/Graph call doesn't freeze
    the event loop — same convention as ``youtube_daily_snapshot_job``."""
    ad_account_id = getattr(settings, "meta_ad_account_id", "") or ""
    system_user_token = getattr(settings, "meta_system_user_token", "") or ""
    if not ad_account_id or not system_user_token:
        logger.info(
            "meta_ads scheduler: not configured "
            "(meta_ad_account_id=%r, meta_system_user_token %s) — skipping",
            ad_account_id, "set" if system_user_token else "unset",
        )
        return

    admin = get_admin_client()
    if admin is None:
        logger.warning("meta_ads scheduler: no admin client — skipping sync run")
        return

    from app.modules.meta_ads.services.ads_sync_service import AdsSyncService
    from app.services.meta import MetaGraphError, get_meta_adapter

    org_id = _target_org_id()
    if org_id is None:
        logger.info(
            "meta_ads scheduler: meta_ads_org_id not configured — skipping "
            "(will NOT fan out across tenants; set META_ADS_ORG_ID to the "
            "org that owns this workspace-global ad account)"
        )
        return

    svc = AdsSyncService(admin_supabase=admin)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    activities_since = datetime.now(timezone.utc) - timedelta(days=2)
    activities_until = datetime.now(timezone.utc)

    logger.info("meta_ads scheduler: running daily sync for org=%s", org_id)
    try:
        adapter = get_meta_adapter(org_id=str(org_id))
        svc.sync_accounts(org_id=org_id, adapter=adapter)
        svc.sync_hierarchy(org_id=org_id, adapter=adapter, ad_account_id=ad_account_id)
        snapshot_count = svc.snapshot_campaign_insights(
            org_id=org_id, adapter=adapter, ad_account_id=ad_account_id,
            since=yesterday, until=today,
        )
        activity_count = svc.ingest_activities(
            org_id=org_id, adapter=adapter, ad_account_id=ad_account_id,
            since=activities_since, until=activities_until,
        )
        logger.info(
            "meta_ads scheduler: org=%s done — snapshots=%d activities=%d",
            org_id, snapshot_count, activity_count,
        )
    except MetaGraphError as exc:
        logger.warning(
            "meta_ads scheduler: sync FAILED for org=%s: %s", org_id, exc,
        )
    except Exception as exc:
        logger.warning(
            "meta_ads scheduler: unexpected error for org=%s: %s",
            org_id, exc, exc_info=True,
        )


async def meta_ads_daily_sync_job() -> None:
    """Async wrapper — runs the sync body in a thread to avoid loop
    starvation."""
    try:
        await asyncio.to_thread(_sync_job_sync)
    except Exception as exc:
        logger.error("meta_ads scheduler: job wrapper error: %s", exc, exc_info=True)


def configure() -> None:
    """Register the ``meta_ads`` daily sync job on the seed-side
    scheduler. Called from ``meta_ads/__init__.py``'s ``register()`` at
    import time — same pattern as ``youtube``/``email_marketing``.
    Idempotent."""
    seed_scheduler.register(
        "meta_ads_daily_sync",
        meta_ads_daily_sync_job,
        cron="0 6 * * *",
    )
    logger.info(
        "meta_ads scheduler configured: daily sync at cron '0 6 * * *'"
    )


# Re-export seed lifecycle handles (same pattern as youtube/email_marketing).
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler

__all__ = [
    "configure",
    "meta_ads_daily_sync_job",
    "start_scheduler",
    "stop_scheduler",
]
