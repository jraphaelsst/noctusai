"""
NoctusAI Core — Billing service.

Orchestrates Stripe SDK calls with Supabase persistence. The billing router
delegates all business logic here so endpoints stay thin.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Dict

from fastapi import HTTPException

from app.config import settings
from app.database import get_admin_client
from app.services import stripe_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_stripe_timestamp(epoch: Optional[int]) -> Optional[str]:
    """Convert a Unix epoch (from Stripe) to an ISO-8601 string or None."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Customer management
# ---------------------------------------------------------------------------

def ensure_customer(org_id: str) -> str:
    """Return the Stripe customer ID for an org, creating one if needed.

    Looks up the subscription row for the org.  If `stripe_customer_id` is
    already set, returns it.  Otherwise creates a Stripe Customer using the
    org name/email and persists the ID back to the subscription row.

    If the org has no subscription yet, the caller must create one first
    (via the admin subscriptions router).
    """
    db = get_admin_client()

    # Get org details for Stripe metadata
    org = db.table("organizations").select("id, nome, slug").eq("id", org_id).single().execute()
    if not org.data:
        raise HTTPException(status_code=404, detail="Organizacao nao encontrada")

    # Check existing subscription for a stripe_customer_id
    sub = (
        db.table("subscriptions")
        .select("id, stripe_customer_id")
        .eq("org_id", org_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if sub.data and sub.data[0].get("stripe_customer_id"):
        return sub.data[0]["stripe_customer_id"]

    # Create customer on Stripe
    org_name = org.data.get("nome") or org.data.get("slug") or org_id
    customer = stripe_service.create_customer(
        email=f"billing+{org.data.get('slug', org_id)}@noctus.ai",
        name=org_name,
        metadata={"org_id": org_id, "org_slug": org.data.get("slug", "")},
    )

    # Persist customer id on the subscription (if one exists)
    if sub.data:
        db.table("subscriptions").update(
            {"stripe_customer_id": customer.id}
        ).eq("id", sub.data[0]["id"]).execute()

    logger.info("Stripe customer %s ensured for org %s", customer.id, org_id)
    return customer.id


# ---------------------------------------------------------------------------
# Start subscription (checkout)
# ---------------------------------------------------------------------------

def start_subscription(
    *,
    org_id: str,
    plan_id: str,
    billing_cycle: str = "monthly",
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> str:
    """Create a Stripe Checkout Session for a plan and return the checkout URL.

    1. Look up the plan to get the appropriate Stripe Price ID.
    2. Ensure the org has a Stripe customer.
    3. Create a Checkout Session.
    """
    db = get_admin_client()

    # Resolve plan and price
    plan = db.table("plans").select("*").eq("id", plan_id).single().execute()
    if not plan.data:
        raise HTTPException(status_code=404, detail="Plano nao encontrado")

    if billing_cycle == "yearly":
        price_id = plan.data.get("stripe_price_id_yearly")
    else:
        price_id = plan.data.get("stripe_price_id_monthly")

    if not price_id:
        raise HTTPException(
            status_code=422,
            detail=f"Plano '{plan.data['nome']}' nao possui preco Stripe configurado para ciclo {billing_cycle}.",
        )

    # Customer
    customer_id = ensure_customer(org_id)

    # URLs
    base = settings.app_base_url.rstrip("/")
    _success = success_url or f"{base}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    _cancel = cancel_url or f"{base}/billing/cancel"

    session = stripe_service.create_checkout_session(
        customer_id=customer_id,
        price_id=price_id,
        success_url=_success,
        cancel_url=_cancel,
        metadata={
            "org_id": org_id,
            "plan_id": plan_id,
            "billing_cycle": billing_cycle,
        },
    )

    logger.info(
        "Checkout session %s created for org=%s plan=%s cycle=%s",
        session.id, org_id, plan_id, billing_cycle,
    )
    return session.url


# ---------------------------------------------------------------------------
# Cancel subscription
# ---------------------------------------------------------------------------

def cancel_subscription(org_id: str, *, at_period_end: bool = True) -> Dict[str, Any]:
    """Cancel the active Stripe subscription for an org.

    Returns the updated local subscription record.
    """
    db = get_admin_client()

    sub = (
        db.table("subscriptions")
        .select("id, stripe_subscription_id, stripe_customer_id")
        .eq("org_id", org_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not sub.data:
        raise HTTPException(status_code=404, detail="Nenhuma assinatura ativa encontrada para esta organizacao")

    record = sub.data[0]
    stripe_sub_id = record.get("stripe_subscription_id")

    if stripe_sub_id:
        stripe_service.cancel_subscription(stripe_sub_id, at_period_end=at_period_end)

    # If canceling immediately, mark as canceled now
    if not at_period_end:
        update_data = {
            "status": "canceled",
            "canceled_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        # Will be finalized by the webhook when the period actually ends
        update_data = {
            "canceled_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"cancel_at_period_end": True},
        }

    result = db.table("subscriptions").update(update_data).eq("id", record["id"]).execute()
    logger.info("Subscription %s cancel requested for org %s (at_period_end=%s)", record["id"], org_id, at_period_end)
    return result.data[0] if result.data else record


# ---------------------------------------------------------------------------
# Billing status
# ---------------------------------------------------------------------------

def get_billing_status(org_id: str) -> Dict[str, Any]:
    """Return a consolidated billing status view for an org.

    Includes plan info, subscription state, Stripe customer and
    upcoming invoice details.
    """
    db = get_admin_client()

    sub = (
        db.table("subscriptions")
        .select("*, plans(*)")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    subscription = sub.data[0] if sub.data else None

    status: Dict[str, Any] = {
        "has_subscription": subscription is not None,
        "subscription": subscription,
        "stripe_customer_id": subscription.get("stripe_customer_id") if subscription else None,
        "stripe_subscription_id": subscription.get("stripe_subscription_id") if subscription else None,
        "plan": subscription.get("plans") if subscription else None,
        "next_invoice": None,
        "payment_method": None,
    }

    # Enrich with Stripe data if we have IDs
    stripe_customer_id = status["stripe_customer_id"]
    if stripe_customer_id and settings.stripe_secret_key:
        try:
            import stripe as _stripe
            _stripe.api_key = settings.stripe_secret_key

            # Upcoming invoice
            try:
                upcoming = _stripe.Invoice.upcoming(customer=stripe_customer_id)
                status["next_invoice"] = {
                    "amount_due": upcoming.amount_due,
                    "currency": upcoming.currency,
                    "period_start": format_stripe_timestamp(upcoming.period_start),
                    "period_end": format_stripe_timestamp(upcoming.period_end),
                    "next_payment_attempt": format_stripe_timestamp(upcoming.next_payment_attempt),
                }
            except _stripe.InvalidRequestError as exc:
                # No upcoming invoice (e.g. free plan, no active sub).
                logger.debug("billing_service: no upcoming Stripe invoice for customer=%s (%s)", stripe_customer_id, exc)

            # Default payment method
            customer = _stripe.Customer.retrieve(stripe_customer_id)
            pm_id = customer.invoice_settings.default_payment_method if customer.invoice_settings else None
            if pm_id:
                pm = _stripe.PaymentMethod.retrieve(pm_id)
                if pm.card:
                    status["payment_method"] = {
                        "brand": pm.card.brand,
                        "last4": pm.card.last4,
                        "exp_month": pm.card.exp_month,
                        "exp_year": pm.card.exp_year,
                    }
        except Exception as exc:
            logger.warning("Failed to enrich billing status from Stripe: %s", exc)

    return status


# ---------------------------------------------------------------------------
# Webhook event handlers
# ---------------------------------------------------------------------------

def handle_checkout_completed(event_data: dict) -> None:
    """Handle checkout.session.completed — activate subscription."""
    db = get_admin_client()
    session = event_data.get("object", {})

    org_id = session.get("metadata", {}).get("org_id")
    plan_id = session.get("metadata", {}).get("plan_id")
    stripe_sub_id = session.get("subscription")
    stripe_customer_id = session.get("customer")

    if not org_id or not plan_id:
        logger.warning("checkout.session.completed missing org_id or plan_id in metadata")
        return

    # Upsert: find existing active sub or create a new one
    existing = (
        db.table("subscriptions")
        .select("id")
        .eq("org_id", org_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )

    update_payload = {
        "plan_id": plan_id,
        "status": "active",
        "stripe_subscription_id": stripe_sub_id,
        "stripe_customer_id": stripe_customer_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "canceled_at": None,
    }

    if existing.data:
        db.table("subscriptions").update(update_payload).eq("id", existing.data[0]["id"]).execute()
        logger.info("Subscription %s updated from checkout for org %s", existing.data[0]["id"], org_id)
    else:
        insert_payload = {**update_payload, "org_id": org_id}
        db.table("subscriptions").insert(insert_payload).execute()
        logger.info("New subscription created from checkout for org %s", org_id)


def handle_subscription_updated(event_data: dict) -> None:
    """Handle customer.subscription.updated — sync status changes."""
    db = get_admin_client()
    sub_obj = event_data.get("object", {})
    stripe_sub_id = sub_obj.get("id")
    stripe_status = sub_obj.get("status")  # active, past_due, canceled, unpaid, etc.

    if not stripe_sub_id:
        return

    # Map Stripe statuses to our internal statuses
    status_map = {
        "active": "active",
        "trialing": "trial",
        "canceled": "canceled",
        "past_due": "active",      # still active but needs attention
        "unpaid": "expired",
        "incomplete": "trial",
        "incomplete_expired": "expired",
    }
    local_status = status_map.get(stripe_status, "active")

    update_payload: Dict[str, Any] = {"status": local_status}

    current_period_end = sub_obj.get("current_period_end")
    if current_period_end:
        update_payload["expires_at"] = format_stripe_timestamp(current_period_end)

    if sub_obj.get("cancel_at_period_end"):
        update_payload["metadata"] = {"cancel_at_period_end": True}

    db.table("subscriptions").update(update_payload).eq(
        "stripe_subscription_id", stripe_sub_id
    ).execute()

    logger.info("Subscription %s synced: stripe_status=%s local_status=%s", stripe_sub_id, stripe_status, local_status)


def handle_subscription_deleted(event_data: dict) -> None:
    """Handle customer.subscription.deleted — mark as canceled."""
    db = get_admin_client()
    sub_obj = event_data.get("object", {})
    stripe_sub_id = sub_obj.get("id")

    if not stripe_sub_id:
        return

    db.table("subscriptions").update({
        "status": "canceled",
        "canceled_at": datetime.now(timezone.utc).isoformat(),
    }).eq("stripe_subscription_id", stripe_sub_id).execute()

    logger.info("Subscription %s marked as canceled (deleted in Stripe)", stripe_sub_id)


def handle_invoice_payment_failed(event_data: dict) -> None:
    """Handle invoice.payment_failed — log for alerting.

    The subscription status will be updated by customer.subscription.updated
    when Stripe moves it to past_due/unpaid, so we only log here.
    """
    invoice = event_data.get("object", {})
    customer_id = invoice.get("customer")
    attempt = invoice.get("attempt_count", 0)
    logger.warning(
        "Invoice payment failed for customer %s (attempt %s, invoice %s)",
        customer_id, attempt, invoice.get("id"),
    )
