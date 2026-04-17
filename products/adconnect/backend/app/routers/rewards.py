from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..data.store import store
from ..auth_deps import get_current_user
from ..services.rewards import balance_for, history_for, tier_status

router = APIRouter()


@router.get("/balance")
def get_balance(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, float]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    return balance_for(did)


@router.get("/history")
def get_history(
    type: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    rows = history_for(did)
    if type:
        rows = [r for r in rows if r["type"] == type]
    rows = sorted(rows, key=lambda r: r["date"], reverse=True)
    return {"data": rows}


@router.get("/tier")
def get_tier(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    return tier_status(did)


class RedeemInput(BaseModel):
    type: str
    amount: float
    orderRef: str


@router.post("/redeem", status_code=status.HTTP_201_CREATED)
def redeem(
    body: RedeemInput,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    did = user.get("distributorId")
    if not did:
        raise HTTPException(401)
    if body.amount <= 0:
        raise HTTPException(400, "Valor precisa ser positivo")
    if body.type not in ("cashback", "verba_mkt"):
        raise HTTPException(400, "Tipo inválido")
    bal = balance_for(did)
    avail = (
        bal["cashbackAvailable"]
        if body.type == "cashback"
        else bal["verbaMktAvailable"]
    )
    if body.amount > avail:
        raise HTTPException(400, "Saldo insuficiente")

    entry = {
        "id": f"rh-{secrets.token_hex(3)}",
        "distributorId": did,
        "date": datetime.now(timezone.utc).isoformat(),
        "orderId": body.orderRef,
        "type": body.type,
        "amount": body.amount,
        "status": "Utilizado",
        "description": f"Usado no pedido {body.orderRef}",
    }
    store.rewards_history.append(entry)
    return entry
