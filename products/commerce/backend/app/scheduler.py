"""Background work for Commerce: the seed scheduler jobs + the invoice jobs worker.

`configure()` registers at import (called from `app/main.py`); `start_background` / `stop_background`
are the lifespan hooks. NOTHING fires unless the process carries `NOCTUS_SCHEDULERS_ENABLED` (set only in
the deployed compose) -- a laptop on the production `.env` never sweeps production orders or issues notes.

Jobs (`register`, `noctusai_lib.api.scheduler`):

* `commerce_expire_orders` / `commerce_expiry_reminders` / `commerce_dispute_poll` / `commerce_fiscal_purge`
  -- `register_commerce_jobs` (the dispute poll is REQUIRED: Asaas has no "dispute lost" webhook, W3).
* `finance_gateway_sync` -- `register_gateway_sync` (6-hourly statement pull per gateway account).
* `finance_generate_recurrences` -- daily; books the due recurring entries.
* `contracts_generate_billing` -- daily (the contracts organ's `register_jobs`); books each contract's receivables into finance.

Worker: `commerce.invoice.issue` / `commerce.invoice.cancel` jobs (`make_invoice_job_handlers`) drained by a
seed `Worker` with `INVOICE_RETRY_POLICY` (the worker's policy is the retry-vs-dead-letter authority).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from noctusai_lib.api.scheduler import register, schedulers_enabled, start_scheduler, stop_scheduler
from noctusai_lib.domain.commerce import register_commerce_jobs
from noctusai_lib.domain.commerce.invoices import CANCEL_JOB, INVOICE_RETRY_POLICY, ISSUE_JOB, make_invoice_job_handlers
from noctusai_lib.domain.finance import register_gateway_sync
from noctusai_lib.domain.finance.recurrences import generate_due_recurrences
from noctusai_lib.domain.jobs import Worker

from app import commerce_deps as deps
from app.commerce import CFG, FINANCE_CFG
from app.dependencies import get_admin_client
from app.routers.commerce_routers import contracts_organ

logger = logging.getLogger(__name__)

RECURRENCES_JOB = "finance_generate_recurrences"
INVOICE_WORKER_ID = "commerce-invoices"

_stop: Optional[asyncio.Event] = None
_task: Optional[asyncio.Task] = None


async def finance_generate_recurrences_job() -> Optional[dict]:
    """Book every due recurrence (idempotent per occurrence). Logged, never fatal to the scheduler."""
    try:
        summary = await asyncio.to_thread(lambda: generate_due_recurrences(get_admin_client(), FINANCE_CFG))
    except Exception:  # noqa: BLE001 -- logged; the scheduler must keep running
        logger.error("finance recurrences job failed", exc_info=True)
        return None
    logger.info("finance recurrences: %s", summary)
    return summary


def configure() -> tuple[str, ...]:
    """Register every Commerce job (idempotent -- re-registering replaces). Returns the job names."""
    names = register_commerce_jobs(
        register,
        cfg=CFG,
        get_db=get_admin_client,
        get_deps=deps.get_money_deps,
        get_link_secret=deps.get_link_secret,
    )
    gateway_sync = register_gateway_sync(FINANCE_CFG, get_db=get_admin_client, operations_for=deps.charge_operations_for)
    register(RECURRENCES_JOB, finance_generate_recurrences_job, cron="10 3 * * *")
    contracts_billing = contracts_organ.register_jobs()
    return (*names, gateway_sync, RECURRENCES_JOB, contracts_billing)


def build_invoice_worker() -> Worker:
    handlers = make_invoice_job_handlers(
        CFG,
        get_db=get_admin_client,
        make_provider=deps.make_provider,
        get_storage=deps.get_storage,
        get_jobs=deps.get_jobs,
        get_mailer=deps.get_email_sender,
        retry_policy=INVOICE_RETRY_POLICY,
    )
    assert set(handlers) == {ISSUE_JOB, CANCEL_JOB}, sorted(handlers)
    return Worker(deps.get_jobs(), worker_id=INVOICE_WORKER_ID, handlers=handlers, retry_policy=INVOICE_RETRY_POLICY)


async def _supervise(worker: Worker, stop: asyncio.Event) -> None:
    """Keep the worker alive: a crash is logged loudly and restarted after a pause; stop wins."""
    while not stop.is_set():
        try:
            await worker.run_forever(stop_event=stop)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- logged, restarted
            logger.error("commerce invoice worker crashed; restarting in 10s", exc_info=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass


async def start_background() -> None:
    """Lifespan startup: the scheduler, then the invoice worker -- both only where schedulers are enabled."""
    global _stop, _task
    start_scheduler()
    if not schedulers_enabled():
        logger.info("commerce invoice worker skipped (schedulers disabled in this process)")
        return
    if _task is not None and not _task.done():
        return
    _stop = asyncio.Event()
    _task = asyncio.ensure_future(_supervise(build_invoice_worker(), _stop))
    logger.info("commerce invoice worker started")


async def stop_background() -> None:
    global _stop, _task
    if _stop is not None:
        _stop.set()
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _stop = _task = None
    stop_scheduler()
