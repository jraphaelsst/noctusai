"""
Billing Router — Stripe-powered billing for NoctusAI organizations.

GET    /api/billing/plans            — Public: sellable plans + prices + offered gateways
POST   /api/billing/subscribe        — Org admin: start a managed subscription (hosted checkout)
GET    /api/billing/subscription     — Org admin: the org's managed subscriptions + payments
POST   /api/billing/checkout  — LEGACY Stripe Checkout off plans.stripe_price_id_* (returns checkout_url)
POST   /api/billing/webhook   — Stripe webhook (no auth, signature verified, EventInbox-idempotent)
POST   /api/billing/webhooks/asaas — Asaas webhook (no auth, asaas-access-token, EventInbox-idempotent)
POST   /api/billing/portal    — Create Stripe Customer Portal session
GET    /api/billing/invoices  — List invoices for current org
GET    /api/billing/status    — Billing status (plan, next invoice, payment method)

Webhook deliveries are recorded in `public.payment_events` (migration 050),
which is also the idempotency inbox. `public.billing_events` (migration 029)
is the pre-050 log; it is no longer written and stays as history.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.api.rate_limit_policies import DEFAULT_AUTH_RL
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from noctusai_lib.primitives.tasks import NoRunningLoopError, schedule_coro

from app.config import settings
from app.database import get_admin_client
from app.dependencies import get_current_user, get_org_id
from app.rate_limit import limiter
from app.services import billing_service, billing_subscriptions, billing_webhooks, stripe_service
from app.services.trusted_auth import get_trusted_db, require_org_admin_dep
from app.services.billing_context import BillingContext, get_billing_context
from app.services.billing_events import (
    ParsedGatewayEvent,
    WebhookAuthError,
    WebhookNotConfigured,
    parse_for_any_mode,
)
from app.schemas.billing import CheckoutRequest, PortalRequest, CancelRequest
from app.schemas.billing_admin import SubscribeRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["Billing"])


# ---------------------------------------------------------------------------
# POST /api/billing/checkout
# ---------------------------------------------------------------------------

@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, authorization: Optional[str] = Header(None)):
    """LEGACY: Stripe Checkout off `plans.stripe_price_id_*` + env keys.

    NOC-REMEDIATE[billing-legacy-checkout]: superseded by `POST
    /api/billing/subscribe` (managed subscriptions, plan_prices, UI-set
    keys). Kept until no client calls it; the admin UI and Pricing page
    already use `/subscribe`. — 2026-09-16

    Returns a ``checkout_url`` that the frontend should redirect to.
    """
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)

    checkout_url = billing_service.start_subscription(
        org_id=org_id,
        plan_id=body.plan_id,
        billing_cycle=body.billing_cycle,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )

    return {"data": {"checkout_url": checkout_url}}


# ---------------------------------------------------------------------------
# POST /api/billing/webhook
# ---------------------------------------------------------------------------

# Events whose org-facing side effects (outbound webhook, email) we fire.
_HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
}


def _run_event(ctx: BillingContext, event: ParsedGatewayEvent) -> billing_webhooks.EventOutcome:
    try:
        return billing_webhooks.process_event(ctx, event)
    except Exception as exc:  # noqa: BLE001 — claim already released + logged
        raise HTTPException(status_code=500, detail="Falha ao processar o evento; será reenviado.") from exc


@router.post("/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def stripe_webhook(request: Request, ctx: BillingContext = Depends(get_billing_context)):
    """Receive and process Stripe webhook events.

    No user auth: the Stripe-Signature header is verified with the Stripe
    SDK (the documented carve-out from `webhook_endpoint`) against the
    webhook secret of every configured mode. The rate-limit decorator is
    webhook-compliance pin #4 (`KB § PATTERNS/webhook-signatures.md`).
    A duplicate event id is a no-op (`payment_events` inbox).
    """
    payload = await request.body()
    try:
        event = parse_for_any_mode(
            "stripe", payload, request.headers, ctx.config.secrets_by_mode("stripe", "webhook_secret")
        )
    except WebhookNotConfigured as exc:
        logger.error("stripe webhook: %s", exc)
        raise HTTPException(status_code=503, detail="Webhook secret não configurado.") from exc
    except WebhookAuthError as exc:
        raise HTTPException(status_code=400, detail=f"Assinatura do webhook inválida: {exc}") from exc

    logger.info("Webhook received: type=%s id=%s mode=%s", event.event_type, event.event_id, event.mode)
    outcome = _run_event(ctx, event)

    if outcome.status == "processed" and event.event_type in _HANDLED_EVENTS:
        event_data = event.payload.get("data", {})
        if event.event_type == "invoice.payment_failed":
            _notify_billing_event(event.event_type, event_data, ctx.db)
        _dispatch_webhook(event.event_type, event_data, ctx.db)

    # 200 for processed, ignored and duplicate alike: none should be retried.
    return {"received": True, "status": outcome.status}


@router.post("/webhooks/asaas")
@limiter.limit(settings.webhook_rate_limit)
async def asaas_webhook(request: Request, ctx: BillingContext = Depends(get_billing_context)):
    """Receive Asaas notifications (static `asaas-access-token` header).

    Asaas pauses a webhook's delivery queue after repeated non-2xx answers,
    so only authentication/config failures are non-2xx; an event we don't
    act on is a 200 `ignored`.
    """
    payload = await request.body()
    try:
        event = parse_for_any_mode(
            "asaas", payload, request.headers, ctx.config.secrets_by_mode("asaas", "webhook_token")
        )
    except WebhookNotConfigured as exc:
        logger.error("asaas webhook: %s", exc)
        raise HTTPException(status_code=503, detail="Webhook Asaas não configurado.") from exc
    except WebhookAuthError as exc:
        raise HTTPException(status_code=401, detail="Token do webhook inválido.") from exc

    logger.info("Asaas webhook: event=%s id=%s mode=%s", event.event_type, event.event_id, event.mode)
    outcome = _run_event(ctx, event)
    return {"received": True, "status": outcome.status}


# ---------------------------------------------------------------------------
# Public plans + managed self-serve subscription
# ---------------------------------------------------------------------------


@router.get("/plans")
@limiter.limit(DEFAULT_AUTH_RL)
async def public_plans(request: Request, ctx: BillingContext = Depends(get_billing_context)):
    """Sellable plans with their active prices + which gateways are offered.

    Public (the pricing page is shown before signup). Carries no secret and
    no Stripe price id.
    """
    plans = list(iter_paged_rows(
        lambda start, end: ctx.db.table("plans").select(
            "id, nome, slug, descricao, audience, trial_days, product_id, features, max_users, max_products, created_at"
        ).eq("ativo", True).order("id").range(start, end).execute().data,
        label="sellable plans",
    ))
    prices = list(iter_paged_rows(
        lambda start, end: ctx.db.table("plan_prices").select(
            "id, plan_id, billing_cycle, currency, amount_cents"
        ).eq("ativo", True).order("id").range(start, end).execute().data,
        label="sellable prices",
    ))
    plans.sort(key=lambda p: str(p.get("created_at") or ""))
    # Explicit projection: a public response must never grow a column
    # (e.g. a Stripe price id) because someone widened the select.
    plan_keys = (
        "id", "nome", "slug", "descricao", "audience", "trial_days", "product_id", "features", "max_users", "max_products",
    )
    price_keys = ("id", "billing_cycle", "currency", "amount_cents")
    by_plan: dict[str, list] = {}
    for price in prices:
        by_plan.setdefault(str(price["plan_id"]), []).append({k: price.get(k) for k in price_keys})
    sellable = [
        {**{k: plan.get(k) for k in plan_keys}, "prices": by_plan[str(plan["id"])]}
        for plan in plans
        if by_plan.get(str(plan["id"]))
    ]
    gateways = [g for g in ("stripe", "asaas") if ctx.config.gateway_enabled(g)]
    return {"data": {"plans": sellable, "gateways": gateways}}


def _safe_return_url(base_url: str, candidate: Optional[str], fallback_path: str) -> str:
    """Only our own origin may be a post-checkout redirect (no open redirect)."""
    base = base_url.rstrip("/")
    if candidate and (candidate == base or candidate.startswith(base + "/")):
        return candidate
    return f"{base}{fallback_path}"


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    auth: AuthContext = Depends(require_org_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
    db: Any = Depends(get_trusted_db),
):
    """Start a managed subscription for the caller's org; returns the payment page."""
    users = db.table("noctus_users").select("email").eq("id", str(auth.user_id)).limit(1).execute().data or []
    payer_email = (users[0].get("email") if users else None) or ""
    try:
        result = billing_subscriptions.start_checkout(
            ctx,
            org_id=str(auth.org_id),
            payer_email=payer_email,
            plan_price_id=body.plan_price_id,
            gateway=body.gateway,
            billing_method=body.billing_method,
            tax_id=body.tax_id,
            success_url=_safe_return_url(ctx.settings.app_base_url, body.success_url, "/billing/success"),
            cancel_url=_safe_return_url(ctx.settings.app_base_url, body.cancel_url, "/billing/cancel"),
        )
    except billing_subscriptions.BillingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"data": result}


@router.get("/subscription")
async def my_subscription(
    auth: AuthContext = Depends(require_org_admin_dep),
    ctx: BillingContext = Depends(get_billing_context),
):
    """The org's managed subscriptions and their last payments (agency admin view)."""
    org_id = str(auth.org_id)
    rows = (
        ctx.db.table("subscriptions")
        .select(
            "id, status, plan_id, gateway, billing_cycle, billing_method, currency, amount_cents, "
            "current_period_end, trial_ends_at, grace_ends_at, cancel_at_period_end, payment_url, "
            "created_at, plans(id, nome)"
        )
        .eq("org_id", org_id)
        .eq("automation_managed", True)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
        .data
        or []
    )
    payments = (
        ctx.db.table("billing_payments")
        .select("id, status, gateway, billing_method, currency, gross_cents, fee_cents, net_cents, paid_at, created_at")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    return {"data": {"subscriptions": rows, "payments": payments}}


def _dispatch_webhook(event_type: str, event_data: dict, db: Any) -> None:
    """Dispatch billing event to registered webhook endpoints (best-effort, fire-and-forget)."""
    org_id = None
    try:
        from app.services import webhook_delivery

        session_obj = event_data.get("object", {})
        stripe_customer_id = session_obj.get("customer")

        # Resolve org_id from metadata or subscription lookup
        org_id = session_obj.get("metadata", {}).get("org_id")
        if not org_id and stripe_customer_id:
            sub = (
                db.table("subscriptions")
                .select("org_id")
                .eq("stripe_customer_id", stripe_customer_id)
                .limit(1)
                .execute()
            )
            if sub.data:
                org_id = sub.data[0]["org_id"]

        if not org_id:
            return

        payload = {
            "event": event_type,
            "data": event_data,
        }

        # Schedule as fire-and-forget coroutine via the canonical helper
        # (logs exceptions via add_done_callback — never silent).
        try:
            schedule_coro(
                webhook_delivery.dispatch(org_id, event_type, payload, db=db),
                logger=logger,
                name=f"billing_webhook_{event_type}",
            )
        except NoRunningLoopError as exc:
            # No running loop (shouldn't happen in FastAPI, but be safe)
            logger.warning(
                "billing: no running asyncio loop to dispatch webhook (%s); event %s for org=%s skipped",
                exc, event_type, org_id,
            )
    except Exception as exc:
        logger.warning(
            "billing: webhook dispatch failed (%s); event %s for org=%s skipped",
            exc, event_type, org_id,
        )


def _notify_billing_event(event_type: str, event_data: dict, db: Any) -> None:
    """Send email notification for billing events (best-effort)."""
    try:
        from app.services.email_service import send_billing_alert

        session_obj = event_data.get("object", {})
        stripe_customer_id = session_obj.get("customer")
        if not stripe_customer_id:
            return

        sub = (
            db.table("subscriptions")
            .select("org_id")
            .eq("stripe_customer_id", stripe_customer_id)
            .limit(1)
            .execute()
        )
        if not sub.data:
            return
        org_id = sub.data[0]["org_id"]

        org = db.table("organizations").select("nome, owner_id").eq("id", org_id).single().execute()
        if not org.data:
            return

        owner = db.table("noctus_users").select("email").eq("id", org.data["owner_id"]).single().execute()
        if not owner.data:
            return

        send_billing_alert(
            to=owner.data["email"],
            event_type=event_type,
            org_name=org.data["nome"],
        )
    except Exception as exc:
        logger.warning(
            "billing: notification send failed (%s); event %s for org=%s",
            exc, event_type, event_data.get("org_id"),
        )


# ---------------------------------------------------------------------------
# POST /api/billing/portal
# ---------------------------------------------------------------------------

@router.post("/portal")
async def create_portal(body: PortalRequest, authorization: Optional[str] = Header(None)):
    """Create a Stripe Customer Portal session for the user's organization.

    Returns a ``portal_url`` that the frontend should redirect to.
    """
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)

    # Get the Stripe customer ID for this org
    customer_id = billing_service.ensure_customer(org_id)

    from app.config import settings
    return_url = body.return_url or f"{settings.app_base_url.rstrip('/')}/billing"

    session = stripe_service.create_portal_session(
        customer_id=customer_id,
        return_url=return_url,
    )

    return {"data": {"portal_url": session.url}}


@router.post("/cancel")
async def cancel_subscription(body: CancelRequest, authorization: Optional[str] = Header(None)):
    """Cancel the active subscription for the current user's organization.

    By default cancels at the end of the billing period (``at_period_end=True``).
    """
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)

    result = billing_service.cancel_subscription(org_id, at_period_end=body.at_period_end)

    # Audit log (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org_id,
            action="cancel", resource_type="subscription",
            resource_id=result.get("id"),
        )
    except Exception as exc:
        logger.warning("billing: cancel-subscription audit log failed for sub_id=%s (%s); cancellation succeeded", result.get("id"), exc)

    return {"data": result}


# ---------------------------------------------------------------------------
# GET /api/billing/invoices
# ---------------------------------------------------------------------------

@router.get("/invoices")
async def list_invoices(
    limit: int = 12,
    authorization: Optional[str] = Header(None),
):
    """List recent invoices for the current user's organization."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    # Get stripe customer id from subscription
    sub = (
        db.table("subscriptions")
        .select("stripe_customer_id")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    customer_id = sub.data[0].get("stripe_customer_id") if sub.data else None
    if not customer_id:
        return {"data": []}

    invoices = stripe_service.get_invoices(customer_id, limit=min(limit, 100))

    # Transform to a leaner shape for the frontend
    invoice_list = [
        {
            "id": inv.id,
            "number": inv.number,
            "status": inv.status,
            "amount_due": inv.amount_due,
            "amount_paid": inv.amount_paid,
            "currency": inv.currency,
            "period_start": billing_service.format_stripe_timestamp(inv.period_start),
            "period_end": billing_service.format_stripe_timestamp(inv.period_end),
            "hosted_invoice_url": inv.hosted_invoice_url,
            "invoice_pdf": inv.invoice_pdf,
            "created": billing_service.format_stripe_timestamp(inv.created),
        }
        for inv in invoices
    ]

    return {"data": invoice_list}


# ---------------------------------------------------------------------------
# GET /api/billing/status
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_billing_status(authorization: Optional[str] = Header(None)):
    """Return consolidated billing status for the current user's organization.

    Includes plan details, subscription state, next invoice, and payment method.
    """
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    status = billing_service.get_billing_status(org_id)
    return {"data": status}
