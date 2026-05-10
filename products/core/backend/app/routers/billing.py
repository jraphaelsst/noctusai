"""
Billing Router — Stripe-powered billing for NoctusAI organizations.

POST   /api/billing/checkout  — Create Stripe Checkout session (returns checkout_url)
POST   /api/billing/webhook   — Stripe webhook handler (no auth, signature verified)
POST   /api/billing/portal    — Create Stripe Customer Portal session
GET    /api/billing/invoices  — List invoices for current org
GET    /api/billing/status    — Billing status (plan, next invoice, payment method)

-- Supabase SQL to create the billing_events table (immutable webhook log):
--
-- CREATE TABLE billing_events (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   stripe_event_id text UNIQUE NOT NULL,
--   event_type text NOT NULL,
--   stripe_customer_id text,
--   org_id uuid REFERENCES organizations(id),
--   payload jsonb NOT NULL DEFAULT '{}',
--   processed_at timestamptz NOT NULL DEFAULT now(),
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
--
-- CREATE INDEX idx_billing_events_type ON billing_events(event_type);
-- CREATE INDEX idx_billing_events_customer ON billing_events(stripe_customer_id);
-- CREATE INDEX idx_billing_events_org ON billing_events(org_id);
--
-- ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;
-- -- Only service role can insert; admins can read
-- CREATE POLICY "billing_events_admin_read" ON billing_events FOR SELECT USING (
--   auth.uid() IN (SELECT id FROM noctus_users WHERE role = 'admin')
-- );
-- -- No UPDATE or DELETE policies: events are immutable
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from noctusai_lib.primitives.tasks import NoRunningLoopError, schedule_coro

from app.config import settings
from app.database import get_admin_client
from app.dependencies import get_current_user, get_org_id
from app.rate_limit import limiter
from app.services import billing_service, stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/billing", tags=["Billing"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan_id: str = Field(..., description="UUID do plano desejado")
    billing_cycle: str = Field(
        default="monthly",
        pattern="^(monthly|yearly)$",
        description="Ciclo de cobranca: monthly ou yearly",
    )
    success_url: Optional[str] = Field(
        default=None,
        description="URL de redirecionamento apos pagamento bem-sucedido",
    )
    cancel_url: Optional[str] = Field(
        default=None,
        description="URL de redirecionamento se o usuario cancelar o checkout",
    )


class PortalRequest(BaseModel):
    return_url: Optional[str] = Field(
        default=None,
        description="URL de retorno apos sair do portal Stripe",
    )


# ---------------------------------------------------------------------------
# POST /api/billing/checkout
# ---------------------------------------------------------------------------

@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, authorization: Optional[str] = Header(None)):
    """Create a Stripe Checkout session for the user's organization.

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

# Events we process; others are logged but ignored
_HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
}


@router.post("/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def stripe_webhook(request: Request):
    """Receive and process Stripe webhook events.

    This endpoint does NOT require authentication.  Instead it verifies the
    Stripe-Signature header to ensure the payload was sent by Stripe.

    Stripe SDK is the carve-out from the canonical
    ``noctusai_lib.security.webhook_signatures.webhook_endpoint`` pattern
    (Stripe ships its own verifier; don't wrap it). The remaining 4 pins
    still apply — including this rate-limit decorator. See
    ``KB § PATTERNS/webhook-signatures.md``.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Header Stripe-Signature ausente")

    # Verify signature — raises HTTPException on failure
    event = stripe_service.construct_webhook_event(payload, sig_header)

    event_type = event.get("type", "unknown")
    event_id = event.get("id", "")
    event_data = event.get("data", {})

    logger.info("Webhook received: type=%s id=%s", event_type, event_id)

    # Persist event to billing_events table (immutable log)
    _log_billing_event(event_id, event_type, event_data)

    # Dispatch to handler
    if event_type == "checkout.session.completed":
        billing_service.handle_checkout_completed(event_data)
    elif event_type == "customer.subscription.updated":
        billing_service.handle_subscription_updated(event_data)
    elif event_type == "customer.subscription.deleted":
        billing_service.handle_subscription_deleted(event_data)
    elif event_type == "invoice.payment_failed":
        billing_service.handle_invoice_payment_failed(event_data)
        _notify_billing_event(event_type, event_data)
    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    # Fire webhook delivery to org endpoints (best-effort)
    if event_type in _HANDLED_EVENTS:
        _dispatch_webhook(event_type, event_data)

    # Always return 200 so Stripe does not retry handled events
    return {"received": True}


def _dispatch_webhook(event_type: str, event_data: dict) -> None:
    """Dispatch billing event to registered webhook endpoints (best-effort, fire-and-forget)."""
    org_id = None
    try:
        from app.services import webhook_delivery

        session_obj = event_data.get("object", {})
        stripe_customer_id = session_obj.get("customer")

        # Resolve org_id from metadata or subscription lookup
        org_id = session_obj.get("metadata", {}).get("org_id")
        if not org_id and stripe_customer_id:
            db = get_admin_client()
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
                webhook_delivery.dispatch(org_id, event_type, payload),
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


def _notify_billing_event(event_type: str, event_data: dict) -> None:
    """Send email notification for billing events (best-effort)."""
    try:
        from app.services.email_service import send_billing_alert

        session_obj = event_data.get("object", {})
        stripe_customer_id = session_obj.get("customer")
        if not stripe_customer_id:
            return

        db = get_admin_client()
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


def _log_billing_event(event_id: str, event_type: str, event_data: dict) -> None:
    """Insert an immutable record into billing_events for audit/debugging."""
    try:
        db = get_admin_client()
        session_obj = event_data.get("object", {})
        stripe_customer_id = session_obj.get("customer")

        # Try to resolve org_id from metadata or subscription lookup
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

        db.table("billing_events").insert({
            "stripe_event_id": event_id,
            "event_type": event_type,
            "stripe_customer_id": stripe_customer_id,
            "org_id": org_id,
            "payload": event_data,
        }).execute()
    except Exception as exc:
        # Never let logging failures break webhook processing
        logger.error("Failed to log billing event %s: %s", event_id, exc)


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


# ---------------------------------------------------------------------------
# POST /api/billing/cancel
# ---------------------------------------------------------------------------

class CancelRequest(BaseModel):
    at_period_end: bool = Field(
        default=True,
        description="Se True, cancela ao final do periodo atual. Se False, cancela imediatamente.",
    )


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
