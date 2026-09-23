"""IgIg background jobs — on the seed scheduler primitive.

``noctusai_lib.api.scheduler`` owns the AsyncIOScheduler, the misfire policy
and the ``NOCTUS_SCHEDULERS_ENABLED`` guard (only a deployed container runs
jobs). This module only REGISTERS igig's jobs; ``app/main.py`` calls
:func:`configure` and wires ``start_scheduler`` / ``stop_scheduler`` into the
lifespan.

Jobs:
  * ``igig_gmail_watch_renovar`` — daily 06:15 (São Paulo). A Gmail
    ``users.watch`` lapses after ≤7 days and then SILENTLY stops delivering;
    Google recommends renewing daily (KB § INTEGRATIONS/google.md § 5a).
"""
from __future__ import annotations

import logging

from noctusai_lib.api import scheduler as seed_scheduler

from app import database
from app.email_deps import current_email_settings, real_gmail_client
from app.services import orcamento_email
from app.store import get_repositorios_admin

logger = logging.getLogger(__name__)

__all__ = ["configure", "renovar_gmail_watches_job", "start_scheduler", "stop_scheduler"]

start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler


async def renovar_gmail_watches_job() -> None:
    try:
        await orcamento_email.renovar_watches(
            database._db.get_admin_client(),
            get_repositorios_admin(),
            gmail_factory=real_gmail_client,
            settings=current_email_settings(),
        )
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job igig_gmail_watch_renovar falhou")


def configure() -> None:
    seed_scheduler.register(
        "igig_gmail_watch_renovar", renovar_gmail_watches_job,
        cron="15 6 * * *", misfire_grace_time=3600,
    )
