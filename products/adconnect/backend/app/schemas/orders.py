"""
Pydantic schemas for the cart + orders routers (Phase 3 — Supabase-backed).

Tables (see `migrations/001_adconnect.sql` § 5 ORDERS):
  • adconnect.carts            — per-distributor cart (status: ativo|abandonado|convertido)
  • adconnect.itens_carrinho   — cart line items (UNIQUE (cart_id, product_id))
  • adconnect.pedidos          — orders with status lifecycle
  • adconnect.itens_pedido     — order line items (snapshot of price + name at order time)

Order status lifecycle (single status column; service-layer enforces transitions):
  rascunho → enviado → confirmado → enviado_para_entrega → entregue / cancelado
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field
from noctusai_lib.api import StrictHttpModel

CartStatus = Literal["ativo", "abandonado", "convertido"]
OrderStatus = Literal[
    "rascunho",
    "enviado",
    "confirmado",
    "enviado_para_entrega",
    "entregue",
    "cancelado",
]


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class CartItemIn(StrictHttpModel):
    """Body for `POST /cart/items` — add a line item (or upsert quantity)."""

    product_id: str
    quantidade: int = Field(gt=0)


class CartItemUpdateIn(StrictHttpModel):
    """Body for `PATCH /cart/items/{id}` — change a line's quantity."""

    quantidade: int = Field(gt=0)


class CartItemOut(StrictHttpModel):
    id: str
    cart_id: str
    product_id: str
    sku: Optional[str] = None
    nome: Optional[str] = None
    quantidade: int
    price_at_add: float
    line_total: float
    created_at: Optional[datetime] = None


class CartOut(StrictHttpModel):
    id: str
    distributor_id: str
    created_by: Optional[str] = None
    status: CartStatus
    total: float
    items: list[CartItemOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class OrderItemOut(StrictHttpModel):
    id: str
    pedido_id: str
    product_id: str
    sku_at_order: str
    nome_at_order: str
    quantidade: int
    price_at_order: float
    subtotal: float
    created_at: Optional[datetime] = None


class OrderOut(StrictHttpModel):
    id: str
    distributor_id: str
    cart_id: Optional[str] = None
    placed_by: Optional[str] = None
    status: OrderStatus
    total: float
    observacoes: Optional[str] = None
    placed_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    items: list[OrderItemOut] = Field(default_factory=list)


class OrderListOut(StrictHttpModel):
    data: list[OrderOut] = Field(default_factory=list)


class OrderCheckoutIn(StrictHttpModel):
    """Body for `POST /cart/checkout` — convert active cart to a pedido."""

    observacoes: Optional[str] = None


class OrderStatusTransitionIn(StrictHttpModel):
    """Body for `PATCH /orders/{id}/status` — brand admin transitions order."""

    status: OrderStatus


__all__ = [
    "CartStatus",
    "OrderStatus",
    "CartItemIn",
    "CartItemUpdateIn",
    "CartItemOut",
    "CartOut",
    "OrderItemOut",
    "OrderOut",
    "OrderListOut",
    "OrderCheckoutIn",
    "OrderStatusTransitionIn",
]
