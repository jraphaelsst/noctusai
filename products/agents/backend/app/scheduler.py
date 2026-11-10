"""Scheduled jobs for Agentes (seed `noctusai_lib.api.scheduler` primitive).

`credential_maintenance` — daily 09:00 America/Sao_Paulo: 30-day expiry
notifications for the product tokens this control plane holds, plus pruning
of retired §D approval keys (contract D1's deferred "alert 30 days before
any token expires"). Registration is import-time; the job only FIRES in a
container carrying `NOCTUS_SCHEDULERS_ENABLED` (compose `x-prod-env`).
"""
from __future__ import annotations

import asyncio
import logging

from noctusai_lib.api.scheduler import register

from app.config import settings

logger = logging.getLogger(__name__)

JOB_NAME = "agents_credential_maintenance"
CHANNEL_PURGE_JOB_NAME = "agents_channel_retention_purge"
INATIVIDADE_JOB_NAME = "agents_thread_inatividade"


async def credential_maintenance_job() -> None:
    from app.credentials import build_credential_service
    from app.credentials.alerts import get_notification_sink, run_credential_maintenance

    # The body is synchronous IO (Supabase client) — keep it off the loop.
    await asyncio.to_thread(
        run_credential_maintenance, build_credential_service(settings), get_notification_sink()
    )


async def channel_retention_purge_job() -> None:
    """LGPD (Lais contract §10.1 M5): erase channel conversations idle for
    ``channel_retention_days`` (180) — messages, contact, idempotency rows."""
    from app.channels.retention import get_channel_retention, purge_expired

    # One SQL transaction of synchronous IO — keep it off the loop.
    await asyncio.to_thread(
        purge_expired, get_channel_retention(settings),
        retention_days=settings.channel_retention_days,
    )


async def thread_inatividade_job() -> None:
    """Every minute: close the participants whose inactivity window (an open emergency) elapsed. The close is one
    atomic compare-and-set per participant, so a second replica / a re-run writes no second event."""
    from app.channels.thread_service import encerrar_inativos
    from app.stores.threads import get_thread_store

    await asyncio.to_thread(encerrar_inativos, get_thread_store(settings))


def configure() -> None:
    # Generous grace: a restart spanning 09:00 should still run today.
    register(JOB_NAME, credential_maintenance_job, cron="0 9 * * *", misfire_grace_time=6 * 3600)
    register(
        CHANNEL_PURGE_JOB_NAME, channel_retention_purge_job, cron="30 3 * * *",
        misfire_grace_time=6 * 3600,
    )
    register(INATIVIDADE_JOB_NAME, thread_inatividade_job, cron="* * * * *", misfire_grace_time=60)
