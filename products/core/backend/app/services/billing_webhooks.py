"""Gateway webhook processing — idempotent, managed-only, never silent.

`process_event` is the single entry point both webhook routes call after
authentication:

1. `EventInbox.claim(gateway, event_id)` — the INSERT into
   `public.payment_events` whose UNIQUE (gateway, event_id) makes a
   duplicate delivery a proven no-op (returns `duplicate`).
2. Dispatch by gateway + event type. Events for subscriptions that are not
   `automation_managed` go to the pre-050 Stripe handlers unchanged, so live
   legacy customers see exactly the behaviour they had.
3. On success the inbox row is completed (`processed` / `ignored`). On an
   exception the claim is RELEASED (row deleted) and the error re-raised,
   so the gateway's retry is processed instead of being swallowed as a
   duplicate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.integrations.payments.types import Money

from app.services import billing_service, billing_subscriptions as subs
from app.services.billing_context import BillingContext
from app.services.billing_events import ParsedGatewayEvent

logger = logging.getLogger(__name__)

_STRIPE_STATUS = {
    "trialing": "trial",
    "active": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "paused": "past_due",
    "canceled": "canceled",
    "incomplete": "incomplete",
    "incomplete_expired": "expired",
}

_ASAAS_PAID = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED", "PAYMENT_RECEIVED_IN_CASH"}
_ASAAS_METHOD = {"PIX": "pix", "BOLETO": "boleto", "CREDIT_CARD": "card"}


@dataclass(frozen=True)
class EventOutcome:
    status: str  # "processed" | "ignored" | "duplicate"
    detail: str = ""
    org_id: Optional[str] = None
    subscription_id: Optional[str] = None


def process_event(ctx: BillingContext, event: ParsedGatewayEvent) -> EventOutcome:
    gateway, event_id = event.inbox_key
    if not ctx.inbox.claim(gateway=gateway, event_id=event_id):
        logger.info("billing_webhooks: duplicate %s event %s — no-op", event.gateway, event.event_id)
        return EventOutcome("duplicate", "already processed")
    try:
        if event.gateway == "stripe":
            outcome = _handle_stripe(ctx, event)
        elif event.gateway == "asaas":
            outcome = _handle_asaas(ctx, event)
        else:
            outcome = EventOutcome("ignored", f"unknown gateway {event.gateway}")
    except Exception:
        _release(ctx, event)
        logger.exception(
            "billing_webhooks: %s event %s (%s) failed; claim released for retry",
            event.gateway, event.event_id, event.event_type,
        )
        raise
    _complete(ctx, event, outcome)
    return outcome


def _release(ctx: BillingContext, event: ParsedGatewayEvent) -> None:
    try:
        ctx.inbox.release(gateway=event.gateway, event_id=event.event_id)
    except Exception as exc:  # noqa: BLE001 — the original error is re-raised by the caller
        logger.error(
            "billing_webhooks: could not release claim %s/%s (%s); the gateway retry will be "
            "treated as a duplicate — reprocess it by hand",
            event.gateway, event.event_id, exc,
        )


def _complete(ctx: BillingContext, event: ParsedGatewayEvent, outcome: EventOutcome) -> None:
    ctx.db.table("payment_events").update(
        {
            "gateway_mode": event.mode,
            "event_type": event.event_type,
            "org_id": outcome.org_id,
            "subscription_id": outcome.subscription_id,
            "payload": event.payload,
            "status": outcome.status,
            "processed_at": ctx.clock().isoformat(),
        }
    ).eq("gateway", event.gateway).eq("event_id", event.event_id).execute()
    if outcome.status == "ignored":
        logger.info(
            "billing_webhooks: %s %s ignored — %s", event.gateway, event.event_type, outcome.detail
        )


def _transition(ctx: BillingContext, row: dict[str, Any], status: str, fields: dict[str, Any]) -> EventOutcome:
    try:
        result = subs.apply_status(ctx, row, status, fields=fields)
    except subs.IllegalTransition as exc:
        # Out-of-order delivery (e.g. an update arriving after the row is
        # already canceled). Recorded as ignored with the reason — a 500
        # here would make the gateway retry a move that can never happen.
        logger.warning("billing_webhooks: subscription %s: %s", row.get("id"), exc)
        return EventOutcome("ignored", str(exc), str(row["org_id"]), str(row["id"]))
    return EventOutcome(
        "processed",
        f"{row.get('status')} → {status}" if result.changed else "fields updated",
        str(row["org_id"]),
        str(row["id"]),
    )


# ── Stripe ──────────────────────────────────────────────────────────────


def _stripe_period_end(sub_obj: dict[str, Any]) -> Optional[str]:
    raw = sub_obj.get("current_period_end")
    if raw is None:
        # API 2025-03+ moved the period onto the subscription items.
        items = (sub_obj.get("items") or {}).get("data") or []
        raw = items[0].get("current_period_end") if items else None
    parsed = subs.parse_ts(raw)
    return parsed.isoformat() if parsed else None


def _stripe_invoice_subscription(invoice: dict[str, Any]) -> Optional[str]:
    sub_id = invoice.get("subscription")
    if isinstance(sub_id, dict):
        sub_id = sub_id.get("id")
    if not sub_id:
        details = ((invoice.get("parent") or {}).get("subscription_details") or {})
        sub_id = details.get("subscription")
    return sub_id


def _handle_stripe(ctx: BillingContext, event: ParsedGatewayEvent) -> EventOutcome:
    obj = ((event.payload.get("data") or {}).get("object")) or {}
    kind = event.event_type

    if kind == "checkout.session.completed":
        ours = (obj.get("metadata") or {}).get("subscription_id")
        row = subs.get_subscription(ctx, ours) if ours else None
        if row is None or not row.get("automation_managed"):
            billing_service.handle_checkout_completed(event.payload.get("data") or {}, db=ctx.db)
            return EventOutcome("processed", "legacy checkout handler")
        gateway_sub_id = obj.get("subscription")
        if isinstance(gateway_sub_id, dict):
            gateway_sub_id = gateway_sub_id.get("id")
        if not gateway_sub_id:
            return EventOutcome("ignored", "checkout without subscription", str(row["org_id"]), str(row["id"]))
        gateway_sub = ctx.gateway("stripe", event.mode).get_subscription(gateway_sub_id)
        fields: dict[str, Any] = {
            "gateway_subscription_id": gateway_sub_id,
            "gateway_customer_id": obj.get("customer") or row.get("gateway_customer_id"),
            "gateway_mode": event.mode,
            "payment_url": None,
        }
        raw = gateway_sub.raw or {}
        period_end = _stripe_period_end(raw)
        if period_end:
            fields["current_period_end"] = period_end
        trial_end = subs.parse_ts(raw.get("trial_end"))
        if trial_end:
            fields["trial_ends_at"] = trial_end.isoformat()
        status = _STRIPE_STATUS.get(raw.get("status") or "", "incomplete")
        if gateway_sub.status == "trialing":
            status = "trial"
        return _transition(ctx, row, status, fields)

    if kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        row = subs.find_by_gateway_id(ctx, "stripe", str(obj.get("id")))
        if row is None or not row.get("automation_managed"):
            data = event.payload.get("data") or {}
            if kind == "customer.subscription.updated":
                billing_service.handle_subscription_updated(data, db=ctx.db)
            else:
                billing_service.handle_subscription_deleted(data, db=ctx.db)
            return EventOutcome("processed", "legacy subscription handler")
        fields = {"cancel_at_period_end": bool(obj.get("cancel_at_period_end"))}
        period_end = _stripe_period_end(obj)
        if period_end:
            fields["current_period_end"] = period_end
        if kind == "customer.subscription.deleted":
            target = "expired" if row.get("status") == "grace" else "canceled"
        else:
            target = _STRIPE_STATUS.get(obj.get("status") or "")
            if target is None:
                return EventOutcome("ignored", f"unknown stripe status {obj.get('status')}", str(row["org_id"]), str(row["id"]))
            if target == "past_due" and row.get("status") == "grace":
                target = "grace"  # our leniency window outranks the gateway's retry state
        return _transition(ctx, row, target, fields)

    if kind in ("invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"):
        sub_id = _stripe_invoice_subscription(obj)
        row = subs.find_by_gateway_id(ctx, "stripe", str(sub_id)) if sub_id else None
        if row is None or not row.get("automation_managed"):
            if kind == "invoice.payment_failed":
                billing_service.handle_invoice_payment_failed(event.payload.get("data") or {}, db=ctx.db)
                return EventOutcome("processed", "legacy invoice handler")
            return EventOutcome("ignored", "invoice for an unmanaged subscription")
        paid = kind != "invoice.payment_failed"
        amount = int((obj.get("amount_paid") if paid else obj.get("amount_due")) or 0)
        charge_id = obj.get("charge")
        if isinstance(charge_id, dict):
            charge_id = charge_id.get("id")
        fee_cents: Optional[int] = None
        if paid and charge_id and amount > 0:
            fee_cents = _stripe_fee(ctx, event.mode, charge_id)
        paid_at = None
        if paid:
            transitions = obj.get("status_transitions") or {}
            paid_at = subs.parse_ts(transitions.get("paid_at")) or ctx.clock()
        if amount > 0 or not paid:
            subs.record_payment(
                ctx,
                row,
                gateway_payment_id=str(obj.get("id")),
                gateway_charge_id=charge_id,
                status="paid" if paid else "failed",
                gross_cents=amount,
                currency=str(obj.get("currency") or row.get("currency") or "brl"),
                fee_cents=fee_cents if paid else 0,
                billing_method="card",
                paid_at=paid_at,
            )
        if not paid:
            if row.get("status") in ("active", "trial"):
                return _transition(ctx, row, "past_due", {})
            return EventOutcome("processed", "payment failure recorded", str(row["org_id"]), str(row["id"]))
        if amount == 0:
            # A trial's $0 invoice proves nothing was charged.
            return EventOutcome("processed", "zero-amount invoice", str(row["org_id"]), str(row["id"]))
        fields = {}
        lines = ((obj.get("lines") or {}).get("data")) or []
        period = (lines[0].get("period") if lines else None) or {}
        end = subs.parse_ts(period.get("end"))
        start = subs.parse_ts(period.get("start"))
        if end:
            fields["current_period_end"] = end.isoformat()
        if start:
            fields["current_period_start"] = start.isoformat()
        if row.get("status") in ("active",) and not fields:
            return EventOutcome("processed", "payment recorded", str(row["org_id"]), str(row["id"]))
        return _transition(ctx, row, "active", fields)

    return EventOutcome("ignored", f"unhandled stripe event {kind}")


def _stripe_fee(ctx: BillingContext, mode: str, charge_id: str) -> Optional[int]:
    """The fee, or None when Stripe has not settled it yet (reconcile retries)."""
    from noctusai_lib.integrations.payments import PaymentGatewayError

    try:
        breakdown = ctx.gateway("stripe", mode).get_fee_breakdown(charge_id)
    except (PaymentGatewayError, KeyError, TypeError) as exc:
        logger.info("billing_webhooks: stripe fee for %s not available yet (%s)", charge_id, exc)
        return None
    return breakdown.fee.amount_cents


# ── Asaas ───────────────────────────────────────────────────────────────


def _asaas_money(value: Any) -> int:
    return Money.from_decimal_reais(Decimal(str(value))).amount_cents


def _handle_asaas(ctx: BillingContext, event: ParsedGatewayEvent) -> EventOutcome:
    kind = event.event_type
    payload = event.payload

    if kind.startswith("SUBSCRIPTION_"):
        sub_obj = payload.get("subscription") or {}
        row = subs.find_by_gateway_id(ctx, "asaas", str(sub_obj.get("id"))) if sub_obj.get("id") else None
        if row is None or not row.get("automation_managed"):
            return EventOutcome("ignored", "subscription not managed here")
        if kind in ("SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"):
            if row.get("cancel_at_period_end") and row.get("status") in ("active", "trial"):
                # We stopped it at the gateway ourselves; access runs to period end.
                return EventOutcome("processed", "scheduled cancel acknowledged", str(row["org_id"]), str(row["id"]))
            target = "expired" if row.get("status") == "grace" else "canceled"
            return _transition(ctx, row, target, {})
        return EventOutcome("ignored", f"unhandled asaas event {kind}", str(row["org_id"]), str(row["id"]))

    if not kind.startswith("PAYMENT_"):
        return EventOutcome("ignored", f"unhandled asaas event {kind}")

    payment = payload.get("payment") or {}
    sub_id = payment.get("subscription")
    row = subs.find_by_gateway_id(ctx, "asaas", str(sub_id)) if sub_id else None
    if row is None or not row.get("automation_managed"):
        return EventOutcome("ignored", "payment for a subscription not managed here")

    method = _ASAAS_METHOD.get(str(payment.get("billingType") or ""), "unspecified")
    gross = _asaas_money(payment.get("value") or 0)
    if kind in _ASAAS_PAID:
        net_raw = payment.get("netValue")
        fee = gross - _asaas_money(net_raw) if net_raw is not None else None
        paid_at = subs.parse_ts(payment.get("confirmedDate") or payment.get("paymentDate")) or ctx.clock()
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=timezone.utc)
        subs.record_payment(
            ctx, row,
            gateway_payment_id=str(payment.get("id")),
            status="paid",
            gross_cents=gross,
            currency="BRL",
            fee_cents=fee,
            billing_method=method,
            paid_at=paid_at,
        )
        due = subs.parse_ts(payment.get("dueDate"))
        fields: dict[str, Any] = {}
        if due:
            start = due.date()
            end = subs.add_cycle(start, row.get("billing_cycle") or "monthly")
            fields["current_period_start"] = datetime.combine(start, datetime.min.time(), timezone.utc).isoformat()
            fields["current_period_end"] = datetime.combine(end, datetime.min.time(), timezone.utc).isoformat()
        return _transition(ctx, row, "active", fields)

    if kind == "PAYMENT_OVERDUE":
        subs.record_payment(
            ctx, row,
            gateway_payment_id=str(payment.get("id")),
            status="failed",
            gross_cents=gross,
            currency="BRL",
            fee_cents=0,
            billing_method=method,
            paid_at=None,
        )
        if row.get("status") in ("active", "trial"):
            return _transition(ctx, row, "past_due", {})
        return EventOutcome("processed", "overdue recorded", str(row["org_id"]), str(row["id"]))

    if kind in ("PAYMENT_REFUNDED", "PAYMENT_PARTIALLY_REFUNDED"):
        subs.record_payment(
            ctx, row,
            gateway_payment_id=str(payment.get("id")),
            status="refunded",
            gross_cents=gross,
            currency="BRL",
            fee_cents=None,
            billing_method=method,
            paid_at=None,
        )
        return EventOutcome("processed", "refund recorded", str(row["org_id"]), str(row["id"]))

    return EventOutcome("ignored", f"unhandled asaas event {kind}", str(row["org_id"]), str(row["id"]))


__all__ = ["EventOutcome", "process_event"]
