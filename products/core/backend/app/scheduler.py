"""Background jobs for the Core product — on the seed scheduler primitive.

Registration happens at import (`configure()` is called from `app/main.py`);
`start_scheduler` / `stop_scheduler` are the seed's own, so NOTHING here
fires unless the process carries `NOCTUS_SCHEDULERS_ENABLED` (set only in
the deployed compose). Before this module moved onto the primitive, Core's
own AsyncIOScheduler started unconditionally — a laptop running Core
against the production `.env` would have swept production webhook rows.

Jobs (America/Sao_Paulo):

* `core_webhook_retention_sweep` — 03:00 daily. LGPD Art. 16 purge of
  expired `webhook_deliveries`.
* `core_audit_log_retention_sweep` — 03:30 daily. 400-day purge of expired
  `audit_logs` rows via the `purge_expired_audit_logs()` RPC (migration
  053) — the only path the append-only trigger allows.
* `core_billing_automations`      — hourly at :15. Trials, period end,
  past_due → grace, grace → expired, reconcile. Each sweep also checks the
  owner's `billing_automations_enabled` switch and does nothing when off.
* `core_ptax_daily`               — 13:30 and 18:30 on weekdays. Stores the
  day's PTAX bulletin and prices every `fx_pending` cost/payment row.
* `core_storage_cost_snapshot`    — 02:30 daily.

Every job body takes an optional context so tests run it on Fakes; errors
are logged (a job must not take the scheduler down), never swallowed.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.api.scheduler import register, start_scheduler, stop_scheduler

from app.config import settings
from app.database import get_admin_client
from app.services import billing_automations, fx_service, storage_cost_service
from app.services.billing_context import BillingContext, build_billing_context
from app.services.webhook_retention_service import run_retention_sweep
from app.services.audit_log_retention_service import (
    run_retention_sweep as run_audit_log_retention_sweep,
)

logger = logging.getLogger(__name__)

WEBHOOK_RETENTION_JOB = "core_webhook_retention_sweep"
AUDIT_LOG_RETENTION_JOB = "core_audit_log_retention_sweep"
BILLING_AUTOMATIONS_JOB = "core_billing_automations"
PTAX_JOB = "core_ptax_daily"
STORAGE_SNAPSHOT_JOB = "core_storage_cost_snapshot"


async def webhook_retention_sweep_job(db: Optional[Any] = None) -> dict:
    try:
        result = run_retention_sweep(db if db is not None else get_admin_client())
    except Exception as exc:  # noqa: BLE001 — logged; the scheduler must keep running
        logger.error("Webhook retention sweep error: %s", exc)
        return {"error": str(exc)}
    if result.get("purged", 0) > 0:
        logger.info("Webhook retention sweep: %d deliveries purged", result["purged"])
    return result


async def audit_log_retention_sweep_job(db: Optional[Any] = None) -> dict:
    try:
        result = run_audit_log_retention_sweep(db if db is not None else get_admin_client())
    except Exception as exc:  # noqa: BLE001 — logged; the scheduler must keep running
        logger.error("Audit log retention sweep error: %s", exc)
        return {"error": str(exc)}
    if result.get("purged", 0) > 0:
        logger.info("Audit log retention sweep: %d audit_logs rows purged", result["purged"])
    return result


async def billing_automations_job(ctx: Optional[BillingContext] = None) -> list[dict]:
    try:
        reports = billing_automations.run_all(ctx or build_billing_context())
    except Exception as exc:  # noqa: BLE001
        logger.error("Billing automations run failed: %s", exc)
        return [{"error": str(exc)}]
    return [r.as_dict() for r in reports]


async def ptax_job(ctx: Optional[BillingContext] = None) -> dict:
    try:
        context = ctx or build_billing_context()
        stored = fx_service.fetch_and_store_ptax(context.db, context.fx, context.clock().date())
        costs = fx_service.resolve_pending_cost_ledger(context.db, context.fx)
        payments = fx_service.resolve_pending_payments(context.db, context.fx)
    except Exception as exc:  # noqa: BLE001
        logger.error("PTAX job failed: %s", exc)
        return {"error": str(exc)}
    result = {
        "stored_quote_date": (stored or {}).get("quote_date"),
        "resolved_cost_rows": costs,
        "resolved_payment_rows": payments,
    }
    logger.info("PTAX job: %s", result)
    return result


async def storage_cost_snapshot_job(ctx: Optional[BillingContext] = None) -> dict:
    try:
        report = storage_cost_service.snapshot_storage_costs(ctx or build_billing_context())
    except Exception as exc:  # noqa: BLE001
        logger.error("Storage cost snapshot failed: %s", exc)
        return {"error": str(exc)}
    logger.info("Storage cost snapshot: %s", vars(report))
    return vars(report)


def configure() -> None:
    """Register every Core job (idempotent — re-registering replaces)."""
    register(
        WEBHOOK_RETENTION_JOB,
        webhook_retention_sweep_job,
        cron=getattr(settings, "webhook_retention_cron", "0 3 * * *"),
        misfire_grace_time=3600,
    )
    register(
        AUDIT_LOG_RETENTION_JOB,
        audit_log_retention_sweep_job,
        cron=getattr(settings, "audit_log_retention_cron", "30 3 * * *"),
        misfire_grace_time=3600,
    )
    register(BILLING_AUTOMATIONS_JOB, billing_automations_job, cron="15 * * * *", misfire_grace_time=1800)
    register(PTAX_JOB, ptax_job, cron="30 13,18 * * 1-5", misfire_grace_time=3600)
    register(STORAGE_SNAPSHOT_JOB, storage_cost_snapshot_job, cron="30 2 * * *", misfire_grace_time=3600)


__all__ = [
    "AUDIT_LOG_RETENTION_JOB",
    "BILLING_AUTOMATIONS_JOB",
    "PTAX_JOB",
    "STORAGE_SNAPSHOT_JOB",
    "WEBHOOK_RETENTION_JOB",
    "audit_log_retention_sweep_job",
    "billing_automations_job",
    "configure",
    "ptax_job",
    "start_scheduler",
    "stop_scheduler",
    "storage_cost_snapshot_job",
    "webhook_retention_sweep_job",
]
