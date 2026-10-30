"""Scheduler registration for the daily reminders job (`finance_billing_reminders`)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from ..config import FinanceConfig
from .service import ReminderPorts, run_reminders_all
from .types import DEFAULT_SEND_HOUR

logger = logging.getLogger(__name__)

JOB_ID = "finance_billing_reminders"
#: a restart spanning the slot still runs it (APScheduler keeps the schedule in memory).
MISFIRE_GRACE_SECONDS = 3600


def register_billing_reminders(
    cfg: FinanceConfig,
    *,
    get_db: Callable[[], Any],
    ports: ReminderPorts,
    hour: int = DEFAULT_SEND_HOUR,
    minute: int = 0,
    scheduler: Any = None,
    job_id: str = JOB_ID,
) -> str:
    """Register the daily job (platform wall clock — `NOCTUS_TIMEZONE`, default America/Sao_Paulo — default 12:00). Call before `start_scheduler()`.

    `get_db` is called PER RUN. The job logs and swallows every exception: a failed tick must neither crash the
    scheduler nor de-register the job -- per-send failures are on the log rows and retried by later ticks.
    """
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("hour must be 0..23 and minute 0..59")
    from noctusai_lib.api import scheduler as seed_scheduler

    async def _job() -> None:
        try:
            summary = await asyncio.to_thread(lambda: run_reminders_all(get_db(), cfg, ports))
            logger.info("finance billing reminders: %s", summary)
        except Exception:
            logger.error("finance billing reminders job %s failed", job_id, exc_info=True)

    (scheduler or seed_scheduler).register(job_id, _job, cron=f"{minute} {hour} * * *", misfire_grace_time=MISFIRE_GRACE_SECONDS)
    return job_id


__all__ = ["JOB_ID", "MISFIRE_GRACE_SECONDS", "register_billing_reminders"]
