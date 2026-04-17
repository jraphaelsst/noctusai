from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.cart import calc_quote

router = APIRouter()


class CartItem(BaseModel):
    productId: str
    quantity: int


class QuoteInput(BaseModel):
    items: list[CartItem]
    useCashback: bool = False
    useVerbaMkt: bool = False
    cashbackBalance: float = 0.0
    verbaMktBalance: float = 0.0


@router.post("/quote")
def quote(body: QuoteInput) -> dict[str, Any]:
    items = [{"productId": i.productId, "quantity": i.quantity} for i in body.items]
    return calc_quote(
        items,
        use_cashback=body.useCashback,
        use_verba=body.useVerbaMkt,
        cashback_balance=body.cashbackBalance,
        verba_balance=body.verbaMktBalance,
    )
