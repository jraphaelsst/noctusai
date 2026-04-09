"""
Transaction Router — List and detail views with role-scoped access.

- Patient sees own transactions
- Therapist sees own transactions
- Clinic admin sees clinic's transactions
- Platform admin sees all transactions
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    get_current_user,
    get_user_role,
    get_clinic_id_for_user,
    get_admin_client,
    first_or_none,
)
from app.responses import paginated_response, success_response
from app.responses import calculate_pagination

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


@router.get("/")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    therapist_id: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None),
    clinic_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List transactions. Role-scoped: patient/therapist sees own, clinic sees clinic's, admin sees all."""
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_admin_client()

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)
    query = db.table("transactions").select("*", count="exact")

    # Role-based scoping
    if role == "patient":
        query = query.eq("patient_id", user.id)
    elif role == "therapist":
        query = query.eq("therapist_id", user.id)
    elif role == "clinic_admin":
        user_clinic_id = get_clinic_id_for_user(user)
        if not user_clinic_id:
            raise HTTPException(status_code=403, detail="Clínica não encontrada para este usuário")
        query = query.eq("clinic_id", user_clinic_id)
    # platform_admin: no additional filter (sees all)

    # Apply filters (admin/clinic can further narrow)
    if status:
        query = query.eq("status", status)
    if date_start:
        query = query.gte("created_at", date_start)
    if date_end:
        query = query.lte("created_at", date_end)
    if therapist_id and role == "platform_admin":
        query = query.eq("therapist_id", therapist_id)
    if patient_id and role == "platform_admin":
        query = query.eq("patient_id", patient_id)
    if clinic_id and role == "platform_admin":
        query = query.eq("clinic_id", clinic_id)

    end = offset + validated_page_size - 1
    result = query.order("created_at", desc=True).range(offset, end).execute()

    total = result.count if result.count is not None else 0
    return paginated_response(result.data or [], total, page, page_size)


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get transaction detail with full breakdown (gross, platform fee, clinic share, therapist share)."""
    user, _ = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_admin_client()

    result = (
        db.table("transactions")
        .select("*")
        .eq("id", transaction_id)
        .execute()
    )
    tx = first_or_none(result)
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    # Access control
    if role == "patient" and tx["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    elif role == "therapist" and tx["therapist_id"] != user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    elif role == "clinic_admin":
        user_clinic_id = get_clinic_id_for_user(user)
        if tx.get("clinic_id") != user_clinic_id:
            raise HTTPException(status_code=403, detail="Acesso negado")
    # platform_admin: full access

    return success_response(tx)
