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


async def credential_maintenance_job() -> None:
    from app.credentials import build_credential_service
    from app.credentials.alerts import get_notification_sink, run_credential_maintenance

    # The body is synchronous IO (Supabase client) — keep it off the loop.
    await asyncio.to_thread(
        run_credential_maintenance, build_credential_service(settings), get_notification_sink()
    )


def configure() -> None:
    # Generous grace: a restart spanning 09:00 should still run today.
    register(JOB_NAME, credential_maintenance_job, cron="0 9 * * *", misfire_grace_time=6 * 3600)
