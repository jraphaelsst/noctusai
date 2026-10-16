"""Orbity background jobs — on the seed scheduler primitive.

`noctusai_lib.api.scheduler` owns the AsyncIOScheduler, the misfire policy and
the ``NOCTUS_SCHEDULERS_ENABLED`` guard (only a deployed container runs jobs;
a laptop run registers the jobs but never fires them). This module only
REGISTERS Orbity's jobs; ``app/main.py`` calls :func:`configure` and wires
``start_scheduler`` / ``stop_scheduler`` into the lifespan (igig pattern).

Jobs:
  * ``orbity_automacao_run_due`` — every minute. Finds the orgs with a due
    (or stale-claimed) ``automation_pending_actions`` row and drains each:
    claim -> execute (real WhatsApp send / CRM action) -> advance the flow.
    Per-org failure isolation: one org's error never stops the sweep.
  * ``orbity_rotinas_run_due`` — every 15 minutes. Spawns tasks from every
    active routine due today or earlier, org by org
    (``TasksService.run_due_routines``).
  * ``contracts_generate_billing`` — daily (the seed contracts organ's job, via
    ``contracts_organ.register_jobs``). Renews/expires lapsed contracts and books
    each active contract's monthly receivable (idempotent per contract + cycle)
    through ``OrbityContractsBilling``, which also records the gateway state.
  * ``finance_billing_reminders`` — daily 12:00 America/Sao_Paulo (the seed reminders organ's job, via
    ``reminders_organ.register_jobs``). WhatsApp dunning for the orgs that turned reminders on; dedup-first ledger.
  * ``orbity_billing_process`` — every 2 minutes. Claims queued gateway charges
    (``billing_reserve_charges``: SKIP LOCKED + recovery of rows a crashed worker
    left mid-processing), creates the Asaas charge with its idempotency
    reference, retries transient failures with backoff, then cancels at the
    gateway the charges whose receivable was cancelled.
  * ``orbity_content_claims_sweep`` — every 5 minutes. Releases the content-plan items a crashed "Criar tarefas"
    left in ``task_pending`` (no task linked, untouched for 15 minutes) back to ``planned``.
  * ``finance_generate_recurrences`` — daily. Books the due recurring finance
    entries (the seed finance organ's ``generate_due_recurrences``).

All run their sync DB/HTTP work via ``anyio.to_thread.run_sync`` /
``asyncio.to_thread`` so the event loop is never blocked by a WAHA/gateway call.
"""
from __future__ import annotations

import logging
from uuid import UUID

import anyio
from noctusai_lib.api import scheduler as seed_scheduler

from noctusai_lib.domain.finance.recurrences import generate_due_recurrences

from app import billing
from app.dependencies import get_admin_client
from app.services import billing_charges
from app.services.content_plans_service import release_stale_claims
from app.services.automation_engine import orgs_with_due_work
from app.services.automation_service import AutomationService
from app.services.tasks_service import TasksService, orgs_with_due_routines

logger = logging.getLogger(__name__)

# Re-exported for main.py (lifespan wiring).
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler

BILLING_PROCESS_JOB = "orbity_billing_process"
RECURRENCES_JOB = "finance_generate_recurrences"
CONTENT_CLAIMS_JOB = "orbity_content_claims_sweep"

__all__ = [
    "configure", "job_automacao_run_due", "job_billing_process", "job_content_claims_sweep", "job_finance_recurrences",
    "job_rotinas_run_due",
    "start_scheduler", "stop_scheduler",
]


def _drain_org(admin, org_id: str) -> dict[str, int]:
    return AutomationService(admin, org_id=UUID(org_id)).run_due()


async def job_automacao_run_due() -> None:
    try:
        admin = get_admin_client()
        orgs = await anyio.to_thread.run_sync(lambda: orgs_with_due_work(admin))
        for org_id in orgs:
            try:
                counts = await anyio.to_thread.run_sync(lambda o=org_id: _drain_org(admin, o))
                if counts.get("processed"):
                    logger.info("job orbity_automacao_run_due org=%s: %s", org_id, counts)
            except Exception:  # noqa: BLE001 — one org's failure must not stop the sweep
                logger.exception("job orbity_automacao_run_due falhou org=%s", org_id)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job orbity_automacao_run_due falhou")


async def job_rotinas_run_due() -> None:
    try:
        admin = get_admin_client()
        orgs = await anyio.to_thread.run_sync(lambda: orgs_with_due_routines(admin))
        for org_id in orgs:
            try:
                spawned = await anyio.to_thread.run_sync(
                    lambda o=org_id: TasksService(admin, org_id=UUID(o)).run_due_routines()
                )
                if spawned:
                    logger.info("job orbity_rotinas_run_due org=%s: %d tarefa(s)", org_id, len(spawned))
            except Exception:  # noqa: BLE001 — one org's failure must not stop the sweep
                logger.exception("job orbity_rotinas_run_due falhou org=%s", org_id)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job orbity_rotinas_run_due falhou")


async def job_billing_process() -> None:
    try:
        admin = get_admin_client()
        if not await anyio.to_thread.run_sync(lambda: billing_charges.has_billing_work(admin)):
            return
        counts = await anyio.to_thread.run_sync(lambda: billing_charges.process_charges(admin, billing.get_gateway()))
        if counts.get("reserved") or counts.get("gateway_cancel", {}).get("done"):
            logger.info("job %s: %s", BILLING_PROCESS_JOB, counts)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job %s falhou", BILLING_PROCESS_JOB)


async def job_finance_recurrences() -> None:
    try:
        admin = get_admin_client()
        summary = await anyio.to_thread.run_sync(lambda: generate_due_recurrences(admin, billing.FINANCE_CFG))
        logger.info("job %s: %s", RECURRENCES_JOB, summary)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job %s falhou", RECURRENCES_JOB)


async def job_content_claims_sweep() -> None:
    try:
        admin = get_admin_client()
        released = await anyio.to_thread.run_sync(lambda: release_stale_claims(admin))
        if released:
            logger.info("job %s: %d item(ns) liberado(s)", CONTENT_CLAIMS_JOB, released)
    except Exception:  # noqa: BLE001 — a job failure must be loud, not fatal to the loop
        logger.exception("job %s falhou", CONTENT_CLAIMS_JOB)


def configure() -> None:
    seed_scheduler.register("orbity_automacao_run_due", job_automacao_run_due, minutes=1)
    seed_scheduler.register("orbity_rotinas_run_due", job_rotinas_run_due, minutes=15)
    seed_scheduler.register(BILLING_PROCESS_JOB, job_billing_process, minutes=2)
    seed_scheduler.register(RECURRENCES_JOB, job_finance_recurrences, cron="10 3 * * *")
    seed_scheduler.register(CONTENT_CLAIMS_JOB, job_content_claims_sweep, minutes=5)
    # The seed contracts organ's own daily job (registered through its mounted organ so it books through the host's billing).
    from app.routers.organs import contracts_organ, reminders_organ

    contracts_organ.register_jobs()
    reminders_organ.register_jobs()  # `finance_billing_reminders`, daily 12:00 America/Sao_Paulo, reminders ON per org only
