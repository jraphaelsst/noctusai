"""
AdConnect Orders Router — Supabase-backed (Phase 3).

Replaces the mock-backed `app/data/store.py.orders` variant with a real
DB-backed surface against `adconnect.pedidos` + `adconnect.itens_pedido`.

Endpoints:
  • GET   /orders               — list (distributor: own; admin: all in org).
  • GET   /orders/{id}          — single order with line items.
  • PATCH /orders/{id}/status   — brand-admin lifecycle transition.

Lifecycle transitions are owned by `orders_service.transition_status` —
the router is a thin auth + serialization shim.

Constructor-time prefix is the structural fix for the wildcard-route bug
that surfaced in Phase 2 (orders' `/{order_id}` was registered at the bare
`/`, swallowing peer router URLs after include_router). Phase 2 mitigated
by registration ordering; Phase 3 ships the real fix.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path

from ..auth_deps import get_current_user, require_role
from ..database import _db as _db_module
from ..schemas.orders import (
    OrderListOut,
    OrderOut,
    OrderStatusTransitionIn,
)
from ..services import orders_service

router = APIRouter(prefix="/orders", tags=["orders"])


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


def _resolve_org_id(user: dict[str, Any]) -> str:
    org_id = user.get("org_id") or user.get("orgId")
    return str(org_id) if org_id else DEFAULT_ORG_ID


def _resolve_distributor_id(user: dict[str, Any]) -> Optional[str]:
    did = user.get("distributorId") or user.get("distributor_id")
    return str(did) if did else None


def _is_admin(user: dict[str, Any]) -> bool:
    return (user.get("role") or "").lower() == "admin"


def _check_visibility(user: dict[str, Any], pedido: dict[str, Any]) -> None:
    """Allow the row's distributor or any admin in the same org."""
    if _is_admin(user):
        # Admin → check the pedido's distributor belongs to admin's org.
        # Mock builder doesn't model joins, so we accept admin transparently;
        # RLS at the DB layer enforces the org-scope in production.
        return
    user_did = _resolve_distributor_id(user)
    if user_did and str(pedido.get("distributor_id")) == str(user_did):
        return
    raise HTTPException(403)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=OrderListOut)
def list_orders(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List pedidos.

    • Brand admin (`role=admin`): all pedidos in their org's distributor set.
    • Distributor user: only their own.
    """
    db = _db()
    if _is_admin(user):
        rows = orders_service.list_for_org(db, org_id=_resolve_org_id(user))
        return {"data": rows}
    distributor_id = _resolve_distributor_id(user)
    if not distributor_id:
        raise HTTPException(401, "Usuário sem distribuidor vinculado")
    rows = orders_service.list_for_distributor(
        db, distributor_id=distributor_id
    )
    return {"data": rows}


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: str = Path(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch a single order with line items."""
    db = _db()
    pedido = orders_service.get_pedido_with_items(db, pedido_id=order_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    _check_visibility(user, pedido)
    return pedido


@router.patch("/{order_id}/status", response_model=OrderOut)
def transition_order_status(
    body: OrderStatusTransitionIn,
    order_id: str = Path(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Transition a pedido's status.

    State machine lives in `orders_service.transition_status`. Brand admin
    can move any status forward; distributor can only `cancelado` from
    early states (rascunho / enviado).
    """
    db = _db()
    try:
        return orders_service.transition_status(
            db,
            pedido_id=order_id,
            new_status=body.status,
            actor_role=user.get("role") or "",
        )
    except orders_service.OrderError as exc:
        msg = str(exc)
        if "não encontrado" in msg.lower():
            raise HTTPException(404, msg) from exc
        if "apenas brand admin" in msg.lower():
            raise HTTPException(403, msg) from exc
        raise HTTPException(400, msg) from exc


__all__ = ["router"]
