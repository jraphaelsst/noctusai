"""Billing automations — clock-driven sweeps over MANAGED subscriptions.

Every sweep:

* runs only when the owner has switched `billing_automations_enabled` on
  (Admin > Faturamento); off → returns `skipped` and writes nothing;
* reads only `subscriptions.automation_managed = true` rows, so a
  subscription that predates migration 050 is never read, let alone moved;
* changes licenses only through `license_service.revoke_subscription_licenses`
  / `grant_license(source='subscription')`, so a `legacy` or `manual`
  license can never be touched;
* takes "now" from `ctx.clock` — the tests drive it.

Sweeps (in `run_all` order):

1. `sweep_trials`        trial ended with no payment → past_due
                         (Stripe rows are reconciled against Stripe instead —
                         Stripe moves its own trials).
2. `sweep_period_end`    cancel_at_period_end reached → canceled;
                         a manual subscription past its period → past_due.
3. `sweep_past_due`      past_due → grace (grace_ends_at = past_due_since +
                         plan.grace_days); plan without grace → expired.
4. `sweep_grace`         grace ended unpaid → expired (+ stop the gateway).
5. `reconcile`           gateway truth for Stripe/Asaas rows (terminal at the
                         gateway ⇒ terminal here), pending Stripe fees, and
                         gateway cancellations that failed earlier.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from noctusai_lib.integrations.payments import PaymentGatewayError
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from app.services import billing_subscriptions as subs
from app.services.billing_config import GatewayNotConfigured
from app.services.billing_context import BillingContext

logger = logging.getLogger(__name__)

#: Stripe retries the first post-trial charge itself; give its webhook this
#: long before the reconcile sweep asks Stripe directly.
TRIAL_WEBHOOK_SLACK = timedelta(hours=1)


@dataclass
class SweepReport:
    name: str
    skipped: bool = False
    examined: int = 0
    changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "skipped": self.skipped,
            "examined": self.examined,
            "changed": list(self.changed),
            "errors": list(self.errors),
        }


def _managed(ctx: BillingContext, statuses: list[str]) -> list[dict[str, Any]]:
    # postgrest-unbounded-ok: `.in_` gets a literal list of at most 4 status names; rows are paged.
    return list(
        iter_paged_rows(
            lambda start, end: ctx.db.table("subscriptions")
            .select("*")
            .eq("automation_managed", True)
            .in_("status", statuses)
            .order("id")
            .range(start, end)
            .execute()
            .data,
            label=f"managed subscriptions {statuses}",
        )
    )


def _guarded(ctx: BillingContext, name: str, body: Callable[[SweepReport], None]) -> SweepReport:
    report = SweepReport(name)
    if not ctx.config.automations_enabled():
        report.skipped = True
        logger.info("billing_automations: %s skipped — automations are switched off", name)
        return report
    body(report)
    if report.changed or report.errors:
        logger.info(
            "billing_automations: %s examined=%d changed=%d errors=%d",
            name, report.examined, len(report.changed), len(report.errors),
        )
    return report


def _move(ctx: BillingContext, report: SweepReport, row: dict[str, Any], status: str, fields: dict[str, Any] | None = None) -> None:
    before = row.get("status")
    try:
        outcome = subs.apply_status(ctx, row, status, fields=fields or {})
    except subs.IllegalTransition as exc:
        report.errors.append(f"{row['id']}: {exc}")
        logger.error("billing_automations: %s: %s", row["id"], exc)
        return
    if outcome.changed:
        report.changed.append(f"{row['id']}: {before} → {status}")


def _stop_at_gateway(ctx: BillingContext, report: SweepReport, row: dict[str, Any]) -> None:
    """Stop future charges; on failure flag the row so reconcile retries."""
    gateway, gateway_id = row.get("gateway"), row.get("gateway_subscription_id")
    if gateway not in ("stripe", "asaas") or not gateway_id:
        return
    try:
        ctx.gateway(gateway, row.get("gateway_mode") or ctx.config.mode()).cancel_subscription(gateway_id)
    except (PaymentGatewayError, GatewayNotConfigured) as exc:
        report.errors.append(f"{row['id']}: gateway cancel failed: {exc}")
        logger.error("billing_automations: gateway cancel failed for %s: %s", row["id"], exc)
        metadata = dict(row.get("metadata") or {})
        metadata["gateway_cancel_pending"] = True
        ctx.db.table("subscriptions").update({"metadata": metadata}).eq("id", row["id"]).execute()


def sweep_trials(ctx: BillingContext) -> SweepReport:
    def body(report: SweepReport) -> None:
        now = ctx.clock()
        for row in _managed(ctx, ["trial"]):
            report.examined += 1
            ends = subs.parse_ts(row.get("trial_ends_at"))
            if ends is None or ends > now:
                continue
            if row.get("gateway") == "stripe":
                if ends + TRIAL_WEBHOOK_SLACK <= now:
                    _reconcile_one(ctx, report, row)
                continue
            _move(ctx, report, row, "past_due", {"past_due_since": ends.isoformat()})

    return _guarded(ctx, "trials", body)


def sweep_period_end(ctx: BillingContext) -> SweepReport:
    def body(report: SweepReport) -> None:
        now = ctx.clock()
        for row in _managed(ctx, ["active", "trial"]):
            report.examined += 1
            ends = subs.parse_ts(row.get("current_period_end"))
            if ends is None or ends > now:
                continue
            if row.get("cancel_at_period_end"):
                _move(ctx, report, row, "canceled")
            elif row.get("gateway") == "manual" and row.get("status") == "active":
                _move(ctx, report, row, "past_due", {"past_due_since": ends.isoformat()})

    return _guarded(ctx, "period_end", body)


def _grace_days(ctx: BillingContext, plan_id: Any) -> int:
    rows = ctx.db.table("plans").select("id, grace_days").eq("id", plan_id).limit(1).execute().data or []
    return int((rows[0].get("grace_days") if rows else 0) or 0)


def sweep_past_due(ctx: BillingContext) -> SweepReport:
    def body(report: SweepReport) -> None:
        now = ctx.clock()
        for row in _managed(ctx, ["past_due"]):
            report.examined += 1
            since = subs.parse_ts(row.get("past_due_since")) or now
            grace_days = _grace_days(ctx, row.get("plan_id"))
            if grace_days <= 0:
                _move(ctx, report, row, "expired")
                _stop_at_gateway(ctx, report, row)
                continue
            _move(ctx, report, row, "grace", {"grace_ends_at": (since + timedelta(days=grace_days)).isoformat()})

    return _guarded(ctx, "past_due", body)


def sweep_grace(ctx: BillingContext) -> SweepReport:
    def body(report: SweepReport) -> None:
        now = ctx.clock()
        for row in _managed(ctx, ["grace"]):
            report.examined += 1
            ends = subs.parse_ts(row.get("grace_ends_at"))
            if ends is None or ends > now:
                continue
            _move(ctx, report, row, "expired")
            _stop_at_gateway(ctx, report, row)

    return _guarded(ctx, "grace", body)


def _reconcile_one(ctx: BillingContext, report: SweepReport, row: dict[str, Any]) -> None:
    gateway, gateway_id = row.get("gateway"), row.get("gateway_subscription_id")
    if gateway not in ("stripe", "asaas") or not gateway_id:
        return
    try:
        remote = ctx.gateway(gateway, row.get("gateway_mode") or ctx.config.mode()).get_subscription(gateway_id)
    except (PaymentGatewayError, GatewayNotConfigured) as exc:
        report.errors.append(f"{row['id']}: reconcile read failed: {exc}")
        logger.warning("billing_automations: reconcile read failed for %s: %s", row["id"], exc)
        return
    status = row.get("status")
    if remote.status == "canceled" and status not in subs.TERMINAL_STATUSES:
        if row.get("cancel_at_period_end") and status in ("active", "trial"):
            return  # period-end sweep closes it
        _move(ctx, report, row, "expired" if status == "grace" else "canceled")
    elif remote.status == "active" and status == "trial":
        _move(ctx, report, row, "active")
    elif remote.status in ("past_due", "unpaid") and status in ("active", "trial"):
        _move(ctx, report, row, "past_due")


def reconcile(ctx: BillingContext) -> SweepReport:
    def body(report: SweepReport) -> None:
        for row in _managed(ctx, ["trial", "active", "past_due", "grace"]):
            report.examined += 1
            _reconcile_one(ctx, report, row)
        for row in _managed(ctx, ["canceled", "expired"]):
            if (row.get("metadata") or {}).get("gateway_cancel_pending"):
                before = len(report.errors)
                _stop_at_gateway(ctx, report, row)
                if len(report.errors) == before:
                    metadata = dict(row.get("metadata") or {})
                    metadata.pop("gateway_cancel_pending", None)
                    ctx.db.table("subscriptions").update({"metadata": metadata}).eq("id", row["id"]).execute()
                    report.changed.append(f"{row['id']}: gateway cancel retried")
        _fill_pending_fees(ctx, report)

    return _guarded(ctx, "reconcile", body)


def _fill_pending_fees(ctx: BillingContext, report: SweepReport) -> None:
    pending = list(
        iter_paged_rows(
            lambda start, end: ctx.db.table("billing_payments")
            .select("*")
            .eq("fee_pending", True)
            .order("id")
            .range(start, end)
            .execute()
            .data,
            label="billing_payments fee_pending",
        )
    )
    for payment in pending:
        charge_id = payment.get("gateway_charge_id")
        if payment.get("gateway") != "stripe" or not charge_id:
            report.errors.append(f"payment {payment['id']}: fee pending with no charge id to read")
            continue
        try:
            breakdown = ctx.gateway("stripe", payment["gateway_mode"]).get_fee_breakdown(charge_id)
        except (PaymentGatewayError, GatewayNotConfigured, KeyError, TypeError) as exc:
            report.errors.append(f"payment {payment['id']}: fee still unavailable: {exc}")
            continue
        subscription = subs.get_subscription(ctx, str(payment["subscription_id"])) if payment.get("subscription_id") else None
        if subscription is None:
            report.errors.append(f"payment {payment['id']}: subscription gone; fee not booked")
            continue
        subs.record_payment(
            ctx,
            subscription,
            gateway_payment_id=payment["gateway_payment_id"],
            gateway_charge_id=charge_id,
            status=payment["status"],
            gross_cents=int(payment["gross_cents"]),
            currency=payment["currency"],
            fee_cents=breakdown.fee.amount_cents,
            billing_method=payment.get("billing_method"),
            paid_at=subs.parse_ts(payment.get("paid_at")),
        )
        report.changed.append(f"payment {payment['id']}: fee {breakdown.fee.amount_cents}")


SWEEPS: tuple[Callable[[BillingContext], SweepReport], ...] = (
    sweep_trials,
    sweep_period_end,
    sweep_past_due,
    sweep_grace,
    reconcile,
)


def run_all(ctx: BillingContext) -> list[SweepReport]:
    return [sweep(ctx) for sweep in SWEEPS]


__all__ = [
    "SWEEPS",
    "SweepReport",
    "reconcile",
    "run_all",
    "sweep_grace",
    "sweep_past_due",
    "sweep_period_end",
    "sweep_trials",
]
