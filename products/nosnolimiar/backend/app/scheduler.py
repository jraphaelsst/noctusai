"""Nós no Limiar background jobs -- on the seed scheduler primitive (`noctusai_lib.api.scheduler`).

Jobs:
  * ``nosnolimiar_sessoes_materializar`` -- daily, 00:10 America/Sao_Paulo (and once at startup, as the catch-up).
    Rolls every patient's weekly slot forward so that the session of NEXT week's slot always exists: a slot set on a
    Tuesday for Monday 14h has next Monday's session at once, and from then on each Monday the following Monday's is
    created (one week ahead). Idempotent (the `(schedule_id, starts_at)` unique guard + the slot's cursor) and it
    catches up after a missed day: every occurrence still in the future up to the horizon is created, none in the past.
    One org failing never costs the others their sessions (logged at ERROR with the org, then the sweep continues).

The clients organ also tops the horizon up lazily on every read (agenda, patient, sessions), so the job guarantees the
sessions exist even when nobody opens the app; it does not replace the read path.
"""
from __future__ import annotations

import asyncio
import logging

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.domain.clients import ClientsService, build_clients_store
from noctusai_lib.domain.finance import FinanceConfig, NoopFinanceBooking, SupabaseFinanceBooking

from app.crm import CLIENTS_CONFIG
from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)

SESSIONS_JOB = "nosnolimiar_sessoes_materializar"
_SCHEMA = "nosnolimiar"


def build_service() -> ClientsService:
    """The clients service over the live tables (the job's collaborators; tests build their own over a Fake store)."""
    admin = get_admin_client()
    booking = SupabaseFinanceBooking(admin, FinanceConfig(schema=_SCHEMA)) if CLIENTS_CONFIG.finance_enabled else NoopFinanceBooking()
    return ClientsService(build_clients_store(admin, CLIENTS_CONFIG), CLIENTS_CONFIG, booking)


def materialize_sessions(service: ClientsService | None = None, *, motivo: str = "agendado") -> dict[str, int]:
    """One sweep: `{org_id: sessions created}`. A failing org is logged (ERROR, with the org) and the sweep continues."""
    svc = service or build_service()

    def _failed(org_id: str, exc: Exception) -> None:
        logger.error("%s [%s]: org=%s failed: %s", SESSIONS_JOB, motivo, org_id, exc, exc_info=exc)

    made = svc.materialize_due(on_error=_failed)
    if made:
        logger.info("%s [%s]: created %s", SESSIONS_JOB, motivo, made)
    return made


async def job_materialize_sessions() -> None:
    await asyncio.to_thread(materialize_sessions)


async def startup() -> None:
    """Lifespan startup: start the scheduler, then the catch-up sweep (a deploy or a down day must not lose a slot)."""
    seed_scheduler.start_scheduler()
    await asyncio.to_thread(materialize_sessions, None, motivo="startup")


stop_scheduler = seed_scheduler.stop_scheduler


def configure() -> None:
    """Register the jobs (import time, before `start_scheduler()` fires in the lifespan)."""
    # A deploy that straddles 00:10 still runs it: an hour of misfire grace, then the startup catch-up covers the rest.
    seed_scheduler.register(SESSIONS_JOB, job_materialize_sessions, cron="10 0 * * *", misfire_grace_time=3600)


__all__ = [
    "SESSIONS_JOB", "build_service", "configure", "job_materialize_sessions", "materialize_sessions", "startup", "stop_scheduler",
]
