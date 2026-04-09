"""
Stripe Service — Payment processing, refunds, payouts.

Wraps all Stripe API calls with graceful degradation: when stripe_secret_key
is not configured, returns mock success responses so the rest of the system
can operate without a live Stripe account.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import uuid4

from app.config import settings

logger = logging.getLogger(__name__)

_stripe = None

if settings.stripe_secret_key:
    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        _stripe = stripe
        logger.info("Stripe SDK initialized")
    except ImportError:
        logger.warning("stripe package not installed — running in mock mode")
else:
    logger.info("STRIPE_SECRET_KEY not configured — running in mock mode")


def _mock_id(prefix: str = "mock") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# Payment Intents
# ---------------------------------------------------------------------------

async def charge_payment_method(
    payment_method_id: str,
    amount_cents: int,
    description: str,
    currency: str = "brl",
) -> Dict[str, Any]:
    """Create and confirm a PaymentIntent. Returns {success, payment_intent_id, error}."""
    if not _stripe:
        return {
            "success": True,
            "payment_intent_id": _mock_id("pi"),
            "error": None,
        }

    try:
        intent = _stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            payment_method=payment_method_id,
            confirm=True,
            description=description,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )
        return {
            "success": intent.status == "succeeded",
            "payment_intent_id": intent.id,
            "error": None if intent.status == "succeeded" else f"Status: {intent.status}",
        }
    except Exception as e:
        logger.error("Stripe charge failed: %s", e)
        return {"success": False, "payment_intent_id": None, "error": str(e)}


# ---------------------------------------------------------------------------
# Card Validation (phantom charge)
# ---------------------------------------------------------------------------

async def validate_card(payment_method_id: str) -> Dict[str, Any]:
    """Validate a card with a $0.50 phantom charge + immediate refund.

    Returns {valid: bool, error: str|None}.
    """
    if not _stripe:
        return {"valid": True, "error": None}

    try:
        intent = _stripe.PaymentIntent.create(
            amount=50,  # R$0.50 in centavos
            currency="brl",
            payment_method=payment_method_id,
            confirm=True,
            description="Validação de cartão — será estornado automaticamente",
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )
        if intent.status == "succeeded":
            _stripe.Refund.create(payment_intent=intent.id)
            return {"valid": True, "error": None}
        return {"valid": False, "error": f"Cobrança não confirmada: {intent.status}"}
    except Exception as e:
        logger.error("Card validation failed: %s", e)
        return {"valid": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

async def process_refund(
    payment_intent_id: str,
    amount_cents: int,
) -> Dict[str, Any]:
    """Refund a previous charge. Returns {success, refund_id, error}."""
    if not _stripe:
        return {"success": True, "refund_id": _mock_id("re"), "error": None}

    try:
        refund = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=amount_cents,
        )
        return {
            "success": refund.status in ("succeeded", "pending"),
            "refund_id": refund.id,
            "error": None,
        }
    except Exception as e:
        logger.error("Stripe refund failed: %s", e)
        return {"success": False, "refund_id": None, "error": str(e)}


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------

async def create_payout(
    amount_cents: int,
    destination_bank: Dict[str, Any],
) -> Dict[str, Any]:
    """Process payout to a bank account. Returns {success, payout_id, error}.

    In production this would use Stripe Connect or Stripe Payouts.
    For now, bank details are logged and a mock payout is created when
    Stripe is not configured.
    """
    if not _stripe:
        return {"success": True, "payout_id": _mock_id("po"), "error": None}

    try:
        payout = _stripe.Payout.create(
            amount=amount_cents,
            currency="brl",
            description=f"Saque — {destination_bank.get('bank_name', 'N/A')}",
        )
        return {
            "success": payout.status in ("paid", "pending", "in_transit"),
            "payout_id": payout.id,
            "error": None,
        }
    except Exception as e:
        logger.error("Stripe payout failed: %s", e)
        return {"success": False, "payout_id": None, "error": str(e)}
