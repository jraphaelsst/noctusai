"""
Refund Service — Request, review, and process refunds.

Refund requests are feature-flag controlled via platform_settings.refund_enabled.
When approved, the full refund flow reverses wallet credits and processes
Stripe refunds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination
from app.services import stripe_service, wallet_service

logger = logging.getLogger(__name__)

SP_TZ = timezone(timedelta(hours=-3))


def _get_platform_setting(db: Any, key: str, default: str) -> str:
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


# ---------------------------------------------------------------------------
# Create Refund Request
# ---------------------------------------------------------------------------

async def create_refund_request(
    patient_id: str,
    transaction_id: str,
    reason: str,
    db: Any,
) -> Dict[str, Any]:
    """Patient submits a refund request.

    Validations:
    1. Refund feature is enabled
    2. Transaction exists and belongs to patient
    3. Within refund window (days)
    """
    # Check feature flag
    enabled = _get_platform_setting(db, "refund_enabled", "true")
    if enabled.lower() not in ("true", "1", "yes"):
        raise HTTPException(
            status_code=422,
            detail="Funcionalidade de reembolso está desabilitada no momento",
        )

    # Validate transaction
    tx_result = (
        db.table("transactions")
        .select("*")
        .eq("id", transaction_id)
        .execute()
    )
    tx = first_or_none(tx_result)
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    if tx["patient_id"] != patient_id:
        raise HTTPException(status_code=403, detail="Transação não pertence a este paciente")

    if tx["status"] != "captured":
        raise HTTPException(status_code=422, detail="Apenas transações capturadas podem ser reembolsadas")

    # Check refund window
    window_days = int(_get_platform_setting(db, "refund_window_days", "7"))
    captured_at = tx.get("captured_at") or tx.get("created_at")
    if captured_at:
        if isinstance(captured_at, str):
            # Parse ISO datetime
            try:
                captured_dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            except ValueError as exc:
                logger.warning(
                    "refund_service: tx id=%s has unparseable captured_at=%r (%s); "
                    "defaulting to now() — refund window check is conservative",
                    tx.get("id"), captured_at, exc,
                )
                captured_dt = datetime.now(SP_TZ)
        else:
            captured_dt = captured_at

        now = datetime.now(timezone.utc)
        if now - captured_dt > timedelta(days=window_days):
            raise HTTPException(
                status_code=422,
                detail=f"Prazo para reembolso expirado ({window_days} dias)",
            )

    # Check for existing pending request
    existing = (
        db.table("refund_requests")
        .select("id")
        .eq("transaction_id", transaction_id)
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Já existe uma solicitação de reembolso pendente para esta transação")

    # Create request
    refund_data = {
        "transaction_id": transaction_id,
        "appointment_id": tx.get("appointment_id"),
        "patient_id": patient_id,
        "therapist_id": tx["therapist_id"],
        "clinic_id": tx.get("clinic_id"),
        "reason": reason,
        "status": "pending",
        "refund_amount": float(tx["gross_amount"]),
    }
    result = db.table("refund_requests").insert(refund_data).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Review Refund (Admin)
# ---------------------------------------------------------------------------

async def review_refund(
    refund_id: str,
    admin_id: str,
    action: str,
    response: Optional[str],
    db: Any,
) -> Dict[str, Any]:
    """Admin approves or denies a refund request.

    If approved: reverse wallet credits and process Stripe refund.
    If denied: update status with reason.
    """
    refund_result = (
        db.table("refund_requests")
        .select("*")
        .eq("id", refund_id)
        .execute()
    )
    refund = first_or_none(refund_result)
    if not refund:
        raise HTTPException(status_code=404, detail="Solicitação de reembolso não encontrada")

    if refund["status"] != "pending":
        raise HTTPException(status_code=422, detail=f"Solicitação não está pendente (status: {refund['status']})")

    if action == "deny":
        if not response:
            raise HTTPException(status_code=422, detail="Motivo é obrigatório para negação")

        db.table("refund_requests").update({
            "status": "denied",
            "reviewed_by_admin_id": admin_id,
            "review_response": response,
            "resolved_at": "now()",
        }).eq("id", refund_id).execute()

        updated = db.table("refund_requests").select("*").eq("id", refund_id).execute()
        return updated.data[0]

    # action == "approve"
    refund_amount = Decimal(str(refund["refund_amount"]))

    # Get original transaction
    tx_result = (
        db.table("transactions")
        .select("*")
        .eq("id", refund["transaction_id"])
        .execute()
    )
    tx = first_or_none(tx_result)
    if not tx:
        raise HTTPException(status_code=404, detail="Transação original não encontrada")

    # Reverse therapist wallet credit
    therapist_share = Decimal(str(tx.get("therapist_share_amount", 0)))
    if therapist_share > 0:
        therapist_wallet = await wallet_service.get_or_create_wallet(
            tx["therapist_id"], "therapist", db
        )
        await wallet_service.debit_wallet(
            wallet_id=therapist_wallet["id"],
            amount=therapist_share,
            reference_type="refund",
            reference_id=refund_id,
            description=f"Estorno por reembolso — sessão #{tx.get('appointment_id', 'N/A')[:8]}",
            db=db,
        )

    # Reverse clinic wallet credit
    clinic_share = Decimal(str(tx.get("clinic_share_amount") or 0))
    if tx.get("clinic_id") and clinic_share > 0:
        clinic_wallet = await wallet_service.get_or_create_wallet(
            tx["clinic_id"], "clinic", db
        )
        await wallet_service.debit_wallet(
            wallet_id=clinic_wallet["id"],
            amount=clinic_share,
            reference_type="refund",
            reference_id=refund_id,
            description=f"Estorno por reembolso — sessão #{tx.get('appointment_id', 'N/A')[:8]}",
            db=db,
        )

    # Credit patient wallet
    patient_wallet = await wallet_service.get_or_create_wallet(
        tx["patient_id"], "patient", db
    )
    await wallet_service.credit_wallet(
        wallet_id=patient_wallet["id"],
        amount=refund_amount,
        reference_type="refund",
        reference_id=refund_id,
        description=f"Reembolso aprovado — sessão #{tx.get('appointment_id', 'N/A')[:8]}",
        db=db,
    )

    # Process Stripe refund if there's a gateway reference
    if tx.get("gateway_ref"):
        amount_cents = int(refund_amount * 100)
        await stripe_service.process_refund(tx["gateway_ref"], amount_cents)

    # Update transaction status
    db.table("transactions").update({
        "status": "refunded",
        "refunded_at": "now()",
    }).eq("id", refund["transaction_id"]).execute()

    # Update refund request
    db.table("refund_requests").update({
        "status": "approved",
        "reviewed_by_admin_id": admin_id,
        "review_response": response or "Aprovado",
        "resolved_at": "now()",
    }).eq("id", refund_id).execute()

    updated = db.table("refund_requests").select("*").eq("id", refund_id).execute()
    return updated.data[0]


# ---------------------------------------------------------------------------
# List Refund Requests
# ---------------------------------------------------------------------------

async def list_refund_requests(
    filters: Dict[str, Any],
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """Paginated list of refund requests with optional filters."""
    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)

    query = db.table("refund_requests").select("*", count="exact")

    if filters.get("status"):
        query = query.eq("status", filters["status"])
    if filters.get("patient_id"):
        query = query.eq("patient_id", filters["patient_id"])
    if filters.get("therapist_id"):
        query = query.eq("therapist_id", filters["therapist_id"])

    end = offset + validated_page_size - 1
    result = query.order("created_at", desc=True).range(offset, end).execute()

    total = result.count if result.count is not None else 0
    return result.data or [], total
