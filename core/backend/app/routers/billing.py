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

from app.database import get_admin_client
from app.dependencies import get_current_user
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
    db = get_admin_client()

    # Resolve the user's organization
    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organizacao nao encontrada")

    org_id = profile.data["org_id"]

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
async def stripe_webhook(request: Request):
    """Receive and process Stripe webhook events.

    This endpoint does NOT require authentication.  Instead it verifies the
    Stripe-Signature header to ensure the payload was sent by Stripe.
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
    else:
        logger.debug("Unhandled webhook event type: %s", event_type)

    # Always return 200 so Stripe does not retry handled events
    return {"received": True}


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
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organizacao nao encontrada")

    org_id = profile.data["org_id"]

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
# GET /api/billing/invoices
# ---------------------------------------------------------------------------

@router.get("/invoices")
async def list_invoices(
    limit: int = 12,
    authorization: Optional[str] = Header(None),
):
    """List recent invoices for the current user's organization."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organizacao nao encontrada")

    org_id = profile.data["org_id"]

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
            "period_start": billing_service._ts(inv.period_start),
            "period_end": billing_service._ts(inv.period_end),
            "hosted_invoice_url": inv.hosted_invoice_url,
            "invoice_pdf": inv.invoice_pdf,
            "created": billing_service._ts(inv.created),
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
    db = get_admin_client()

    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organizacao nao encontrada")

    org_id = profile.data["org_id"]
    status = billing_service.get_billing_status(org_id)
    return {"data": status}
