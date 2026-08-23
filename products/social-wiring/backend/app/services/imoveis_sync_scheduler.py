"""Daily Vista catalog refresh — seed scheduler job + startup catch-up.

Keeps ``social_wiring.imoveis`` current at **00:05 America/Sao_Paulo**.
Before this existed the mirror only moved when a human pressed
"Sincronizar com o Vista" on the Imóveis page, and it had been stale since
2026-08-03.

── The guarantee: three layers, because one is not enough ──────────────
APScheduler holds its schedule in memory. A container that is down at
00:05 does not "queue" the run — the slot passes and the next one is
tomorrow. Three layers close that, each covering what the one above
cannot:

  1. **The cron slot** — ``5 0 * * *``, the normal path.
  2. **Misfire grace, 1 hour** (``_MISFIRE_GRACE``). A deploy or crash-loop
     that resolves within the hour still fires the missed run on startup,
     because APScheduler compares the slot against the grace window.
  3. **Startup catch-up** (:func:`catch_up_if_overdue`, called from
     ``app/lifespan.py``). Covers everything longer: a night-long outage, a
     paused container, a VPS reboot at 00:00 that finishes at 03:00. It
     asks the DATA, not the scheduler — "is any org's newest
     ``sincronizado_em`` older than the last 00:05 that should have run?"
     — and if so runs the sync immediately.

Layer 3 is what makes the refresh guaranteed rather than best-effort:
it is stateless across restarts because the answer lives in the table, so
it cannot itself be lost to a restart.

── Why no run-ledger table ─────────────────────────────────────────────
``max(sincronizado_em)`` per org already answers "when did data last
land", and it is the honest question. A separate ledger would record that
a run was *attempted*; only the rows record that it *worked*. A failed or
half-finished pull leaves ``sincronizado_em`` behind and correctly reads
as still-overdue on the next boot.

── Concurrency: two locks, two different failures ──────────────────────
``_sync_lock`` is an in-process ``asyncio.Lock``. It stops the cron path
and the startup catch-up overlapping inside THIS process — a boot at
00:04 would otherwise run both. It cannot see another process.

``sync_lease`` (migration 069) is a database lease keyed on
``imoveis_vista_sync``. It stops a SECOND PROCESS running the same job.
Two containers after a replica bump are both legitimately authorised, and
nothing in the scheduler layer would keep them apart.

Both are needed. Dropping the asyncio lock would mean two coroutines in
one process racing for the same lease and one silently skipping its run;
dropping the lease would mean two containers each doing a full Vista pull
against the same catalog.

Related but NOT a substitute: ``start_scheduler`` refuses to run outside
a deployed container (``NOCTUS_SCHEDULERS_ENABLED``), which closes the
2026-08-22 laptop case at the source. That guard answers "may this
process run jobs at all"; the lease answers "may it run THIS job right
now" — the multi-replica question the guard says nothing about.

Roadmap: ``project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client
from app.services import sync_lease
from app.services.imoveis_service import build_sync_service

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_JOB_NAME = "imoveis_vista_sync_daily"
# 00:05 America/Sao_Paulo. The seed scheduler is constructed with that
# timezone (`noctusai_lib/api/scheduler.py`), so this is local, not UTC.
_JOB_CRON = "5 0 * * *"
_TZ = ZoneInfo("America/Sao_Paulo")
_SLOT = time(0, 5)
# One hour, against the seed default of 30 seconds. For a nightly full
# pull the slot matters more than punctuality: running 40 minutes late is
# entirely fine, skipping a night is not.
_MISFIRE_GRACE = 3600
#: Lease key for the cross-process run lock (migration 069). One name for
#: this job, fleet-wide — the point is that every process contends on the
#: same row.
_LEASE_NAME = "imoveis_vista_sync"

# Serialises the cron path against the startup catch-up. Module-level is
# safe on 3.11+ — asyncio.Lock no longer binds a loop at construction.
_sync_lock = asyncio.Lock()


# ─── Overdue arithmetic ─────────────────────────────────────────────────


def _last_expected_slot(now: datetime) -> datetime:
    """The most recent 00:05 America/Sao_Paulo at or before ``now``.

    Deliberately computed in local time then compared as an instant: DST
    would make a fixed 24h subtraction drift, and Brazil has suspended but
    not abolished it.
    """
    local = now.astimezone(_TZ)
    today_slot = local.replace(
        hour=_SLOT.hour, minute=_SLOT.minute, second=0, microsecond=0,
    )
    if local < today_slot:
        return today_slot - timedelta(days=1)
    return today_slot


def _last_sync_at(admin: Any, org_id: str) -> Optional[datetime]:
    """Newest ``sincronizado_em`` for one org, or None if never synced.

    One indexed row read (`idx_sw_imoveis_org_sincronizado_em`) rather than
    a group-by, which PostgREST does not express directly.
    """
    resp = (
        admin
        .schema(_SCHEMA)
        .table("imoveis")
        .select("sincronizado_em")
        .eq("org_id", org_id)
        .order("sincronizado_em", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows or not rows[0].get("sincronizado_em"):
        return None
    return datetime.fromisoformat(rows[0]["sincronizado_em"])


def _orgs_with_catalog(admin: Any) -> list[str]:
    """Distinct ``org_id`` already holding imóveis rows.

    Paginated explicitly: PostgREST caps an unbounded select at 1000 rows
    and this table holds ~1919 per org — an uncapped read would see only
    the first page and, with a single org, still look correct. The same
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


def _overdue_orgs(admin: Any, org_ids: list[str], now: datetime) -> list[str]:
    """Orgs whose newest row predates the last slot that should have run.

    A lookup failure counts the org as overdue: re-running an idempotent
    sync costs 4-6 minutes, while wrongly skipping it costs a day of
    staleness. Erring toward the recoverable side.
    """
    slot = _last_expected_slot(now)
    overdue: list[str] = []
    for org_id in org_ids:
        try:
            last = _last_sync_at(admin, org_id)
        except Exception as exc:
            logger.warning(
                "%s: could not read last sync for org=%s (%s) — treating as "
                "overdue", _JOB_NAME, org_id, exc,
            )
            overdue.append(org_id)
            continue
        if last is None or last < slot:
            overdue.append(org_id)
    return overdue


# ─── Adapter ────────────────────────────────────────────────────────────


def _build_adapter() -> Any:
    """Construct the Vista adapter, or None when Vista is unwired.

    Imported inside the function: the adapter raises when unconfigured, and
    an import-time raise would take the whole app down on a deploy where
    Vista simply isn't wired yet. Same reasoning as
    `imoveis_router.sync_imoveis`.
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
            "%s: Vista not configured (%s) — skipping. The manual sync "
            "button reports the same condition as a 503.", _JOB_NAME, exc,
        )
        return None


# ─── The shared runner ──────────────────────────────────────────────────


async def _sync_orgs(
    admin: Any,
    adapter: Any,
    org_ids: list[str],
    *,
    motivo: str,
    sync_service_factory: Any = None,
) -> None:
    """Refresh each org, isolating failures.

    `sync_service_factory` is a Class-B kwarg seam (default `None` → the real
    `build_sync_service`), so a test substitutes the collaborator by PASSING it
    rather than by reassigning it on this module.

    One org failing must not cost the others their refresh, so each is
    wrapped. Nothing re-raises: an escaping exception would reach
    APScheduler as a bare traceback with no org context — the silent-error
    shape this logs its way out of.
    """
    for org_id in org_ids:
        try:
            build = sync_service_factory or build_sync_service
            report = await build(admin, adapter).sync(
                UUID(org_id), with_detalhes=True
            )
        except Exception as exc:
            logger.error(
                "%s [%s]: org=%s failed: %s",
                _JOB_NAME, motivo, org_id, exc, exc_info=True,
            )
            continue

        # `complete=False` means the pull finished but dropped pages or
        # detalhes. A degraded success, not a failure — and it must not
        # look like a clean run in the log.
        log = logger.info if report.complete else logger.warning
        log(
            "%s [%s]: org=%s upserted=%d detalhes=%d page_failures=%d "
            "detalhes_failed=%d complete=%s duration=%.1fs",
            _JOB_NAME, motivo, org_id, report.upserted,
            report.detalhes_fetched, len(report.page_failures),
            len(report.detalhes_failed), report.complete,
            report.duration_seconds,
        )


async def _run(
    *,
    motivo: str,
    only_overdue: bool,
    admin_factory: Any = None,
    adapter_factory: Any = None,
    discover_fn: Any = None,
    overdue_fn: Any = None,
    sync_service_factory: Any = None,
    lease_fn: Any = None,
) -> None:
    """Discover, filter, sync — under the lock.

    Every collaborator arrives through a Class-B kwarg seam defaulting to
    `None`, resolved to the real thing here. The tests previously substituted
    all five by `monkeypatch.setattr(sched, ...)` — patching our own module,
    which `check_seed_compliance` flags high-severity for a reason: it takes
    the real wiring out of the code path, so the test proves the fake works and
    says nothing about whether `_run` calls the right things. Same seam shape
    as the clientes backfill job (72bb2c97), for the same finding.
    """
    admin = (admin_factory or get_admin_client)()
    if admin is None:
        logger.error("%s [%s]: no admin client — skipping.", _JOB_NAME, motivo)
        return

    adapter = (adapter_factory or _build_adapter)()
    if adapter is None:
        return

    try:
        org_ids = await asyncio.to_thread(discover_fn or _orgs_with_catalog, admin)
    except Exception as exc:
        logger.error(
            "%s [%s]: org discovery failed: %s",
            _JOB_NAME, motivo, exc, exc_info=True,
        )
        return

    if not org_ids:
        logger.info(
            "%s [%s]: no org has an imóveis catalog yet — nothing to "
            "refresh. The first import is the manual sync button, by "
            "design.", _JOB_NAME, motivo,
        )
        return

    if only_overdue:
        now = datetime.now(tz=_TZ)
        org_ids = await asyncio.to_thread(
            overdue_fn or _overdue_orgs, admin, org_ids, now
        )
        if not org_ids:
            logger.info(
                "%s [%s]: every org synced since %s — nothing overdue.",
                _JOB_NAME, motivo, _last_expected_slot(now).isoformat(),
            )
            return
        logger.warning(
            "%s [%s]: %d org(s) missed the %s slot — catching up now.",
            _JOB_NAME, motivo, len(org_ids),
            _last_expected_slot(now).isoformat(),
        )

    # Two locks, deliberately, because they cover different failures.
    #
    # `_sync_lock` is an in-process asyncio lock: it stops the cron path and
    # the startup catch-up overlapping inside THIS process (a boot at 00:04).
    # It cannot see another process.
    #
    # `sync_lease` is a database lease: it stops a SECOND process running the
    # same job. `start_scheduler` now refuses to run outside a deployed
    # container, which closes the laptop case at the source — but two
    # legitimately-authorised containers after a replica bump would still
    # collide, and that is what this holds against.
    async with _sync_lock:
        with (lease_fn or sync_lease.lease)(admin, _LEASE_NAME) as acquired:
            if not acquired:
                logger.info(
                    "%s [%s]: another process holds the sync lease — "
                    "skipping. Not an error: exactly one run is the point.",
                    _JOB_NAME, motivo,
                )
                return
            await _sync_orgs(
                admin, adapter, org_ids,
                motivo=motivo,
                sync_service_factory=sync_service_factory,
            )


# ─── Entry points ───────────────────────────────────────────────────────


async def daily_imoveis_sync_job(**seams: Any) -> None:
    """The 00:05 cron path — refreshes every org unconditionally.

    `**seams` forwards the `_run` kwarg seams so a test can drive this REAL
    entry point with fake collaborators instead of patching the module.
    """
    await _run(motivo="cron", only_overdue=False, **seams)


async def catch_up_if_overdue(**seams: Any) -> None:
    """Startup path — refreshes only orgs that missed their slot.

    Called from ``app/lifespan.py``. Awaiting a 4-6 minute full pull inside
    lifespan startup would stall the container past its health check, so
    the caller schedules this as a background task rather than awaiting it;
    see :func:`schedule_catch_up`.
    """
    await _run(motivo="catch-up", only_overdue=True, **seams)


def schedule_catch_up() -> Optional[asyncio.Task]:
    """Fire the catch-up as a background task and return immediately.

    Returns the task so a caller (and the tests) can await it; production
    intentionally does not. A reference is returned rather than discarded
    because a bare `create_task` result can be garbage-collected mid-flight.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error(
            "%s: schedule_catch_up called outside an event loop — the "
            "catch-up did NOT start.", _JOB_NAME,
        )
        return None

    task = loop.create_task(catch_up_if_overdue())
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# Strong references to in-flight tasks. Without this the event loop only
# holds a weak reference and a long sync can be collected mid-run.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def configure() -> None:
    """Register the daily refresh on the seed scheduler.

    Idempotent; called from ``app.main._register_media_wiring`` at import
    time, before any ``start_scheduler()`` fires.
    """
    seed_scheduler.register(
        _JOB_NAME,
        daily_imoveis_sync_job,
        cron=_JOB_CRON,
        misfire_grace_time=_MISFIRE_GRACE,
    )
    logger.info(
        "imoveis vista sync scheduler configured: daily at 00:05 "
        "America/Sao_Paulo (misfire grace %ds)", _MISFIRE_GRACE,
    )


__all__ = [
    "catch_up_if_overdue",
    "configure",
    "daily_imoveis_sync_job",
    "schedule_catch_up",
]
