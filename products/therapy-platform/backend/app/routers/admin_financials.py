"""
Admin Financials Router — Global dashboard, wallet listing, commission overrides, payouts.

All endpoints require platform_admin role.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_user_role, get_admin_client, first_or_none
from app.responses import paginated_response, success_response
from app.responses import calculate_pagination
from app.schemas.financial import CommissionOverrideRequest
from app.services import payout_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/financials", tags=["Admin Financials"])


def _require_admin(user) -> str:
    """Enforce platform_admin role. Returns user.id."""
    role = get_user_role(user)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores da plataforma")
    return user.id


@router.get("/")
async def global_dashboard(
    authorization: Optional[str] = Header(None),
):
    """Global financial dashboard: total revenue, commissions, payouts."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    # Total revenue from captured transactions
    tx_result = (
        db.table("transactions")
        .select("gross_amount, platform_fee_amount, clinic_share_amount, therapist_share_amount, status")
        .eq("status", "captured")
        .execute()
    )
    transactions = tx_result.data or []

    total_gross = sum(float(tx.get("gross_amount", 0)) for tx in transactions)
    total_platform_fees = sum(float(tx.get("platform_fee_amount", 0)) for tx in transactions)
    total_clinic_share = sum(float(tx.get("clinic_share_amount") or 0) for tx in transactions)
    total_therapist_share = sum(float(tx.get("therapist_share_amount", 0)) for tx in transactions)

    # Payout summary
    payout_result = (
        db.table("payouts")
        .select("amount, net_amount, fee_amount, status")
        .execute()
    )
    payouts = payout_result.data or []

    total_payouts_requested = sum(float(p.get("amount", 0)) for p in payouts)
    total_payouts_completed = sum(
        float(p.get("net_amount", 0)) for p in payouts if p.get("status") == "completed"
    )
    total_payout_fees = sum(float(p.get("fee_amount", 0)) for p in payouts)
    pending_payouts = sum(1 for p in payouts if p.get("status") == "pending")

    # Refund summary
    refund_result = (
        db.table("refund_requests")
        .select("refund_amount, status")
        .execute()
    )
    refunds = refund_result.data or []
    total_refunded = sum(
        float(r.get("refund_amount", 0)) for r in refunds if r.get("status") == "approved"
    )
    pending_refunds = sum(1 for r in refunds if r.get("status") == "pending")

    return success_response({
        "transactions": {
            "total_count": len(transactions),
            "total_gross": total_gross,
            "total_platform_fees": total_platform_fees,
            "total_clinic_share": total_clinic_share,
            "total_therapist_share": total_therapist_share,
        },
        "payouts": {
            "total_requested": total_payouts_requested,
            "total_completed": total_payouts_completed,
            "total_fees": total_payout_fees,
            "pending_count": pending_payouts,
        },
        "refunds": {
            "total_refunded": total_refunded,
            "pending_count": pending_refunds,
        },
    })


@router.get("/wallets")
async def list_all_wallets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    owner_type: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List all wallets (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)
    query = db.table("wallets").select("*", count="exact")

    if owner_type:
        query = query.eq("owner_type", owner_type)

    end = offset + validated_page_size - 1
    result = query.order("last_updated", desc=True).range(offset, end).execute()

    total = result.count if result.count is not None else 0
    return paginated_response(result.data or [], total, page, page_size)


@router.post("/commissions")
async def set_commission_override(
    body: CommissionOverrideRequest,
    authorization: Optional[str] = Header(None),
):
    """Set or update a platform commission override for a clinic or therapist."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    # Upsert: check if override exists
    existing = (
        db.table("platform_commission_overrides")
        .select("id")
        .eq("target_type", body.target_type)
        .eq("target_id", body.target_id)
        .execute()
    )
    row = first_or_none(existing)

    if row:
        result = (
            db.table("platform_commission_overrides")
            .update({"custom_commission_pct": float(body.custom_commission_pct)})
            .eq("id", row["id"])
            .execute()
        )
    else:
        result = (
            db.table("platform_commission_overrides")
            .insert({
                "target_type": body.target_type,
                "target_id": body.target_id,
                "custom_commission_pct": float(body.custom_commission_pct),
            })
            .execute()
        )

    return success_response(result.data[0])


@router.get("/payouts")
async def list_all_payouts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    recipient_type: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List all payouts (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    filters = {}
    if status:
        filters["status"] = status
    if recipient_type:
        filters["recipient_type"] = recipient_type

    data, total = await payout_service.list_payouts(filters, page, page_size, db)
    return paginated_response(data, total, page, page_size)


@router.post("/payouts/{payout_id}/process")
async def process_payout(
    payout_id: str,
    authorization: Optional[str] = Header(None),
):
    """Process a pending payout (admin only). Triggers Stripe transfer."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    result = await payout_service.process_payout(payout_id, db)
    return success_response(result)
