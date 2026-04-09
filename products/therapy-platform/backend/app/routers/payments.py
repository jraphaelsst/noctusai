"""
Payment Router — Card validation and payment method management.

Provides phantom charge validation and stubs for Stripe Customer
payment method CRUD.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.dependencies import get_current_user, get_admin_client
from app.responses import success_response
from app.schemas.financial import CardValidationRequest, PaymentMethodAdd
from app.services import stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["Payments"])


@router.post("/validate-card")
async def validate_card(
    body: CardValidationRequest,
    authorization: Optional[str] = Header(None),
):
    """Validate a card via phantom charge ($0.50 charged and immediately refunded)."""
    user, _ = await get_current_user(authorization)
    result = await stripe_service.validate_card(body.payment_method_id)
    return success_response(result)


@router.get("/methods")
async def list_payment_methods(
    authorization: Optional[str] = Header(None),
):
    """List saved payment methods for the authenticated user.

    Stub — in production this would call Stripe Customer API.
    """
    user, _ = await get_current_user(authorization)
    # In production: stripe.PaymentMethod.list(customer=stripe_customer_id, type="card")
    return success_response([])


@router.post("/methods")
async def add_payment_method(
    body: PaymentMethodAdd,
    authorization: Optional[str] = Header(None),
):
    """Attach a payment method to the user.

    Stub — in production this would attach via Stripe Customer API.
    """
    user, _ = await get_current_user(authorization)
    # In production: stripe.PaymentMethod.attach(body.stripe_payment_method_id, customer=...)
    return success_response({
        "id": body.stripe_payment_method_id,
        "is_default": body.is_default,
        "attached": True,
    })


@router.delete("/methods/{method_id}")
async def remove_payment_method(
    method_id: str,
    authorization: Optional[str] = Header(None),
):
    """Remove a payment method.

    Stub — in production this would detach via Stripe API.
    """
    user, _ = await get_current_user(authorization)
    # In production: stripe.PaymentMethod.detach(method_id)
    return success_response({"id": method_id, "detached": True})
