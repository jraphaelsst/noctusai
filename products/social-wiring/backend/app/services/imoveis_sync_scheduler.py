"""Vista imóveis refresh — every 2 hours (configurable), for every org with a Vista credential; plus startup catch-up.

Keeps ``social_wiring.imoveis`` current. Before this existed the mirror only moved when a human pressed
"Sincronizar com o Vista"; then a nightly 00:05 pull; since 2026-11-03 an INTERVAL job (default 7200 s,
``settings.imoveis_sync_intervalo_s``), because Vista's ``/imoveis/listar`` went silent (2026-10-23) and the mirror is
now also refreshed code by code (see ``imoveis_atualizacao_service``).

── What a run does (per org, via ``imoveis_atualizacao_service.executar``) ──────────────────────
``modo="auto"``: try ``listar``; if it is empty while the mirror has rows, fall back to the per-code refresh
(``ImovelSyncService.sync_detalhes``) + discovery of new codes, and raise ONE in-app notice a day to the org admins.
Tiered cadence: every run refreshes the *vitrine* (public listings still listed) + discovery; once per
``settings.imoveis_sync_resto_intervalo_s`` (default a day) the run also sweeps the rest (sold / suspended / hidden /
removed) so a come-back is noticed. Each run is persisted (``imoveis_sync_execucoes``, migration 316).

── The guarantee: three layers, because one is not enough ──────────────────────────────────────
APScheduler holds its schedule in memory; a container that is down at a slot does not "queue" it. (1) the interval
trigger; (2) misfire grace of one hour; (3) startup catch-up (:func:`catch_up_if_overdue`, from ``app/lifespan.py``):
it asks the DATA ("is any org's newest ``sincronizado_em`` older than one interval?") and runs immediately if so.

── Orgs: those with a Vista credential in the database ─────────────────────────────────────────
The credential is per org (``social_wiring.credentials``, provider ``vista``; ``vista_credenciais``). An org with no
record is not a candidate; there is no environment key to fall back to.

── Concurrency ─────────────────────────────────────────────────────────────────────────────────
``_sync_lock``: in-process, the interval path vs the startup catch-up. The per-org DB lease
``imoveis_vista_sync:<org>`` (inside ``executar``): a second PROCESS, and a manual "Atualizar agora" during a scheduled
run. ``start_scheduler`` additionally refuses to run outside a deployed container (``NOCTUS_SCHEDULERS_ENABLED``).

Roadmap: ``project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.api import scheduler as seed_scheduler

from app.config import settings
from app.dependencies import get_admin_client, get_core_client
from noctusai_lib.integrations.credential_resolvers import VISTA_PROVIDER

from app.services import imoveis_atualizacao_service

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_JOB_NAME = "imoveis_vista_refresh"
_TZ = ZoneInfo("America/Sao_Paulo")
# One hour, against the seed default of 30 seconds: running late is fine, skipping a slot is not.
_MISFIRE_GRACE = 3600

# Serialises the cron path against the startup catch-up. Module-level is
# safe on 3.11+ — asyncio.Lock no longer binds a loop at construction.
_sync_lock = asyncio.Lock()


# ─── Overdue arithmetic ─────────────────────────────────────────────────


def _intervalo() -> timedelta:
    return timedelta(seconds=max(60, int(settings.imoveis_sync_intervalo_s)))


def _last_expected_slot(now: datetime) -> datetime:
    """The instant an org's data should have been refreshed since: one interval ago."""
    return now - _intervalo()


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


def _orgs_with_credential(admin: Any) -> list[str]:
    """Distinct ``org_id`` holding a Vista credential record (provider ``vista``), paged past PostgREST's 1000-row cap.

    The candidates of the refresh: no record, no refresh (and no environment key to fall back to)."""
    orgs: set[str] = set()
    offset = 0
    while True:
        rows = (
            admin.schema(_SCHEMA).table("credentials").select("org_id").eq("provider", VISTA_PROVIDER)
            .order("org_id").range(offset, offset + 999).execute().data or []
        )
        orgs.update(str(r["org_id"]) for r in rows if r.get("org_id"))
        if len(rows) < 1000:
            return sorted(orgs)
        offset += 1000


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


def _build_adapter(org_id: str) -> Any:
    """THIS org's Vista adapter (its own encrypted credential), or None when the org has none.

    Per org on purpose: the credential is per org (`vista_credenciais`), there is no environment key to fall back to,
    and an org without a record is skipped (logged) without costing the others their refresh."""
    from app.services import vista_credenciais

    return vista_credenciais.adapter_ou_none(org_id)


# ─── The shared runner ──────────────────────────────────────────────────


async def _sync_orgs(
    admin: Any,
    adapter_factory: Any,
    org_ids: list[str],
    *,
    motivo: str,
    sync_service_factory: Any = None,
    lease_fn: Any = None,
    core_factory: Any = None,
) -> None:
    """Refresh each org, isolating failures.

    `sync_service_factory` / `lease_fn` / `core_factory` are Class-B kwarg seams (default `None` → the real thing), so a
    test substitutes a collaborator by PASSING it rather than by reassigning it on this module.

    One org failing must not cost the others their refresh, so each is wrapped. Nothing re-raises: an escaping
    exception would reach APScheduler as a bare traceback with no org context — the silent-error shape this logs its
    way out of."""
    core = None
    for org_id in org_ids:
        adapter = adapter_factory(org_id)
        if adapter is None:
            logger.warning(
                "%s [%s]: org=%s has no Vista credential (Settings > Chaves API > Vista CRM) — skipped.",
                _JOB_NAME, motivo, org_id,
            )
            continue
        try:
            if core is None:
                core = (core_factory or get_core_client)()
            escopo = await asyncio.to_thread(
                imoveis_atualizacao_service.escopo_do_agendamento, admin, org_id, int(settings.imoveis_sync_resto_intervalo_s),
            )
            resultado = await imoveis_atualizacao_service.executar(
                admin, adapter, org_id, modo="auto", escopo=escopo, origem="agendado", core=core,
                sync_factory=sync_service_factory, lease_fn=lease_fn,
                sonda_max_falhas=int(settings.imoveis_sonda_max_falhas),
            )
        except Exception as exc:
            logger.error("%s [%s]: org=%s failed: %s", _JOB_NAME, motivo, org_id, exc, exc_info=True)
            continue
        # A degraded run must not look like a clean one in the log.
        log = logger.info if resultado.get("status") == "ok" else logger.warning
        log("%s [%s]: org=%s status=%s path=%s", _JOB_NAME, motivo, org_id, resultado.get("status"), resultado.get("caminho"))


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
    core_factory: Any = None,
) -> None:
    """Discover, filter, refresh — under the in-process lock (the cross-process one is per org, inside `executar`).

    Every collaborator arrives through a Class-B kwarg seam defaulting to `None`, resolved to the real thing here."""
    admin = (admin_factory or get_admin_client)()
    if admin is None:
        logger.error("%s [%s]: no admin client — skipping.", _JOB_NAME, motivo)
        return

    adapter_factory = adapter_factory or _build_adapter

    try:
        org_ids = await asyncio.to_thread(discover_fn or _orgs_with_credential, admin)
    except Exception as exc:
        logger.error("%s [%s]: org discovery failed: %s", _JOB_NAME, motivo, exc, exc_info=True)
        return

    if not org_ids:
        logger.info("%s [%s]: no org has a Vista credential — nothing to refresh.", _JOB_NAME, motivo)
        return

    if only_overdue:
        now = datetime.now(tz=_TZ)
        org_ids = await asyncio.to_thread(overdue_fn or _overdue_orgs, admin, org_ids, now)
        if not org_ids:
            logger.info("%s [%s]: every org refreshed since %s — nothing overdue.", _JOB_NAME, motivo, _last_expected_slot(now).isoformat())
            return
        logger.warning(
            "%s [%s]: %d org(s) overdue (older than %s) — refreshing now.",
            _JOB_NAME, motivo, len(org_ids), _last_expected_slot(now).isoformat(),
        )

    async with _sync_lock:
        await _sync_orgs(
            admin, adapter_factory, org_ids, motivo=motivo, sync_service_factory=sync_service_factory,
            lease_fn=lease_fn, core_factory=core_factory,
        )


# ─── Entry points ───────────────────────────────────────────────────────


async def imoveis_vista_refresh_job(**seams: Any) -> None:
    """The interval path — refreshes every org with a Vista credential, unconditionally.

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
    """Register the interval refresh on the seed scheduler (``settings.imoveis_sync_intervalo_s``, default 7200 s).

    Idempotent; called from ``app.main._register_media_wiring`` at import
    time, before any ``start_scheduler()`` fires.
    """
    segundos = int(_intervalo().total_seconds())
    seed_scheduler.register(
        _JOB_NAME,
        imoveis_vista_refresh_job,
        seconds=segundos,
        misfire_grace_time=_MISFIRE_GRACE,
    )
    logger.info(
        "imoveis vista refresh scheduler configured: every %ds (misfire grace %ds)", segundos, _MISFIRE_GRACE,
    )


__all__ = [
    "catch_up_if_overdue",
    "configure",
    "imoveis_vista_refresh_job",
    "schedule_catch_up",
]
