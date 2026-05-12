"""
AdConnect Cart Router — Supabase-backed (Phase 3).

Replaces the mock-quote endpoint with a real cart surface that backs
`adconnect.carts` + `adconnect.itens_carrinho`. The route shape is
distributor-scoped; brand admin doesn't carry a cart (the brand admin uses
the order endpoints to manage placed pedidos).

Endpoints:
  • GET    /cart                — current cart for distributor.
  • POST   /cart/items          — add line item (or upsert qty if exists).
  • PATCH  /cart/items/{id}     — update qty.
  • DELETE /cart/items/{id}     — remove line.
  • POST   /cart/checkout       — convert active cart to a pedido.

Constructor-time prefix is mandatory — FastAPI 0.115 ignores router.prefix
mutation post-construction (Phase 2 finding; PROJECT.md §11). Phase 3 IS
the structural fix for the wildcard-route bug that mitigation in Phase 2
worked around.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status

from ..dependencies import get_current_user_org
from ..database import _db as _db_module
from ..schemas.orders import (
    CartItemIn,
    CartItemUpdateIn,
    CartOut,
    OrderCheckoutIn,
    OrderOut,
)
from ..services import cart_service, orders_service

router = APIRouter(prefix="/cart", tags=["cart"])


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db() -> Any:
    """Lazy access via `_db` so test patches of `_db.get_client` are honored."""
    try:
        client = _db_module.get_client()
    except Exception:
        client = None
    if client is None:
        try:
            client = _db_module.get_admin_client()
        except Exception:
            client = None
    if client is None:
        raise HTTPException(503, "Supabase client unavailable")
    return client


def _resolve_org_id(user: Any, org_id: Optional[str] = None) -> str:
    """Read brand ``org_id`` from the auth-resolved triple's ``org_id``
    (canonical), falling back to ``user.user_metadata.org_id``, then the
    single-instance default."""
    if org_id:
        return str(org_id)
    metadata = getattr(user, "user_metadata", None) or {}
    return str(metadata.get("org_id") or DEFAULT_ORG_ID)


def _resolve_distributor_id(user: Any) -> Optional[str]:
    metadata = getattr(user, "user_metadata", None) or {}
    did = metadata.get("distributor_id") or metadata.get("distributorId")
    return str(did) if did else None


def _require_distributor(user: Any) -> str:
    did = _resolve_distributor_id(user)
    if not did:
        raise HTTPException(401, "Usuário sem distribuidor vinculado")
    return did


def _resolve_admin_email(user: Any) -> Optional[str]:
    """Brand admin email for the placed-order notification.

    For Phase 3 we surface the env-configured `BRAND_ADMIN_EMAIL` if set on
    the JWT (some products mirror it). Real lookup via `noctus_users` is a
    Phase 5 admin-V2 concern — returning None is the documented happy path
    in dev and the email is fire-and-forget.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    return metadata.get("brand_admin_email") or metadata.get("brandAdminEmail")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=CartOut)
def get_cart(
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    """Return the distributor's active cart (creating one lazily if needed).

    Distributor-only endpoint — admin gets 403. The shape includes
    `items[]` with each line's `sku`, `nome`, `quantidade`, `price_at_add`,
    and `line_total`.
    """
    user, _token, auth_org_id = auth
    distributor_id = _require_distributor(user)
    org_id = _resolve_org_id(user, auth_org_id)
    db = _db()
    cart = cart_service.get_or_create_active_cart(
        db,
        distributor_id=distributor_id,
        org_id=org_id,
        created_by=getattr(user, "id", None),
    )
    return cart


@router.post(
    "/items", response_model=CartOut, status_code=status.HTTP_201_CREATED
)
def add_cart_item(
    body: CartItemIn,
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    """Add a product line to the active cart (or upsert quantity)."""
    user, _token, auth_org_id = auth
    distributor_id = _require_distributor(user)
    org_id = _resolve_org_id(user, auth_org_id)
    db = _db()
    try:
        return cart_service.add_line(
            db,
            distributor_id=distributor_id,
            org_id=org_id,
            created_by=getattr(user, "id", None),
            product_id=body.product_id,
            quantidade=body.quantidade,
        )
    except cart_service.CartError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/items/{line_id}", response_model=CartOut)
def update_cart_item(
    body: CartItemUpdateIn,
    line_id: str = Path(...),
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    """Update a line's quantity. 404 if line not in caller's active cart."""
    user, _token, auth_org_id = auth
    distributor_id = _require_distributor(user)
    org_id = _resolve_org_id(user, auth_org_id)
    db = _db()
    try:
        return cart_service.update_line(
            db,
            distributor_id=distributor_id,
            org_id=org_id,
            line_id=line_id,
            quantidade=body.quantidade,
        )
    except cart_service.CartError as exc:
        msg = str(exc)
        # Fine-tune status: not-found → 404, validation → 400.
        code = 404 if "não encontrad" in msg.lower() else 400
        raise HTTPException(code, msg) from exc


@router.delete("/items/{line_id}", response_model=CartOut)
def remove_cart_item(
    line_id: str = Path(...),
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    """Remove a line from the active cart."""
    user, _token, auth_org_id = auth
    distributor_id = _require_distributor(user)
    org_id = _resolve_org_id(user, auth_org_id)
    db = _db()
    try:
        return cart_service.remove_line(
            db,
            distributor_id=distributor_id,
            org_id=org_id,
            line_id=line_id,
        )
    except cart_service.CartError as exc:
        msg = str(exc)
        code = 404 if "não encontrad" in msg.lower() else 400
        raise HTTPException(code, msg) from exc


@router.post(
    "/checkout", response_model=OrderOut, status_code=status.HTTP_201_CREATED
)
def checkout(
    body: OrderCheckoutIn,
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    """Convert the active cart into a pedido + flips cart status to convertido.

    Triggers (non-fatal):
      • Reward accrual via `rewards_service.accrue_for_pedido`.
      • Brand-admin email notification.
    """
    user, _token, auth_org_id = auth
    distributor_id = _require_distributor(user)
    org_id = _resolve_org_id(user, auth_org_id)
    db = _db()
    cart = cart_service.get_active_cart(
        db, distributor_id=distributor_id, org_id=org_id
    )
    if cart is None:
        raise HTTPException(400, "Sem carrinho ativo")
    if not cart.get("items"):
        raise HTTPException(400, "Carrinho vazio")
    try:
        return orders_service.create_pedido_from_cart(
            db,
            cart_id=str(cart["id"]),
            distributor_id=distributor_id,
            org_id=org_id,
            placed_by=getattr(user, "id", None),
            observacoes=body.observacoes,
            admin_email=_resolve_admin_email(user),
        )
    except orders_service.OrderError as exc:
        raise HTTPException(400, str(exc)) from exc


__all__ = ["router"]
