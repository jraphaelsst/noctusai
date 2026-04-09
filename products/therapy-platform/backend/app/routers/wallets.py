"""
Wallet Router — Balance, movements, top-ups, and withdrawals.

Any authenticated user can view their own wallet and request withdrawals.
Top-ups are typically used by patients to load credits.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_user_role, get_admin_client
from app.responses import paginated_response, success_response
from app.schemas.financial import WalletTopUpRequest, WithdrawalRequest
from app.services import wallet_service, payout_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wallets", tags=["Wallets"])


def _resolve_owner(user) -> tuple[str, str]:
    """Resolve wallet owner_id and owner_type from user metadata."""
    role = get_user_role(user)
    if role == "patient":
        return user.id, "patient"
    elif role in ("therapist",):
        return user.id, "therapist"
    elif role == "clinic_admin":
        metadata = user.user_metadata or {}
        clinic_id = metadata.get("clinic_id")
        if clinic_id:
            return clinic_id, "clinic"
        return user.id, "therapist"
    else:
        return user.id, "patient"


@router.get("/me")
async def get_my_wallet(authorization: Optional[str] = Header(None)):
    """Get the authenticated user's wallet (creates one if it doesn't exist)."""
    user, _ = await get_current_user(authorization)
    owner_id, owner_type = _resolve_owner(user)
    db = get_admin_client()
    wallet = await wallet_service.get_or_create_wallet(owner_id, owner_type, db)
    return success_response(wallet)


@router.get("/me/movements")
async def list_my_movements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
):
    """List wallet movements for the authenticated user, newest first."""
    user, _ = await get_current_user(authorization)
    owner_id, owner_type = _resolve_owner(user)
    db = get_admin_client()

    wallet = await wallet_service.get_or_create_wallet(owner_id, owner_type, db)
    data, total = await wallet_service.get_wallet_movements(wallet["id"], page, page_size, db)
    return paginated_response(data, total, page, page_size)


@router.post("/top-up")
async def top_up(
    body: WalletTopUpRequest,
    authorization: Optional[str] = Header(None),
):
    """Load credits into wallet via Stripe charge."""
    user, _ = await get_current_user(authorization)
    owner_id, owner_type = _resolve_owner(user)
    db = get_admin_client()

    wallet = await wallet_service.top_up_wallet(
        owner_id=owner_id,
        owner_type=owner_type,
        amount=body.amount,
        payment_method_id=body.payment_method_id,
        db=db,
    )
    return success_response(wallet)


@router.post("/withdraw")
async def withdraw(
    body: WithdrawalRequest,
    authorization: Optional[str] = Header(None),
):
    """Request a withdrawal from wallet to bank account."""
    user, _ = await get_current_user(authorization)
    owner_id, owner_type = _resolve_owner(user)
    db = get_admin_client()

    payout = await payout_service.request_withdrawal(
        owner_id=owner_id,
        owner_type=owner_type,
        amount=body.amount,
        db=db,
    )
    return success_response(payout)
