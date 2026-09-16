"""Managed subscriptions — lifecycle, licenses and payments over Core's tables.

"Managed" = `subscriptions.automation_managed = true`: rows created by the
billing flow of migration 050 (self-serve checkout or manual onboarding).
Every function here refuses an unmanaged row, so subscriptions that existed
before 050 are never moved by webhooks, automations or admin actions.

State changes go through the seed state machine
(`noctusai_lib.domain.payments.transition`); an illegal move raises
`IllegalTransition` instead of being written. The DB keeps its historical
`'trial'` spelling for the seed's `TRIALING`.

Licensing follows state: entering trial/active/past_due/grace grants the
plan's product license (`source='subscription'`); entering canceled/expired
revokes it. Legacy and manual licenses are never touched (see
`license_service`).
"""
from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.domain.payments import Subscription, SubscriptionState, transition
from noctusai_lib.integrations.payments import PaymentGatewayError
from noctusai_lib.integrations.payments.checkout import CheckoutRequest
from noctusai_lib.integrations.payments.types import Money

from app.services import fx_service, license_service
from app.services.billing_config import GatewayNotConfigured
from app.services.billing_context import BillingContext

logger = logging.getLogger(__name__)

DB_TO_STATE: dict[str, SubscriptionState] = {
    "incomplete": SubscriptionState.INCOMPLETE,
    "trial": SubscriptionState.TRIALING,
    "active": SubscriptionState.ACTIVE,
    "past_due": SubscriptionState.PAST_DUE,
    "grace": SubscriptionState.GRACE,
    "canceled": SubscriptionState.CANCELED,
    "expired": SubscriptionState.EXPIRED,
}
STATE_TO_DB: dict[SubscriptionState, str] = {v: k for k, v in DB_TO_STATE.items()}

#: States in which the org keeps its product license.
LICENSED_STATUSES = frozenset({"trial", "active", "past_due", "grace"})
TERMINAL_STATUSES = frozenset({"canceled", "expired"})
ORG_ADMIN_ROLES = ("owner", "admin", "manager")


class BillingError(RuntimeError):
    """A billing request the caller can fix (maps to 4xx)."""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


class IllegalTransition(RuntimeError):
    """The requested state change is not in the seed state machine."""


class UnmanagedSubscription(RuntimeError):
    """A pre-050 subscription reached a managed-only code path."""


@dataclass(frozen=True)
class TransitionOutcome:
    subscription: dict[str, Any]
    changed: bool
    granted: bool = False
    revoked: int = 0


# ── helpers ─────────────────────────────────────────────────────────────


def parse_ts(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        from datetime import timezone

        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def add_cycle(start: date, cycle: str) -> date:
    """`start` + one billing cycle, clamping to month end (Jan 31 → Feb 28)."""
    months = 12 if cycle == "yearly" else 1
    total = start.month - 1 + months
    year, month = start.year + total // 12, total % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def _require_managed(row: dict[str, Any]) -> None:
    if not row.get("automation_managed"):
        raise UnmanagedSubscription(
            f"subscription {row.get('id')} predates billing automation; refusing to modify it"
        )


def get_subscription(ctx: BillingContext, subscription_id: str) -> Optional[dict[str, Any]]:
    rows = ctx.db.table("subscriptions").select("*").eq("id", subscription_id).limit(1).execute().data or []
    return rows[0] if rows else None


def find_by_gateway_id(ctx: BillingContext, gateway: str, gateway_subscription_id: str) -> Optional[dict[str, Any]]:
    rows = (
        ctx.db.table("subscriptions")
        .select("*")
        .eq("gateway", gateway)
        .eq("gateway_subscription_id", gateway_subscription_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _plan_row(db: Any, plan_id: str) -> Optional[dict[str, Any]]:
    rows = db.table("plans").select("*").eq("id", plan_id).limit(1).execute().data or []
    return rows[0] if rows else None


def _plan(ctx: BillingContext, plan_id: str) -> Optional[dict[str, Any]]:
    return _plan_row(ctx.db, plan_id)


# ── state changes ───────────────────────────────────────────────────────


def apply_status(
    ctx: BillingContext,
    row: dict[str, Any],
    target_status: str,
    *,
    fields: Optional[dict[str, Any]] = None,
) -> TransitionOutcome:
    """Move a managed subscription to `target_status` (+ write `fields`).

    Same status → only `fields` are written (idempotent re-delivery).
    """
    _require_managed(row)
    if target_status not in DB_TO_STATE:
        raise IllegalTransition(f"unknown subscription status {target_status!r}")
    now = ctx.clock()
    current_status = row.get("status")
    updates: dict[str, Any] = dict(fields or {})

    if current_status != target_status:
        snapshot = Subscription(
            id=str(row["id"]),
            external_reference=str(row.get("org_id")),
            gateway=str(row.get("gateway") or "manual"),
            id_at_gateway=str(row.get("gateway_subscription_id") or ""),
            state=DB_TO_STATE[current_status],
            created_at=parse_ts(row.get("created_at")) or now,
            updated_at=parse_ts(row.get("updated_at")) or now,
            canceled_at=parse_ts(row.get("canceled_at")),
        )
        try:
            moved = transition(snapshot, DB_TO_STATE[target_status], now=now)
        except ValueError as exc:
            raise IllegalTransition(str(exc)) from exc
        updates["status"] = target_status
        if moved.canceled_at is not None and target_status in TERMINAL_STATUSES:
            updates["canceled_at"] = moved.canceled_at.isoformat()
        if target_status == "past_due" and not row.get("past_due_since"):
            updates.setdefault("past_due_since", now.isoformat())
        if target_status == "active":
            updates.setdefault("past_due_since", None)
            updates.setdefault("grace_ends_at", None)

    if not updates:
        return TransitionOutcome(row, changed=False)

    updates["updated_at"] = now.isoformat()
    result = ctx.db.table("subscriptions").update(updates).eq("id", row["id"]).execute()
    updated = {**row, **updates, **((result.data or [{}])[0])}
    changed = current_status != target_status
    if changed:
        logger.info(
            "billing: subscription %s %s → %s", row["id"], current_status, target_status
        )

    granted = False
    revoked = 0
    if target_status in LICENSED_STATUSES:
        granted = ensure_license(ctx, updated)
    elif target_status in TERMINAL_STATUSES:
        revoked = len(
            license_service.revoke_subscription_licenses(ctx.db, str(row["id"]), clock=ctx.clock)
        )
    return TransitionOutcome(updated, changed=changed, granted=granted, revoked=revoked)


def ensure_license(ctx: BillingContext, row: dict[str, Any]) -> bool:
    """Grant the plan's product license to the subscription's org (idempotent)."""
    plan = _plan(ctx, str(row["plan_id"]))
    product_id = (plan or {}).get("product_id")
    if not product_id:
        logger.warning(
            "billing: plan %s of subscription %s licenses no product; nothing granted",
            row.get("plan_id"), row.get("id"),
        )
        return False
    result = license_service.grant_license(
        ctx.db,
        org_id=str(row["org_id"]),
        product_id=str(product_id),
        source="subscription",
        subscription_id=str(row["id"]),
    )
    return result.created


# ── creating subscriptions ──────────────────────────────────────────────


def _active_price(db: Any, plan_price_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    prices = (
        db.table("plan_prices").select("*").eq("id", plan_price_id).limit(1).execute().data or []
    )
    if not prices or not prices[0].get("ativo"):
        raise BillingError("Preço não encontrado ou inativo.", status_code=404)
    price = prices[0]
    plan = _plan_row(db, str(price["plan_id"]))
    if not plan or not plan.get("ativo"):
        raise BillingError("Plano não encontrado ou inativo.", status_code=404)
    return plan, price


def validate_price_for_org_type(db: Any, plan_price_id: str, org_type: str) -> dict[str, Any]:
    """Signup + checkout guard: the price exists, is sold, fits the audience."""
    plan, price = _active_price(db, plan_price_id)
    audience = plan.get("audience") or "any"
    if audience != "any" and audience != org_type:
        raise BillingError("Este plano não está disponível para este tipo de conta.", status_code=422)
    return {"plan": plan, "price": price}


def _open_managed_for_product(ctx: BillingContext, org_id: str, product_id: Optional[str]) -> Optional[dict[str, Any]]:
    # postgrest-unbounded-ok: one org's OPEN subscriptions — a handful at most (one per product).
    rows = (
        ctx.db.table("subscriptions")
        .select("id, status, plan_id")
        .eq("org_id", org_id)
        .eq("automation_managed", True)
        .in_("status", ["incomplete", "trial", "active", "past_due", "grace"])
        .execute()
        .data
        or []
    )
    for row in rows:
        plan = _plan(ctx, str(row["plan_id"]))
        if (plan or {}).get("product_id") == product_id:
            return row
    return None


def start_checkout(
    ctx: BillingContext,
    *,
    org_id: str,
    payer_email: str,
    plan_price_id: str,
    gateway: str,
    billing_method: str,
    tax_id: Optional[str],
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    """Self-serve: create the managed row, then the gateway's payment page."""
    if gateway not in ("stripe", "asaas"):
        raise BillingError("Gateway inválido.")
    if not ctx.config.gateway_enabled(gateway):
        raise BillingError("Este meio de pagamento não está disponível.", status_code=409)
    mode = ctx.config.mode()
    if not ctx.config.gateway_ready(gateway, mode):
        raise BillingError("Pagamento indisponível: gateway não configurado.", status_code=503)
    if gateway == "stripe" and billing_method != "card":
        raise BillingError("Stripe aceita apenas cartão.")
    if gateway == "asaas" and not tax_id:
        raise BillingError("Informe o CPF/CNPJ para pagar com Asaas.")

    orgs = ctx.db.table("organizations").select("id, nome, org_type").eq("id", org_id).limit(1).execute().data or []
    if not orgs:
        raise BillingError("Organização não encontrada.", status_code=404)
    org = orgs[0]
    chosen = validate_price_for_org_type(ctx.db, plan_price_id, org.get("org_type") or "individual")
    plan, price = chosen["plan"], chosen["price"]
    if _open_managed_for_product(ctx, org_id, plan.get("product_id")):
        raise BillingError("Esta organização já tem uma assinatura em andamento para este produto.", status_code=409)

    stripe_price_id = price.get(f"stripe_price_id_{mode}")
    if gateway == "stripe" and not stripe_price_id:
        raise BillingError(
            f"Este preço não tem um Price do Stripe para o modo '{mode}'.", status_code=409
        )

    now = ctx.clock()
    trial_days = int(plan.get("trial_days") or 0) if gateway == "stripe" else 0
    inserted = (
        ctx.db.table("subscriptions")
        .insert(
            {
                "org_id": org_id,
                "plan_id": plan["id"],
                "plan_price_id": price["id"],
                "status": "incomplete",
                "gateway": gateway,
                "gateway_mode": mode,
                "billing_cycle": price["billing_cycle"],
                "billing_method": billing_method,
                "currency": price["currency"],
                "amount_cents": int(price["amount_cents"]),
                "automation_managed": True,
                "started_at": now.isoformat(),
            }
        )
        .execute()
        .data
        or []
    )
    if not inserted:
        raise RuntimeError("billing: subscription insert returned no row")
    row = inserted[0]

    request = CheckoutRequest(
        # The org is the gateway customer's key (one customer per org);
        # our subscription id rides in metadata, and the Asaas subscription
        # is matched by its gateway id stored below.
        external_reference=org_id,
        email=payer_email,
        name=org.get("nome") or org_id,
        price=Money(int(price["amount_cents"]), price["currency"]),
        billing_cycle=price["billing_cycle"],
        billing_method=billing_method,
        plan_ref=stripe_price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "subscription_id": str(row["id"]),
            "org_id": org_id,
            "plan_id": str(plan["id"]),
            "plan_price_id": str(price["id"]),
        },
        trial_days=trial_days,
        tax_id=tax_id,
    )
    try:
        session = ctx.checkout(gateway, mode).create_checkout(request)
    except (GatewayNotConfigured, PaymentGatewayError) as exc:
        # The row never reached a gateway — close it so it does not block
        # the next attempt (incomplete → canceled is legal).
        apply_status(ctx, row, "canceled", fields={"metadata": {"checkout_error": str(exc)[:300]}})
        raise BillingError(f"Não foi possível iniciar o pagamento: {exc}", status_code=502) from exc

    updates: dict[str, Any] = {
        "gateway_customer_id": session.customer_id_at_gateway,
        "payment_url": session.checkout_url,
        "updated_at": now.isoformat(),
    }
    # Stripe creates the subscription only when the payer finishes the
    # hosted page (the webhook brings the id); Asaas creates it now.
    if gateway == "asaas" and session.subscription_id_at_gateway:
        updates["gateway_subscription_id"] = session.subscription_id_at_gateway
    ctx.db.table("subscriptions").update(updates).eq("id", row["id"]).execute()
    remember_customer(ctx, org_id=org_id, gateway=gateway, mode=mode,
                      customer_id=session.customer_id_at_gateway, email=payer_email)
    result: dict[str, Any] = {
        "subscription_id": row["id"],
        "checkout_url": session.checkout_url,
        "gateway": gateway,
        "mode": mode,
        "pix_qr": None,
    }
    if session.pix_qr is not None:
        result["pix_qr"] = {
            "payload": session.pix_qr.payload,
            "encoded_image": session.pix_qr.encoded_image,
            "expiration_date": session.pix_qr.expiration_date,
        }
    return result


def remember_customer(
    ctx: BillingContext, *, org_id: str, gateway: str, mode: str, customer_id: str, email: Optional[str]
) -> None:
    existing = (
        ctx.db.table("billing_customers")
        .select("id, gateway_customer_id")
        .eq("org_id", org_id)
        .eq("gateway", gateway)
        .eq("gateway_mode", mode)
        .limit(1)
        .execute()
        .data
        or []
    )
    now = ctx.clock().isoformat()
    if existing:
        if existing[0].get("gateway_customer_id") != customer_id:
            ctx.db.table("billing_customers").update(
                {"gateway_customer_id": customer_id, "email": email, "updated_at": now}
            ).eq("id", existing[0]["id"]).execute()
        return
    ctx.db.table("billing_customers").insert(
        {
            "org_id": org_id,
            "gateway": gateway,
            "gateway_mode": mode,
            "gateway_customer_id": customer_id,
            "email": email,
        }
    ).execute()


def onboard_manual(
    ctx: BillingContext,
    *,
    org_id: str,
    plan_price_id: str,
    current_period_end: Optional[datetime],
    trial_days: int,
    note: Optional[str],
    actor_user_id: str,
) -> dict[str, Any]:
    """Platform admin sells a plan outside the gateways (manual onboarding).

    The subscription is managed like any other: licensed now, moved to
    past_due when its period ends without a renewal, then grace, then
    expired — unless the admin extends `current_period_end`.
    """
    orgs = ctx.db.table("organizations").select("id, org_type").eq("id", org_id).limit(1).execute().data or []
    if not orgs:
        raise BillingError("Organização não encontrada.", status_code=404)
    plan, price = _active_price(ctx.db, plan_price_id)
    if _open_managed_for_product(ctx, org_id, plan.get("product_id")):
        raise BillingError("Esta organização já tem uma assinatura em andamento para este produto.", status_code=409)
    now = ctx.clock()
    trial_ends_at = now + timedelta(days=trial_days) if trial_days > 0 else None
    period_end = current_period_end
    if period_end is None:
        # A manual trial's first "period" IS the trial: when it ends the
        # admin records the payment (`renew_manual`) or the row goes
        # past_due → grace → expired like any unpaid subscription.
        period_end = trial_ends_at or datetime.combine(
            add_cycle(now.date(), price["billing_cycle"]), now.timetz()
        )
    payload = {
        "org_id": org_id,
        "plan_id": plan["id"],
        "plan_price_id": price["id"],
        "status": "incomplete",
        "gateway": "manual",
        "billing_cycle": price["billing_cycle"],
        "billing_method": "unspecified",
        "currency": price["currency"],
        "amount_cents": int(price["amount_cents"]),
        "automation_managed": True,
        "started_at": now.isoformat(),
        "current_period_start": now.isoformat(),
        "current_period_end": period_end.isoformat(),
        "metadata": {"onboarded_by": actor_user_id, "note": note or ""},
    }
    inserted = ctx.db.table("subscriptions").insert(payload).execute().data or []
    if not inserted:
        raise RuntimeError("billing: manual subscription insert returned no row")
    row = inserted[0]
    if trial_ends_at is not None:
        outcome = apply_status(ctx, row, "trial", fields={"trial_ends_at": trial_ends_at.isoformat()})
    else:
        outcome = apply_status(ctx, row, "active")
    return outcome.subscription


def renew_manual(ctx: BillingContext, row: dict[str, Any], *, period_end: datetime) -> dict[str, Any]:
    """Platform admin records a manual payment: active until `period_end`."""
    _require_managed(row)
    if row.get("gateway") != "manual":
        raise BillingError("Só assinaturas manuais são renovadas por aqui.", status_code=409)
    if period_end <= ctx.clock():
        raise BillingError("A nova data de fim precisa estar no futuro.")
    fields = {
        "current_period_start": ctx.clock().isoformat(),
        "current_period_end": period_end.isoformat(),
        "trial_ends_at": None,
    }
    try:
        return apply_status(ctx, row, "active", fields=fields).subscription
    except IllegalTransition as exc:
        raise BillingError(f"Não é possível renovar esta assinatura: {exc}", status_code=409) from exc


def cancel(ctx: BillingContext, row: dict[str, Any], *, at_period_end: bool) -> dict[str, Any]:
    """Cancel a managed subscription now, or at the end of the paid period.

    At period end, access continues and the row carries
    `cancel_at_period_end`; Stripe ends it itself (the webhook follows),
    Asaas is stopped now (it cannot schedule) and the period-end sweep
    closes the row locally, as it does for manual subscriptions.
    """
    _require_managed(row)
    status = row.get("status")
    if status in TERMINAL_STATUSES:
        return row
    gateway = row.get("gateway")
    gateway_id = row.get("gateway_subscription_id")
    scheduled = (
        at_period_end
        and status in ("active", "trial")
        and (gateway == "stripe" and bool(gateway_id) or bool(row.get("current_period_end")))
    )
    if gateway in ("stripe", "asaas") and gateway_id:
        mode = row.get("gateway_mode") or ctx.config.mode()
        if gateway == "stripe" and scheduled:
            schedule_stripe_cancel(ctx, mode, gateway_id)
        else:
            ctx.gateway(gateway, mode).cancel_subscription(gateway_id)
    if scheduled:
        now = ctx.clock().isoformat()
        ctx.db.table("subscriptions").update(
            {"cancel_at_period_end": True, "updated_at": now}
        ).eq("id", row["id"]).execute()
        return {**row, "cancel_at_period_end": True, "updated_at": now}
    return apply_status(ctx, row, "canceled").subscription


def schedule_stripe_cancel(ctx: BillingContext, mode: str, gateway_subscription_id: str) -> None:
    """`cancel_at_period_end` on Stripe (not in the seed Protocol)."""
    import stripe

    key = ctx.config.get_secret("stripe", "secret_key", mode)
    if not key:
        raise GatewayNotConfigured(f"Stripe sem chave para o modo '{mode}'.")
    try:
        stripe.Subscription.modify(gateway_subscription_id, cancel_at_period_end=True, api_key=key)
    except stripe.StripeError as exc:
        raise PaymentGatewayError("stripe", str(exc), status=getattr(exc, "http_status", None)) from exc


# ── payments ────────────────────────────────────────────────────────────


def record_payment(
    ctx: BillingContext,
    row: dict[str, Any],
    *,
    gateway_payment_id: str,
    status: str,
    gross_cents: int,
    currency: str,
    fee_cents: Optional[int],
    billing_method: Optional[str],
    paid_at: Optional[datetime],
    gateway_charge_id: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert one charge by (gateway, gateway_payment_id); book its fee."""
    currency = currency.upper()
    gateway = str(row.get("gateway"))
    mode = str(row.get("gateway_mode") or "live")
    fee_known = fee_cents is not None
    fee = int(fee_cents or 0)
    now = ctx.clock()
    day = (paid_at or now).date()
    conversion = fx_service.conversion_for(ctx.db, ctx.fx, currency, day)
    payload: dict[str, Any] = {
        "org_id": row["org_id"],
        "subscription_id": row["id"],
        "gateway": gateway,
        "gateway_mode": mode,
        "gateway_payment_id": gateway_payment_id,
        "gateway_charge_id": gateway_charge_id,
        "status": status,
        "billing_method": billing_method,
        "currency": currency,
        "gross_cents": int(gross_cents),
        "fee_cents": fee,
        "net_cents": int(gross_cents) - fee,
        "fee_pending": status == "paid" and not fee_known,
        "fx_pending": conversion.pending,
        "fx_rate": str(conversion.fx_rate) if conversion.fx_rate is not None else None,
        "fx_quote_date": conversion.fx_quote_date.isoformat() if conversion.fx_quote_date else None,
        "gross_brl": _brl(conversion, gross_cents),
        "fee_brl": _brl(conversion, fee),
        "paid_at": paid_at.isoformat() if paid_at else None,
        "updated_at": now.isoformat(),
    }
    existing = (
        ctx.db.table("billing_payments")
        .select("id, status, fee_cents, fee_pending")
        .eq("gateway", gateway)
        .eq("gateway_payment_id", gateway_payment_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing:
        current = existing[0]
        if not fee_known and not current.get("fee_pending"):
            # Keep a fee we already know; this delivery just didn't carry it.
            payload["fee_cents"] = int(current.get("fee_cents") or 0)
            payload["net_cents"] = int(gross_cents) - payload["fee_cents"]
            payload["fee_brl"] = _brl(conversion, payload["fee_cents"])
            payload["fee_pending"] = False
        ctx.db.table("billing_payments").update(payload).eq("id", current["id"]).execute()
        saved = {**current, **payload}
    else:
        inserted = ctx.db.table("billing_payments").insert(payload).execute().data or []
        saved = inserted[0] if inserted else payload
    if status == "paid" and not payload["fee_pending"] and payload["fee_cents"] > 0:
        book_fee(ctx, saved, conversion)
    return saved


def _brl(conversion: fx_service.Conversion, cents: int) -> Optional[str]:
    if conversion.pending:
        return None
    amount = Decimal(int(cents)) / 100
    if conversion.fx_rate is None:
        return str(amount.quantize(Decimal("0.01")))
    return str(conversion.to_brl(amount, places="0.01"))


def book_fee(ctx: BillingContext, payment: dict[str, Any], conversion: fx_service.Conversion) -> None:
    """One `cost_ledger` row per settled charge fee (idempotent by reference)."""
    reference_id = f"{payment['gateway']}:{payment['gateway_payment_id']}"
    exists = (
        ctx.db.table("cost_ledger")
        .select("id")
        .eq("category", "payment_fee")
        .eq("reference_type", "billing_payment")
        .eq("reference_id", reference_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if exists:
        return
    amount = Decimal(int(payment["fee_cents"])) / 100
    currency = str(payment["currency"]).upper()
    row: dict[str, Any] = {
        "org_id": payment["org_id"],
        "category": "payment_fee",
        "step": f"billing.{payment['gateway']}",
        "reference_type": "billing_payment",
        "reference_id": reference_id,
        "amount_native": str(amount),
        "currency": currency,
    }
    if currency == "BRL":
        row.update({"amount_brl": str(amount), "fx_pending": False})
    elif conversion.pending:
        row.update({"fx_pending": True})
    else:
        row.update(
            {
                "fx_pending": False,
                "fx_rate": str(conversion.fx_rate),
                "fx_quote_date": conversion.fx_quote_date.isoformat(),
                "amount_brl": str(conversion.to_brl(amount)),
            }
        )
    ctx.db.table("cost_ledger").insert(row).execute()


__all__ = [
    "BillingError",
    "DB_TO_STATE",
    "IllegalTransition",
    "LICENSED_STATUSES",
    "ORG_ADMIN_ROLES",
    "TERMINAL_STATUSES",
    "TransitionOutcome",
    "UnmanagedSubscription",
    "add_cycle",
    "apply_status",
    "book_fee",
    "cancel",
    "ensure_license",
    "find_by_gateway_id",
    "get_subscription",
    "onboard_manual",
    "parse_ts",
    "record_payment",
    "remember_customer",
    "renew_manual",
    "start_checkout",
    "validate_price_for_org_type",
]
