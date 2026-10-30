"""Background jobs for the Core product — on the seed scheduler primitive.

Registration happens at import (`configure()` is called from `app/main.py`);
`start_scheduler` / `stop_scheduler` are the seed's own, so NOTHING here
fires unless the process carries `NOCTUS_SCHEDULERS_ENABLED` (set only in
the deployed compose). Before this module moved onto the primitive, Core's
own AsyncIOScheduler started unconditionally — a laptop running Core
against the production `.env` would have swept production webhook rows.

Jobs (platform clock — `NOCTUS_TIMEZONE`, default America/Sao_Paulo):

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
* `core_credits_debit`            — every minute. Charges un-charged `ai_usage`
  rows to their org's prepaid credit wallet (migration 093; idempotent per row,
  BYOK orgs stamped 0). Orgs without a wallet are not touched.
* `core_owner_daily_brief`        — 07:00 daily. Code-only owner brief (no
  LLM): failed/missing routines, LLM spend, cost ledger, fleet, deploy.
  Its own run in `public.scheduler_runs` is the Operação dead-man.
* `core_scheduler_runs_retention` — 04:15 daily. Trims the run ledger
  (ok/skipped after 14 days, error after 90).

Every job body takes an optional context so tests run it on Fakes; errors
are logged (a job must not take the scheduler down), never swallowed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from noctusai_lib.api.scheduler import register, start_scheduler, stop_scheduler

from app.config import settings
from app.database import get_admin_client
from app.services import billing_automations, fx_service, storage_cost_service
from app.services.owner_brief_service import run_owner_brief
from noctusai_lib.domain.scheduler_runs import RUNS_TABLE
from noctusai_lib.primitives.timeutil import now_utc
from app.services.billing_context import BillingContext, build_billing_context
from app.services.credits.debit import run_debit
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
CREDITS_DEBIT_JOB = "core_credits_debit"
OWNER_BRIEF_JOB = "core_owner_daily_brief"
RUNS_RETENTION_JOB = "core_scheduler_runs_retention"
RUNS_RETENTION_OK_DAYS = 14
RUNS_RETENTION_ERROR_DAYS = 90


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


async def credits_debit_job(ctx: Optional[BillingContext] = None) -> dict:
    try:
        report = run_debit(ctx or build_billing_context())
    except Exception as exc:  # noqa: BLE001 — logged; the scheduler must keep running
        logger.error("Credits debit failed: %s", exc)
        return {"error": str(exc)}
    result = report.as_dict()
    if report.applied or report.errors:
        logger.info("Credits debit: %s", result)
    return result


async def owner_brief_job(db: Optional[Any] = None) -> dict:
    """The owner daily brief. Not wrapped in a catch-all: an exception here
    is exactly what the run ledger (and the admin alert) must see."""
    result = await asyncio.to_thread(
        lambda: run_owner_brief(db if db is not None else get_admin_client(), now_utc())
    )
    logger.info("Owner brief: %s", vars(result))
    return vars(result)


async def scheduler_runs_retention_job(db: Optional[Any] = None) -> dict:
    """Trim `public.scheduler_runs`: ok/skipped rows after 14 days, errors after 90."""
    client = db if db is not None else get_admin_client()
    now = now_utc()
    ok_cutoff = (now - timedelta(days=RUNS_RETENTION_OK_DAYS)).isoformat()
    err_cutoff = (now - timedelta(days=RUNS_RETENTION_ERROR_DAYS)).isoformat()

    def _purge() -> dict:
        ok = client.table(RUNS_TABLE).delete().in_("status", ["ok", "skipped"]).lt("started_at", ok_cutoff).execute()
        err = client.table(RUNS_TABLE).delete().eq("status", "error").lt("started_at", err_cutoff).execute()
        return {"ok_purged": len(ok.data or []), "error_purged": len(err.data or [])}

    result = await asyncio.to_thread(_purge)
    logger.info("Scheduler runs retention: %s", result)
    return result


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
    register(CREDITS_DEBIT_JOB, credits_debit_job, minutes=1, misfire_grace_time=30)
    register(OWNER_BRIEF_JOB, owner_brief_job, cron="0 7 * * *", misfire_grace_time=3 * 3600)
    register(RUNS_RETENTION_JOB, scheduler_runs_retention_job, cron="15 4 * * *", misfire_grace_time=3600)


__all__ = [
    "AUDIT_LOG_RETENTION_JOB",
    "BILLING_AUTOMATIONS_JOB",
    "CREDITS_DEBIT_JOB",
    "OWNER_BRIEF_JOB",
    "RUNS_RETENTION_JOB",
    "PTAX_JOB",
    "STORAGE_SNAPSHOT_JOB",
    "WEBHOOK_RETENTION_JOB",
    "audit_log_retention_sweep_job",
    "billing_automations_job",
    "configure",
    "credits_debit_job",
    "owner_brief_job",
    "scheduler_runs_retention_job",
    "ptax_job",
    "start_scheduler",
    "stop_scheduler",
    "storage_cost_snapshot_job",
    "webhook_retention_sweep_job",
]
