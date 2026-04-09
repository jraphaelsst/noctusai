"""
Wallet Service — Balance management, top-ups, debits, credits, movements.

Every balance change creates a wallet_movement record for audit trail.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination
from app.services import stripe_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wallet CRUD
# ---------------------------------------------------------------------------

async def get_or_create_wallet(
    owner_id: str,
    owner_type: str,
    db: Any,
) -> Dict[str, Any]:
    """Return existing wallet or create one with balance=0."""
    result = (
        db.table("wallets")
        .select("*")
        .eq("owner_id", owner_id)
        .eq("owner_type", owner_type)
        .execute()
    )
    row = first_or_none(result)
    if row:
        return row

    new_wallet = (
        db.table("wallets")
        .insert({
            "owner_id": owner_id,
            "owner_type": owner_type,
            "balance": 0,
        })
        .execute()
    )
    return new_wallet.data[0]


async def get_wallet(
    owner_id: str,
    owner_type: str,
    db: Any,
) -> Dict[str, Any]:
    """Return wallet with current balance. Raises 404 if not found."""
    result = (
        db.table("wallets")
        .select("*")
        .eq("owner_id", owner_id)
        .eq("owner_type", owner_type)
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")
    return row


async def get_wallet_balance(
    owner_id: str,
    owner_type: str,
    db: Any,
) -> Decimal:
    """Return current balance for the given owner."""
    wallet = await get_wallet(owner_id, owner_type, db)
    return Decimal(str(wallet["balance"]))


# ---------------------------------------------------------------------------
# Top-up (credit via Stripe charge)
# ---------------------------------------------------------------------------

async def top_up_wallet(
    owner_id: str,
    owner_type: str,
    amount: Decimal,
    payment_method_id: str,
    db: Any,
) -> Dict[str, Any]:
    """Charge the payment method via Stripe and credit the wallet."""
    amount_cents = int(amount * 100)
    charge_result = await stripe_service.charge_payment_method(
        payment_method_id=payment_method_id,
        amount_cents=amount_cents,
        description=f"Crédito em carteira — {owner_type}/{owner_id}",
    )
    if not charge_result["success"]:
        raise HTTPException(
            status_code=402,
            detail=f"Falha na cobrança: {charge_result.get('error', 'Erro desconhecido')}",
        )

    wallet = await get_or_create_wallet(owner_id, owner_type, db)
    new_balance = Decimal(str(wallet["balance"])) + amount

    updated = (
        db.table("wallets")
        .update({"balance": float(new_balance)})
        .eq("id", wallet["id"])
        .execute()
    )

    db.table("wallet_movements").insert({
        "wallet_id": wallet["id"],
        "type": "credit",
        "amount": float(amount),
        "reference_type": "top_up",
        "reference_id": None,
        "description": f"Crédito via cartão — {charge_result.get('payment_intent_id', 'N/A')}",
    }).execute()

    return updated.data[0]


# ---------------------------------------------------------------------------
# Debit / Credit (internal wallet operations)
# ---------------------------------------------------------------------------

async def debit_wallet(
    wallet_id: str,
    amount: Decimal,
    reference_type: str,
    reference_id: Optional[str],
    description: str,
    db: Any,
) -> Dict[str, Any]:
    """Debit wallet by amount. Raises error if insufficient balance."""
    wallet_result = (
        db.table("wallets")
        .select("*")
        .eq("id", wallet_id)
        .execute()
    )
    wallet = first_or_none(wallet_result)
    if not wallet:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    current_balance = Decimal(str(wallet["balance"]))
    if current_balance < amount:
        raise HTTPException(
            status_code=422,
            detail=f"Saldo insuficiente. Disponível: R${current_balance:.2f}, Necessário: R${amount:.2f}",
        )

    new_balance = current_balance - amount
    updated = (
        db.table("wallets")
        .update({"balance": float(new_balance)})
        .eq("id", wallet_id)
        .execute()
    )

    db.table("wallet_movements").insert({
        "wallet_id": wallet_id,
        "type": "debit",
        "amount": float(amount),
        "reference_type": reference_type,
        "reference_id": reference_id,
        "description": description,
    }).execute()

    return updated.data[0]


async def credit_wallet(
    wallet_id: str,
    amount: Decimal,
    reference_type: str,
    reference_id: Optional[str],
    description: str,
    db: Any,
) -> Dict[str, Any]:
    """Credit wallet by amount."""
    wallet_result = (
        db.table("wallets")
        .select("*")
        .eq("id", wallet_id)
        .execute()
    )
    wallet = first_or_none(wallet_result)
    if not wallet:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    new_balance = Decimal(str(wallet["balance"])) + amount
    updated = (
        db.table("wallets")
        .update({"balance": float(new_balance)})
        .eq("id", wallet_id)
        .execute()
    )

    db.table("wallet_movements").insert({
        "wallet_id": wallet_id,
        "type": "credit",
        "amount": float(amount),
        "reference_type": reference_type,
        "reference_id": reference_id,
        "description": description,
    }).execute()

    return updated.data[0]


# ---------------------------------------------------------------------------
# Movements (history)
# ---------------------------------------------------------------------------

async def get_wallet_movements(
    wallet_id: str,
    page: int,
    page_size: int,
    db: Any,
) -> Tuple[List[Dict], int]:
    """Paginated list of wallet movements, newest first."""
    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)

    count_result = (
        db.table("wallet_movements")
        .select("id", count="exact")
        .eq("wallet_id", wallet_id)
        .execute()
    )
    total = count_result.count if count_result.count is not None else 0

    end = offset + validated_page_size - 1
    data_result = (
        db.table("wallet_movements")
        .select("*")
        .eq("wallet_id", wallet_id)
        .order("created_at", desc=True)
        .range(offset, end)
        .execute()
    )

    return data_result.data or [], total
