"""Background jobs for {{PRODUCT_NAME}}: finance recurrences + contracts billing on the seed scheduler.

`configure()` registers at import (called from `app/main.py`); `start_background` / `stop_background` are the lifespan
hooks. NOTHING fires unless the process carries `NOCTUS_SCHEDULERS_ENABLED` (set only in a deployed compose) -- a laptop
on a real `.env` never books real entries.

* `finance_generate_recurrences` -- daily; books the due recurring entries (all orgs, idempotent per occurrence).
* `contracts_generate_billing` -- daily; registered by the contracts organ itself (`MountedOrgan.register_jobs`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from noctusai_lib.api.scheduler import register, start_scheduler, stop_scheduler
from noctusai_lib.domain.finance.recurrences import generate_due_recurrences

from app.dependencies import get_admin_client
from app.erp_organs import ERP_ORGANS, FINANCE_CFG

logger = logging.getLogger(__name__)

RECURRENCES_JOB = "finance_generate_recurrences"


async def finance_generate_recurrences_job() -> Optional[dict]:
    """Book every due recurrence. Logged, never fatal to the scheduler."""
    try:
        summary = await asyncio.to_thread(lambda: generate_due_recurrences(get_admin_client(), FINANCE_CFG))
    except Exception:  # noqa: BLE001 -- logged; the scheduler must keep running
        logger.error("finance recurrences job failed", exc_info=True)
        return None
    logger.info("finance recurrences: %s", summary)
    return summary


def configure() -> tuple[str, ...]:
    """Register every ERP job (idempotent -- re-registering replaces). Returns the job names."""
    register(RECURRENCES_JOB, finance_generate_recurrences_job, cron="10 3 * * *")
    names = [RECURRENCES_JOB]
    for organ in ERP_ORGANS:
        if organ.register_jobs is not None:
            names.append(organ.register_jobs())
    return tuple(names)


async def start_background() -> None:
    start_scheduler()


async def stop_background() -> None:
    stop_scheduler()
