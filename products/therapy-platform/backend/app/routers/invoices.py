"""
Invoices Router — Receipt/invoice generation from financial transactions.

Therapists generate invoices (recibos) from completed transactions.
Both therapists and patients can list and view their invoices.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    first_or_none,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import paginated_response, success_response
from app.services import invoice_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/invoices", tags=["Invoices"])


@router.post("")
async def generate_invoice(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Generate an invoice from a transaction (therapist only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "therapist":
        raise HTTPException(status_code=403, detail="Apenas terapeutas podem gerar recibos")

    db = get_user_client(token)
    data = await invoice_service.generate_invoice(
        transaction_id=body.get("transaction_id", ""),
        therapist_id=user.id,
        patient_id=body.get("patient_id", ""),
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_invoices(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List invoices for the current user.

    - Therapist: sees invoices they generated
    - Patient: sees invoices addressed to them
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    data, total = await invoice_service.list_invoices(
        user_id=user.id,
        role=role,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    authorization: Optional[str] = Header(None),
):
    """Get a single invoice."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    db = get_user_client(token)

    existing = first_or_none(
        db.table("invoices")
        .select("*")
        .eq("id", invoice_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Recibo não encontrado")

    # Authorization: must be therapist or patient on the invoice
    if role == "therapist" and existing.get("therapist_id") != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar este recibo")
    if role == "patient" and existing.get("patient_id") != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar este recibo")

    return success_response(existing)
