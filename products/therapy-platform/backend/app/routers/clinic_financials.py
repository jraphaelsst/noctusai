"""
Clinic Financials Router — Dashboard, transfers, and transfer history.

All endpoints require clinic_admin role.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_role,
    get_clinic_id_for_user,
    get_admin_client,
)
from app.responses import paginated_response, success_response
from app.responses import calculate_pagination
from app.schemas.financial import ClinicTransferRequest
from app.services import wallet_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clinic/financials", tags=["Clinic Financials"])


def _require_clinic_admin(user) -> str:
    """Enforce clinic_admin role and return clinic_id."""
    role = get_user_role(user)
    if role != "clinic_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores de clínica")
    clinic_id = get_clinic_id_for_user(user)
    if not clinic_id:
        raise HTTPException(status_code=403, detail="Clínica não encontrada para este usuário")
    return clinic_id


@router.get("/")
async def clinic_dashboard(
    authorization: Optional[str] = Header(None),
):
    """Clinic financial dashboard: total revenue, platform fees, per-therapist breakdown."""
    user, _ = await get_current_user(authorization)
    clinic_id = _require_clinic_admin(user)
    db = get_admin_client()

    # Get clinic wallet
    wallet = await wallet_service.get_or_create_wallet(clinic_id, "clinic", db)

    # Get clinic transactions
    tx_result = (
        db.table("transactions")
        .select("*")
        .eq("clinic_id", clinic_id)
        .eq("status", "captured")
        .execute()
    )
    transactions = tx_result.data or []

    total_gross = sum(float(tx.get("gross_amount", 0)) for tx in transactions)
    total_platform_fees = sum(float(tx.get("platform_fee_amount", 0)) for tx in transactions)
    total_clinic_share = sum(float(tx.get("clinic_share_amount") or 0) for tx in transactions)
    total_therapist_share = sum(float(tx.get("therapist_share_amount", 0)) for tx in transactions)

    # Per-therapist breakdown
    therapist_map: dict = {}
    for tx in transactions:
        tid = tx["therapist_id"]
        if tid not in therapist_map:
            therapist_map[tid] = {
                "therapist_id": tid,
                "session_count": 0,
                "total_gross": 0,
                "total_clinic_share": 0,
                "total_therapist_share": 0,
            }
        therapist_map[tid]["session_count"] += 1
        therapist_map[tid]["total_gross"] += float(tx.get("gross_amount", 0))
        therapist_map[tid]["total_clinic_share"] += float(tx.get("clinic_share_amount") or 0)
        therapist_map[tid]["total_therapist_share"] += float(tx.get("therapist_share_amount", 0))

    return success_response({
        "wallet_balance": float(wallet["balance"]),
        "total_gross": total_gross,
        "total_platform_fees": total_platform_fees,
        "total_clinic_share": total_clinic_share,
        "total_therapist_share": total_therapist_share,
        "session_count": len(transactions),
        "therapist_breakdown": list(therapist_map.values()),
    })


@router.post("/transfers")
async def create_transfer(
    body: ClinicTransferRequest,
    authorization: Optional[str] = Header(None),
):
    """Voluntary transfer from clinic wallet to therapist wallet."""
    user, _ = await get_current_user(authorization)
    clinic_id = _require_clinic_admin(user)
    db = get_admin_client()

    # Debit clinic wallet
    clinic_wallet = await wallet_service.get_or_create_wallet(clinic_id, "clinic", db)
    await wallet_service.debit_wallet(
        wallet_id=clinic_wallet["id"],
        amount=body.amount,
        reference_type="voluntary_transfer",
        reference_id=None,
        description=f"Transferência para terapeuta — {body.reason}",
        db=db,
    )

    # Credit therapist wallet
    therapist_wallet = await wallet_service.get_or_create_wallet(body.therapist_id, "therapist", db)
    await wallet_service.credit_wallet(
        wallet_id=therapist_wallet["id"],
        amount=body.amount,
        reference_type="voluntary_transfer",
        reference_id=None,
        description=f"Transferência recebida da clínica — {body.reason}",
        db=db,
    )

    # Record the transfer
    transfer_data = {
        "clinic_id": clinic_id,
        "therapist_id": body.therapist_id,
        "amount": float(body.amount),
        "reason": body.reason,
        "initiated_by_user_id": user.id,
    }
    result = db.table("clinic_transfers").insert(transfer_data).execute()

    return success_response(result.data[0])


@router.get("/transfers")
async def list_transfers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(None),
):
    """List clinic transfer history."""
    user, _ = await get_current_user(authorization)
    clinic_id = _require_clinic_admin(user)
    db = get_admin_client()

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)

    result = (
        db.table("clinic_transfers")
        .select("*", count="exact")
        .eq("clinic_id", clinic_id)
        .order("created_at", desc=True)
        .range(offset, offset + validated_page_size - 1)
        .execute()
    )

    total = result.count if result.count is not None else 0
    return paginated_response(result.data or [], total, page, page_size)
