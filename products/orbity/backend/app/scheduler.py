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

Both run their sync DB/HTTP work via ``anyio.to_thread.run_sync`` so the event
loop is never blocked by a WAHA call.
"""
from __future__ import annotations

import logging
from uuid import UUID

import anyio
from noctusai_lib.api import scheduler as seed_scheduler

from app.dependencies import get_admin_client
from app.services.automation_engine import orgs_with_due_work
from app.services.automation_service import AutomationService
from app.services.tasks_service import TasksService, orgs_with_due_routines

logger = logging.getLogger(__name__)

# Re-exported for main.py (lifespan wiring).
start_scheduler = seed_scheduler.start_scheduler
stop_scheduler = seed_scheduler.stop_scheduler

__all__ = [
    "configure", "job_automacao_run_due", "job_rotinas_run_due",
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


def configure() -> None:
    seed_scheduler.register("orbity_automacao_run_due", job_automacao_run_due, minutes=1)
    seed_scheduler.register("orbity_rotinas_run_due", job_rotinas_run_due, minutes=15)
