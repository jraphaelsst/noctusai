"""Edição de Fotos scheduled jobs — daily model notes + PTAX backfill.

Same shape as `app/services/imoveis_sync_scheduler.py` (the product's one
scheduler idiom): seed APScheduler cron in America/Sao_Paulo, a long misfire
grace, a startup catch-up, and the `sync_lease` cross-process lock. The seed
scheduler itself only starts where `NOCTUS_SCHEDULERS_ENABLED` is set, and
the catch-up checks the same guard.

What a slot DOES here is small: it ENQUEUES an engine job
(`fotos.notas_modelos` / `fotos.fx_backfill`). The worker runs it — so both
wait while "processamento ativo" is off, exactly like every other paid call.

Why the catch-up needs no ledger: the notes job is dedupe-keyed on the
slot's São Paulo DATE (`enqueue_model_notes(slot=...)`), so the cron path and
any number of startup catch-ups for the same slot collapse to one job, and
the handler skips a model already noted since the slot. "Was the slot
missed?" is answered by the jobs table itself.

- Notes: `5 0 * * *` (plan §1: rewritten daily at 00:05).
- PTAX backfill: `30 13,18 * * *` — BCB publishes the closing PTAX in the
  early afternoon; the 18:30 run catches a late bulletin. One job per run
  (`dedupe_suffix` = the hour).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.domain.photo_editing import enqueue_fx_backfill, enqueue_model_notes

from app.config import settings
from app.dependencies import get_admin_client
from app.modules.edicao_fotos.services import ports as ports_service
from app.services import sync_lease

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Sao_Paulo")
NOTES_JOB = "edicao_fotos_notas_modelos_diario"
NOTES_CRON = "5 0 * * *"
NOTES_SLOT = time(0, 5)
FX_JOB = "edicao_fotos_fx_backfill"
FX_CRON = "30 13,18 * * *"
MISFIRE_GRACE = 3600
#: Enqueueing takes milliseconds; a short lease is plenty.
LEASE_NAME = "edicao_fotos_agendador"
LEASE_TTL_SECONDS = 120


def last_expected_slot(now: datetime) -> datetime:
    """The most recent 00:05 America/Sao_Paulo at or before ``now``."""
    local = now.astimezone(TZ)
    slot = local.replace(hour=NOTES_SLOT.hour, minute=NOTES_SLOT.minute, second=0, microsecond=0)
    return slot if local >= slot else slot - timedelta(days=1)


def _now() -> datetime:
    return datetime.now(tz=TZ)


async def _with_ports_and_lease(
    job: str,
    motivo: str,
    action: Any,
    *,
    ports_factory: Any = None,
    admin_factory: Any = None,
    lease_fn: Any = None,
) -> Optional[str]:
    """Run ``action(ports)`` under the lease. Returns the enqueued job id,
    or ``None`` when this process must not / could not run it (logged)."""
    try:
        ports = (ports_factory or ports_service.get_ports)(settings)
    except ports_service.EdicaoFotosUnavailable as exc:
        logger.warning("%s [%s]: motor indisponível — %s", job, motivo, exc)
        return None
    admin = (admin_factory or get_admin_client)()
    with (lease_fn or sync_lease.lease)(admin, LEASE_NAME, ttl_seconds=LEASE_TTL_SECONDS) as got:
        if not got:
            logger.info("%s [%s]: outro processo tem o lease — pulando.", job, motivo)
            return None
        enqueued = await action(ports)
    logger.info("%s [%s]: job %s enfileirado (%s).", job, motivo, enqueued.id, enqueued.status.value)
    return enqueued.id


async def daily_notes_job(*, now: Optional[datetime] = None, **seams: Any) -> Optional[str]:
    slot = last_expected_slot(now or _now())
    return await _with_ports_and_lease(
        NOTES_JOB, "cron", lambda ports: enqueue_model_notes(ports, slot=slot), **seams
    )


async def fx_backfill_job(*, now: Optional[datetime] = None, **seams: Any) -> Optional[str]:
    local = (now or _now()).astimezone(TZ)
    return await _with_ports_and_lease(
        FX_JOB,
        "cron",
        lambda ports: enqueue_fx_backfill(ports, local.date(), dedupe_suffix=f"{local.hour:02d}"),
        **seams,
    )


async def catch_up(*, now: Optional[datetime] = None, **seams: Any) -> Optional[str]:
    """Startup: make sure the last notes slot has its job (dedupe makes this
    a no-op when the cron already ran)."""
    if not seed_scheduler.schedulers_enabled():
        logger.info("%s: catch-up pulado (processo sem %s).", NOTES_JOB, seed_scheduler.SCHEDULERS_ENABLED_ENV)
        return None
    slot = last_expected_slot(now or _now())
    return await _with_ports_and_lease(
        NOTES_JOB, "catch-up", lambda ports: enqueue_model_notes(ports, slot=slot), **seams
    )


_BACKGROUND: set[asyncio.Task] = set()


def schedule_catch_up() -> Optional[asyncio.Task]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("%s: schedule_catch_up fora de um event loop — catch-up NÃO iniciado.", NOTES_JOB)
        return None
    task = loop.create_task(catch_up())
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return task


def configure() -> None:
    """Register both jobs on the seed scheduler (idempotent; called from
    the module's `register()`)."""
    seed_scheduler.register(NOTES_JOB, daily_notes_job, cron=NOTES_CRON, misfire_grace_time=MISFIRE_GRACE)
    seed_scheduler.register(FX_JOB, fx_backfill_job, cron=FX_CRON, misfire_grace_time=MISFIRE_GRACE)
    logger.info(
        "edicao_fotos scheduler configurado: notas %s, PTAX %s (America/Sao_Paulo)", NOTES_CRON, FX_CRON
    )


__all__ = [
    "FX_CRON",
    "FX_JOB",
    "NOTES_CRON",
    "NOTES_JOB",
    "catch_up",
    "configure",
    "daily_notes_job",
    "fx_backfill_job",
    "last_expected_slot",
    "schedule_catch_up",
]
