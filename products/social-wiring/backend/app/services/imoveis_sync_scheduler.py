"""Daily Vista catalog refresh — seed scheduler job.

Registers ONE daily job (``imoveis_vista_sync_daily``) that re-pulls the
Vista catalog into ``social_wiring.imoveis`` at **00:05 America/Sao_Paulo**.
Before this existed the mirror only moved when a human pressed
"Sincronizar com o Vista" on the Imóveis page — it had been stale since
2026-08-03 when the job was written.

Registration mirrors ``app.services.meta.scheduler`` (the seed-side
``noctusai_lib.api.scheduler`` primitive): jobs register at import time via
:func:`configure`; ``start_scheduler`` / ``stop_scheduler`` are already
wired into ``app/lifespan.py``.

── Which orgs does it sync? ────────────────────────────────────────────
Orgs that **already have imóveis rows**, discovered from the table itself.

That is deliberate and it is not the same rule the Meta job uses. Meta
discovers orgs from per-org ``credentials`` rows; Vista has no such row —
``crm_base_url`` / ``crm_api_key`` are process-global env config
(``app/config.py:232-238``), so "orgs with Vista configured" is either
every org or none, and there is nothing per-org to enumerate.

Syncing orgs that already have a catalog makes this a **refresh** job, not
an import job. The first import for a new org stays the manual button — a
deliberate user action, because it is the one that decides an org's
catalog should exist at all. An empty-table org is therefore skipped
rather than silently seeded with another tenant's catalog.

── Why a full pull, nightly ────────────────────────────────────────────
The sync is idempotent by ``(org_id, codigo)`` and takes 4-6 minutes for
the ~1919-imóvel catalog at concurrency 4-8 (measured, roadmap P2.3).
Vista's ``listar`` exposes ``DataAtualizacao`` but *not* a reliable
"changed since" filter, so an incremental pull would have to fetch every
listing row anyway to discover what moved — the saving would be only the
``detalhes`` leg, at the cost of missing any imóvel whose detalhes changed
without its date advancing. 00:05 is outside business hours; the full pull
is the honest option.

``with_detalhes=True`` is not optional here: ``caracteristicas`` and
``finalidades`` are detalhes-only on the wire, so a listar-only nightly
run would blank the amenity set on every row it touched.

Roadmap: ``project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client
from app.services.imoveis_service import build_sync_service

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_JOB_NAME = "imoveis_vista_sync_daily"
# 00:05 America/Sao_Paulo — the seed scheduler is constructed with that
# timezone (`noctusai_lib/api/scheduler.py:87`), so this is local time, not
# UTC. Five past midnight rather than midnight itself: it keeps this job
# off the same tick as any other `0 0 * * *` work.
_JOB_CRON = "5 0 * * *"


def _orgs_with_catalog(admin: Any) -> list[str]:
    """Distinct ``org_id`` already holding imóveis rows.

    Paginated explicitly: PostgREST caps an unbounded select at 1000 rows,
    and this table holds ~1919 per org — an uncapped read would silently
    see only the first page and, with one org, still look correct. The same
    trap `imoveis_service._select_all` documents.
    """
    orgs: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        resp = (
            admin
            .schema(_SCHEMA)
            .table("imoveis")
            .select("org_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        orgs.update(row["org_id"] for row in rows if row.get("org_id"))
        if len(rows) < page_size:
            break
        offset += page_size
    return sorted(orgs)


def _build_adapter() -> Any:
    """Construct the Vista adapter, or return None if Vista is unwired.

    Imported inside the function, not at module scope: the adapter raises
    when Vista is unconfigured, and an import-time raise would take the
    whole app down on a deploy where Vista simply isn't wired yet. Same
    reasoning as `imoveis_router.sync_imoveis`.
    """
    from noctusai_lib.integrations.vista import (
        VistaNotConfigured,
        VistaRESTAdapter,
    )

    try:
        return VistaRESTAdapter(
            base_url=settings.crm_base_url,
            api_key=settings.crm_api_key,
        )
    except VistaNotConfigured as exc:
        logger.warning(
            "%s: Vista not configured (%s) — skipping this run. "
            "The manual sync button reports the same condition as a 503.",
            _JOB_NAME, exc,
        )
        return None


async def daily_imoveis_sync_job() -> None:
    """Refresh every org's Vista catalog.

    One org failing must not cost the others their refresh, so each org is
    isolated. Nothing re-raises: an escaping exception would be swallowed
    by APScheduler into a bare traceback with no org context, which is the
    silent-error shape this logs its way out of.
    """
    admin = get_admin_client()
    if admin is None:
        logger.error("%s: no admin client — skipping this run.", _JOB_NAME)
        return

    adapter = _build_adapter()
    if adapter is None:
        return

    try:
        org_ids = await asyncio.to_thread(_orgs_with_catalog, admin)
    except Exception as exc:
        logger.error(
            "%s: org discovery failed: %s", _JOB_NAME, exc, exc_info=True,
        )
        return

    if not org_ids:
        logger.info(
            "%s: no org has an imóveis catalog yet — nothing to refresh. "
            "The first import is the manual sync button, by design.",
            _JOB_NAME,
        )
        return

    for org_id in org_ids:
        try:
            report = await build_sync_service(admin, adapter).sync(
                UUID(org_id), with_detalhes=True
            )
        except Exception as exc:
            logger.error(
                "%s: org=%s failed: %s", _JOB_NAME, org_id, exc, exc_info=True,
            )
            continue

        # `complete=False` means the pull finished but dropped pages or
        # detalhes. That is a degraded success, not a failure, and it must
        # not look like a clean run in the log.
        log = logger.info if report.complete else logger.warning
        log(
            "%s: org=%s upserted=%d detalhes=%d page_failures=%d "
            "detalhes_failed=%d complete=%s duration=%.1fs",
            _JOB_NAME, org_id, report.upserted, report.detalhes_fetched,
            len(report.page_failures), len(report.detalhes_failed),
            report.complete, report.duration_seconds,
        )


def configure() -> None:
    """Register the daily catalog refresh on the seed scheduler.

    Idempotent (``register`` replaces-existing); called from
    ``app.main._register_media_wiring`` at import time, before any
    ``start_scheduler()`` fires.
    """
    seed_scheduler.register(_JOB_NAME, daily_imoveis_sync_job, cron=_JOB_CRON)
    logger.info(
        "imoveis vista sync scheduler configured: daily at 00:05 "
        "America/Sao_Paulo"
    )


__all__ = ["configure", "daily_imoveis_sync_job"]
