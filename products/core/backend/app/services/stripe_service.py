"""
NoctusAI Core — Stripe SDK wrapper.

Thin abstraction over the Stripe Python SDK. Every function here maps to
a single Stripe API call so the billing service (and tests) never import
stripe directly.
"""
import logging
from typing import Optional, List

import stripe
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK configuration — key is set lazily so tests can override settings
# ---------------------------------------------------------------------------

def _ensure_api_key() -> None:
    """Set the module-level Stripe API key from settings. Raises if missing."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Serviço de pagamento indisponível. Configure STRIPE_SECRET_KEY.",
        )
    stripe.api_key = settings.stripe_secret_key


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def create_customer(
    *,
    email: str,
    name: str,
    metadata: Optional[dict] = None,
) -> stripe.Customer:
    """Create a Stripe Customer and return the full object."""
    _ensure_api_key()
    try:
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata=metadata or {},
        )
        logger.info("Stripe customer created: %s", customer.id)
        return customer
    except stripe.StripeError as exc:
        logger.error("Stripe create_customer error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Erro ao criar cliente no Stripe.",
        ) from exc


# ---------------------------------------------------------------------------
# Checkout Sessions
# ---------------------------------------------------------------------------

def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    metadata: Optional[dict] = None,
) -> stripe.checkout.Session:
    """Create a Stripe Checkout Session in subscription mode."""
    _ensure_api_key()
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata or {},
        )
        logger.info("Checkout session created: %s for customer %s", session.id, customer_id)
        return session
    except stripe.StripeError as exc:
        logger.error("Stripe create_checkout_session error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Erro ao criar sessão de checkout.",
        ) from exc


# ---------------------------------------------------------------------------
# Customer Portal Sessions
# ---------------------------------------------------------------------------

def create_portal_session(
    *,
    customer_id: str,
    return_url: str,
) -> stripe.billing_portal.Session:
    """Create a Stripe Customer Portal session so the customer can manage billing."""
    _ensure_api_key()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        logger.info("Portal session created for customer %s", customer_id)
        return session
    except stripe.StripeError as exc:
        logger.error("Stripe create_portal_session error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Erro ao criar portal de gerenciamento.",
        ) from exc


# ---------------------------------------------------------------------------
# Subscription cancellation
# ---------------------------------------------------------------------------

def cancel_subscription(
    stripe_subscription_id: str,
    *,
    at_period_end: bool = True,
) -> stripe.Subscription:
    """Cancel a Stripe Subscription (at period end by default)."""
    _ensure_api_key()
    try:
        if at_period_end:
            sub = stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True,
            )
        else:
            sub = stripe.Subscription.cancel(stripe_subscription_id)
        logger.info(
            "Stripe subscription %s canceled (at_period_end=%s)",
            stripe_subscription_id, at_period_end,
        )
        return sub
    except stripe.StripeError as exc:
        logger.error("Stripe cancel_subscription error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Erro ao cancelar assinatura no Stripe.",
        ) from exc


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

def get_invoices(
    customer_id: str,
    *,
    limit: int = 24,
) -> List[stripe.Invoice]:
    """Return recent invoices for a Stripe customer."""
    _ensure_api_key()
    try:
        invoices = stripe.Invoice.list(customer=customer_id, limit=limit)
        return invoices.data
    except stripe.StripeError as exc:
        logger.error("Stripe get_invoices error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Erro ao buscar faturas.",
        ) from exc


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def construct_webhook_event(
    payload: bytes,
    sig_header: str,
) -> stripe.Event:
    """Verify the Stripe webhook signature and return the parsed Event.

    Raises HTTPException 400 on invalid signature so the router can return
    an appropriate response to Stripe.
    """
    if not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook secret não configurado.",
        )
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret,
        )
        return event
    except stripe.SignatureVerificationError as exc:
        logger.warning("Webhook signature verification failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Assinatura do webhook inválida.",
        ) from exc
    except ValueError as exc:
        logger.warning("Webhook payload decode error: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Payload do webhook inválido.",
        ) from exc
