from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..data.store import store
from ..auth_deps import get_current_user, require_role
from ..services.cart import calc_quote
from ..services.rewards import balance_for

router = APIRouter()


class OrderCartItem(BaseModel):
    productId: str
    quantity: int


class CreateOrderInput(BaseModel):
    items: list[OrderCartItem]
    cnpjId: str
    useCashback: bool = False
    useVerbaMkt: bool = False
    scheduledDate: str | None = None
    notes: str | None = None


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_order(
    body: CreateOrderInput,
    user: dict[str, Any] = Depends(require_role("customer")),
) -> dict[str, Any]:
    distributor_id = user.get("distributorId")
    if not distributor_id:
        raise HTTPException(401, "Usuário sem distribuidor vinculado")

    balance = balance_for(distributor_id)
    items = [{"productId": i.productId, "quantity": i.quantity} for i in body.items]

    q = calc_quote(
        items,
        use_cashback=body.useCashback,
        use_verba=body.useVerbaMkt,
        cashback_balance=balance["cashbackAvailable"],
        verba_balance=balance["verbaMktAvailable"],
    )

    now = datetime.now(timezone.utc).isoformat()
    order: dict[str, Any] = {
        "id": f"ORD-{secrets.token_hex(4)}",
        # Identificador simulado do Omie — trocar pela integração real em lib/omie.
        "omieId": f"OMI-{4600 + len(store.orders)}",
        "distributorId": distributor_id,
        "cnpjId": body.cnpjId,
        "status": "received",
        "items": [
            {
                "productId": line["productId"],
                "sku": line["sku"],
                "name": line["name"],
                "quantity": line["quantity"],
                "priceB2B": line["priceB2B"],
                "cashbackPct": line["cashbackPct"],
                "lineTotal": line["lineTotal"],
                "cashbackValue": line["cashbackValue"],
                "verbaMktValue": line["verbaMktValue"],
            }
            for line in q["lines"]
        ],
        "subtotal": q["subtotal"],
        "cashbackEarned": q["totalCashbackEarned"],
        "verbaMktEarned": q["totalVerbaMktEarned"],
        "cashbackApplied": q["cashbackApplied"],
        "verbaMktApplied": q["verbaMktApplied"],
        "total": q["total"],
        "scheduledDate": body.scheduledDate,
        "notes": body.notes,
        "createdAt": now,
        "updatedAt": now,
    }

    store.orders.append(order)

    if order["cashbackEarned"] > 0:
        store.rewards_history.append(
            {
                "id": f"rh-{secrets.token_hex(3)}",
                "distributorId": distributor_id,
                "date": now,
                "orderId": order["omieId"],
                "type": "cashback",
                "amount": order["cashbackEarned"],
                "status": "Pendente",
                "description": "Pedido pendente de faturamento",
            }
        )
    if order["verbaMktEarned"] > 0:
        store.rewards_history.append(
            {
                "id": f"rh-{secrets.token_hex(3)}",
                "distributorId": distributor_id,
                "date": now,
                "orderId": order["omieId"],
                "type": "verba_mkt",
                "amount": order["verbaMktEarned"],
                "status": "Pendente",
                "description": "Pedido pendente de faturamento",
            }
        )
    return order


@router.get("/")
def list_orders(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") == "admin":
        data = sorted(store.orders, key=lambda o: o["createdAt"], reverse=True)
        return {"data": data}
    distributor_id = user.get("distributorId")
    if not distributor_id:
        raise HTTPException(401)
    data = [o for o in store.orders if o["distributorId"] == distributor_id]
    data.sort(key=lambda o: o["createdAt"], reverse=True)
    return {"data": data}


@router.get("/{order_id}")
def get_order(
    order_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    order = next(
        (
            o
            for o in store.orders
            if o["id"] == order_id or o.get("omieId") == order_id
        ),
        None,
    )
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    if user.get("role") != "admin" and order["distributorId"] != user.get(
        "distributorId"
    ):
        raise HTTPException(403)
    return order
