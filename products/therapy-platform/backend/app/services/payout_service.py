"""
Payout Service — Withdrawal requests, processing, and listing.

Handles the full withdrawal lifecycle: validation, wallet debit, bank transfer
via Stripe, and status tracking. Failed payouts are automatically refunded.
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination
from app.services import stripe_service, wallet_service

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def _get_platform_setting(db: Any, key: str, default: str) -> str:
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


def _get_bank_details(owner_id: str, owner_type: str, db: Any) -> Dict[str, Any]:
    """Fetch bank details from therapist_settings or clinic_settings."""
    if owner_type == "therapist":
        table = "therapist_settings"
        id_col = "therapist_id"
    elif owner_type == "clinic":
        table = "clinic_settings"
        id_col = "clinic_id"
    else:
        return {}

    result = (
        db.table(table)
        .select("bank_name, bank_agency, bank_account, pix_key")
        .eq(id_col, owner_id)
        .execute()
    )
    row = first_or_none(result)
    return row or {}


# ---------------------------------------------------------------------------
# Request Withdrawal
# ---------------------------------------------------------------------------

async def request_withdrawal(
    owner_id: str,
    owner_type: str,
    amount: Decimal,
    db: Any,
) -> Dict[str, Any]:
    """Validate and process a withdrawal request.

    1. Check amount >= withdrawal_min_amount
    2. Check wallet balance >= amount
    3. Calculate fee
    4. Create payout record (status=pending)
    5. Debit wallet
    6. Create wallet movement
    """
    # Validate minimum
    min_amount = Decimal(_get_platform_setting(db, "withdrawal_min_amount", "10"))
    if amount < min_amount:
        raise HTTPException(
            status_code=422,
            detail=f"Valor mínimo para saque: R${min_amount:.2f}",
        )

    # Validate balance
    wallet = await wallet_service.get_or_create_wallet(owner_id, owner_type, db)
    current_balance = Decimal(str(wallet["balance"]))
    if current_balance < amount:
        raise HTTPException(
            status_code=422,
            detail=f"Saldo insuficiente. Disponível: R${current_balance:.2f}",
        )

    # Calculate fee
    fee_pct = Decimal(_get_platform_setting(db, "withdrawal_fee_pct", "2"))
    fee_amount = (amount * fee_pct / Decimal("100")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    net_amount = amount - fee_amount

    # Get bank details snapshot
    bank_details = _get_bank_details(owner_id, owner_type, db)

    # Create payout record
    payout_data = {
        "recipient_id": owner_id,
        "recipient_type": owner_type,
        "amount": float(amount),
        "fee_pct": float(fee_pct),
        "fee_amount": float(fee_amount),
        "net_amount": float(net_amount),
        "status": "pending",
        "bank_details_snapshot": bank_details,
    }
    payout_result = db.table("payouts").insert(payout_data).execute()
    payout = payout_result.data[0]

    # Debit wallet
    await wallet_service.debit_wallet(
        wallet_id=wallet["id"],
        amount=amount,
        reference_type="withdrawal",
        reference_id=payout["id"],
        description=f"Saque solicitado — R${net_amount:.2f} líquido (taxa: R${fee_amount:.2f})",
        db=db,
    )

    return payout


# ---------------------------------------------------------------------------
# Process Payout (admin / background job)
# ---------------------------------------------------------------------------

async def process_payout(
    payout_id: str,
    db: Any,
) -> Dict[str, Any]:
    """Process a pending payout via Stripe.

    If Stripe fails, refunds the withdrawal back to the wallet.
    """
    payout_result = (
        db.table("payouts")
        .select("*")
        .eq("id", payout_id)
        .execute()
    )
    payout = first_or_none(payout_result)
    if not payout:
        raise HTTPException(status_code=404, detail="Saque não encontrado")

    if payout["status"] != "pending":
        raise HTTPException(status_code=422, detail=f"Saque não está pendente (status: {payout['status']})")

    # Update to processing
    db.table("payouts").update({"status": "processing"}).eq("id", payout_id).execute()

    # Get bank details
    bank_details = payout.get("bank_details_snapshot") or _get_bank_details(
        payout["recipient_id"], payout["recipient_type"], db
    )

    net_amount_cents = int(Decimal(str(payout["net_amount"])) * 100)
    stripe_result = await stripe_service.create_payout(
        amount_cents=net_amount_cents,
        destination_bank=bank_details,
    )

    if stripe_result["success"]:
        db.table("payouts").update({
            "status": "completed",
            "processed_at": "now()",
        }).eq("id", payout_id).execute()

        updated = (
            db.table("payouts")
            .select("*")
            .eq("id", payout_id)
            .execute()
        )
        return updated.data[0]
    else:
        # Failed — refund wallet
        db.table("payouts").update({"status": "failed"}).eq("id", payout_id).execute()

        wallet = await wallet_service.get_or_create_wallet(
            payout["recipient_id"], payout["recipient_type"], db
        )
        await wallet_service.credit_wallet(
            wallet_id=wallet["id"],
            amount=Decimal(str(payout["amount"])),
            reference_type="withdrawal",
            reference_id=payout_id,
            description=f"Estorno de saque falho — {stripe_result.get('error', 'Erro desconhecido')}",
            db=db,
        )

        raise HTTPException(
            status_code=502,
            detail=f"Falha no processamento do saque: {stripe_result.get('error', 'Erro desconhecido')}",
        )


# ---------------------------------------------------------------------------
# List Payouts
# ---------------------------------------------------------------------------

async def list_payouts(
    filters: Dict[str, Any],
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """Paginated list of payouts with optional filters."""
    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)

    query = db.table("payouts").select("*", count="exact")

    if filters.get("recipient_type"):
        query = query.eq("recipient_type", filters["recipient_type"])
    if filters.get("status"):
        query = query.eq("status", filters["status"])
    if filters.get("recipient_id"):
        query = query.eq("recipient_id", filters["recipient_id"])

    end = offset + validated_page_size - 1
    result = query.order("requested_at", desc=True).range(offset, end).execute()

    total = result.count if result.count is not None else 0
    return result.data or [], total
