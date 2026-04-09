"""
Invoice Service — Generate and manage invoices from financial transactions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination

logger = logging.getLogger(__name__)


async def generate_invoice(
    transaction_id: str,
    therapist_id: str,
    patient_id: str,
    db: Any,
) -> Dict:
    """Generate an invoice record from a financial transaction."""
    # Verify transaction exists
    tx_check = (
        db.table("financial_transactions")
        .select("id, amount, description")
        .eq("id", transaction_id)
        .execute()
    )
    transaction = first_or_none(tx_check)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transação financeira não encontrada")

    # Check for duplicate invoice
    dup_check = (
        db.table("invoices")
        .select("id")
        .eq("transaction_id", transaction_id)
        .execute()
    )
    if dup_check.data:
        raise HTTPException(status_code=409, detail="Fatura já gerada para esta transação")

    record = {
        "transaction_id": transaction_id,
        "therapist_id": therapist_id,
        "patient_id": patient_id,
        "amount": transaction.get("amount"),
        "descricao": transaction.get("description"),
        "status": "gerada",
    }
    result = db.table("invoices").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao gerar fatura")
    logger.info("Invoice generated for transaction %s", transaction_id)
    return row


async def list_invoices(
    user_id: str,
    role: str,
    db: Any,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict], int]:
    """List invoices for a user based on their role."""
    page, page_size, offset = calculate_pagination(page, page_size)

    query = db.table("invoices").select("*", count="exact")

    if role == "therapist":
        query = query.eq("therapist_id", user_id)
    elif role == "patient":
        query = query.eq("patient_id", user_id)
    # platform_admin / clinic_admin see all (no filter)

    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return result.data or [], result.count or 0


async def get_invoice(
    invoice_id: str,
    db: Any,
) -> Dict:
    """Get a single invoice by ID."""
    result = db.table("invoices").select("*").eq("id", invoice_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    return row
