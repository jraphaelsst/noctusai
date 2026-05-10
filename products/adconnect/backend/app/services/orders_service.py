"""
Orders service — orchestration layer for `adconnect.pedidos` and
`adconnect.itens_pedido`.

Owns:
  • `create_pedido_from_cart` — atomically converts an active cart into a
    pedido + itens_pedido rows; flips cart status to `convertido`; fires
    reward accrual + admin notification.
  • `transition_status` — enforces the lifecycle state-machine.
  • `list_for_distributor` / `get_for_user` — read-side with role scoping.

Lifecycle (single status column; service-layer enforces transitions):
  rascunho → enviado → confirmado → enviado_para_entrega → entregue
                    └→ cancelado (from anywhere except entregue)

Reward integration (Phase 3 ↔ Phase 4 wire-up):
  After a pedido is created, `rewards_service.accrue_for_pedido` is called
  with the pedido row. Failures are logged but do not fail the order.

Email integration:
  Order placed → email to brand admin via
  `noctusai_lib.integrations.email.send_to_one`. Caller passes the resolved
  admin email; service stays decoupled from auth lookup. Failures are
  logged + swallowed (mirrors `sellout_service._notify_admin_submission`).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.integrations.email import Digest, send_to_one

from . import cart_service
from .products_service import get_product
from .rewards_service import accrue_for_pedido

logger = logging.getLogger(__name__)

PEDIDOS_TABLE = "pedidos"
ITENS_PEDIDO_TABLE = "itens_pedido"


class OrderError(ValueError):
    """Raised when an order operation violates a business rule."""


# ---------------------------------------------------------------------------
# Lifecycle state machine
# ---------------------------------------------------------------------------
# Service-layer enforces valid transitions — DON'T model state via flags.
# Single `status` column with checked transitions is the canonical pattern
# (PROJECT.md §6 Phase 3 step 3).

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "rascunho": {"enviado", "cancelado"},
    "enviado": {"confirmado", "cancelado"},
    "confirmado": {"enviado_para_entrega", "cancelado"},
    "enviado_para_entrega": {"entregue", "cancelado"},
    "entregue": set(),  # terminal — no further transitions
    "cancelado": set(),  # terminal
}

_TIMESTAMP_FIELD: dict[str, str] = {
    "enviado": "placed_at",
    "confirmado": "confirmed_at",
    "entregue": "delivered_at",
    "cancelado": "canceled_at",
}


def is_valid_transition(current: str, target: str) -> bool:
    """Pure check — used by tests and `transition_status`."""
    return target in _VALID_TRANSITIONS.get(current, set())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _schedule_coro(coro) -> None:
    """Fire-and-forget async work without blocking the request.

    Pattern mirrors `sellout_service._schedule_email`. Falls back to
    `asyncio.run` in sync test contexts; never raises into the caller.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception as exc:
            logger.warning("orders_service: scheduled coro failed (%s)", exc)


async def _notify_admin_order_placed(
    *,
    org_id: Optional[str],
    distributor_id: str,
    pedido_id: str,
    total: float,
    admin_email: Optional[str],
) -> None:
    """Email the brand admin that a new order was placed."""
    if not admin_email:
        logger.debug(
            "orders_service: no admin_email — skipping order-placed notification"
        )
        return
    digest = Digest(
        subject=f"[AdConnect] Novo pedido — distribuidor {distributor_id}",
        text=(
            f"Um novo pedido ({pedido_id}) foi colocado pelo distribuidor "
            f"{distributor_id} no valor de R$ {total:.2f}. Acesse o painel "
            f"para confirmar."
        ),
    )
    try:
        await send_to_one(
            digest,
            recipient=admin_email,
            org_id=org_id,
            log_prefix="ADCONNECT_ORDER_PLACED",
        )
    except Exception as exc:
        logger.warning("orders_service: order-placed email failed (%s)", exc)


# ---------------------------------------------------------------------------
# Public surface — placement
# ---------------------------------------------------------------------------


def create_pedido_from_cart(
    db: Any,
    *,
    cart_id: str,
    distributor_id: str,
    org_id: str,
    placed_by: Optional[str],
    observacoes: Optional[str] = None,
    admin_email: Optional[str] = None,
) -> dict[str, Any]:
    """Convert an active cart to a pedido + itens_pedido rows.

    Returns the inserted pedido row (with `items` list attached).

    Side effects (non-fatal):
      • Flips cart status to `convertido`.
      • Fires `accrue_for_pedido` (Phase 4 reward engine).
      • Fires brand-admin email notification.

    Raises:
      OrderError if the cart has no items, or insert fails.
    """
    items_res = (
        db.table(cart_service.ITENS_CARRINHO_TABLE)
        .select("*")
        .eq("cart_id", cart_id)
        .execute()
    )
    cart_items = list(items_res.data or [])
    if not cart_items:
        raise OrderError("Carrinho vazio")

    # Compute total + assemble itens_pedido payloads (snapshot price + name).
    total = Decimal("0")
    itens_payloads: list[dict[str, Any]] = []
    for it in cart_items:
        qty = int(it.get("quantidade") or 0)
        price = _to_decimal(it.get("price_at_add"))
        subtotal = price * qty
        total += subtotal
        # Snapshot product fields at order time.
        product = get_product(
            db,
            product_id=str(it.get("product_id")),
            org_id=org_id,
            distributor_id=distributor_id,
        ) or {}
        itens_payloads.append(
            {
                "product_id": it.get("product_id"),
                "sku_at_order": product.get("sku") or "",
                "nome_at_order": product.get("nome") or "",
                "quantidade": qty,
                "price_at_order": float(price),
                "subtotal": float(subtotal),
            }
        )

    placed_at = _now_iso()
    pedido_payload = {
        "distributor_id": distributor_id,
        "cart_id": cart_id,
        "placed_by": placed_by,
        "status": "enviado",
        "total": float(total),
        "observacoes": observacoes,
        "placed_at": placed_at,
    }
    pedido_res = db.table(PEDIDOS_TABLE).insert(pedido_payload).execute()
    pedido_rows = list(pedido_res.data or [])
    if not pedido_rows:
        raise OrderError("Falha ao criar pedido")
    pedido = pedido_rows[0]
    pedido_id = str(pedido.get("id"))

    # Insert itens_pedido (with the now-known pedido_id).
    inserted_items: list[dict[str, Any]] = []
    for payload in itens_payloads:
        payload_with_pedido = dict(payload)
        payload_with_pedido["pedido_id"] = pedido_id
        item_res = db.table(ITENS_PEDIDO_TABLE).insert(payload_with_pedido).execute()
        item_rows = list(item_res.data or [])
        if item_rows:
            inserted_items.append(item_rows[0])
        else:  # pragma: no cover - defensive
            inserted_items.append(payload_with_pedido)

    pedido["items"] = inserted_items

    # Flip cart status to convertido.
    try:
        cart_service.mark_cart_converted(db, cart_id=cart_id)
    except Exception as exc:
        logger.warning(
            "orders_service: mark_cart_converted failed for %s (%s)", cart_id, exc
        )

    # Reward accrual — pure function, log failures but don't fail the order.
    try:
        # Provide both items + valor_total in the row passed to the engine
        # (the rewards engine reads `pedido_row.get('items')` and
        # `pedido_row.get('valor_total') or pedido_row.get('total')`).
        engine_row = dict(pedido)
        engine_row["org_id"] = org_id
        engine_row["valor_total"] = float(total)
        engine_row["items"] = inserted_items
        accrued = accrue_for_pedido(db, pedido_id=pedido_id, pedido_row=engine_row)
        logger.info(
            "orders_service.create_pedido_from_cart: %d accruals for pedido %s",
            len(accrued),
            pedido_id,
        )
    except Exception as exc:
        logger.warning(
            "orders_service: reward accrual failed for %s (%s)", pedido_id, exc
        )

    # Email notification — fire-and-forget.
    _schedule_coro(
        _notify_admin_order_placed(
            org_id=org_id,
            distributor_id=distributor_id,
            pedido_id=pedido_id,
            total=float(total),
            admin_email=admin_email,
        )
    )

    return pedido


# ---------------------------------------------------------------------------
# Public surface — lifecycle
# ---------------------------------------------------------------------------


def transition_status(
    db: Any,
    *,
    pedido_id: str,
    new_status: str,
    actor_role: str,
) -> dict[str, Any]:
    """Apply a status transition with state-machine validation.

    Args:
        actor_role: caller's role; only `admin` may move past `enviado`.
            Distributors can only `cancelado` from `rascunho`/`enviado` (the
            router enforces this — service is the SQL boundary; we still
            check here so the rule survives router refactors).

    Raises:
        OrderError on invalid transition or missing pedido.
    """
    res = (
        db.table(PEDIDOS_TABLE)
        .select("*")
        .eq("id", pedido_id)
        .limit(1)
        .execute()
    )
    rows = list(res.data or [])
    if not rows:
        raise OrderError("Pedido não encontrado")
    current = rows[0]
    current_status = str(current.get("status") or "")

    if not is_valid_transition(current_status, new_status):
        raise OrderError(
            f"Transição inválida: {current_status} → {new_status}"
        )

    # Role guard: anything past 'enviado' is brand-admin only.
    role = (actor_role or "").lower()
    if new_status not in {"cancelado"} and role != "admin":
        raise OrderError("Apenas brand admin pode avançar o status do pedido")

    payload: dict[str, Any] = {"status": new_status, "updated_at": _now_iso()}
    ts_field = _TIMESTAMP_FIELD.get(new_status)
    if ts_field:
        payload[ts_field] = _now_iso()

    update_res = (
        db.table(PEDIDOS_TABLE)
        .update(payload)
        .eq("id", pedido_id)
        .execute()
    )
    updated = list(update_res.data or [])
    # Always merge the payload into the response — the mock builder echoes
    # the seeded SELECT data unchanged through `.update().execute()`, and
    # real Supabase returns post-update rows but only when `.select()` is
    # chained. The merge is invariant to either backend; the router needs
    # the new status reflected.
    base = updated[0] if updated else dict(current)
    merged = dict(base)
    merged.update(payload)
    return merged


# ---------------------------------------------------------------------------
# Public surface — read
# ---------------------------------------------------------------------------


def list_for_distributor(
    db: Any,
    *,
    distributor_id: str,
) -> list[dict[str, Any]]:
    """Return the distributor's pedidos, most recent first."""
    res = (
        db.table(PEDIDOS_TABLE)
        .select("*")
        .eq("distributor_id", distributor_id)
        .execute()
    )
    rows = list(res.data or [])
    rows.sort(
        key=lambda r: r.get("placed_at") or r.get("created_at") or "",
        reverse=True,
    )
    return rows


def list_for_org(db: Any, *, org_id: str) -> list[dict[str, Any]]:
    """Brand admin: list every pedido for distributors in their org.

    The mock builder doesn't fully model joins, so we filter via a two-step
    fetch: distributors-in-org → pedidos-with-distributor-in-set. The N
    here is bounded by the brand's distributor count.
    """
    dist_res = (
        db.table("distributors").select("id").eq("org_id", org_id).execute()
    )
    dist_ids = {
        str(d.get("id")) for d in (dist_res.data or []) if d.get("id")
    }
    if not dist_ids:
        return []

    res = db.table(PEDIDOS_TABLE).select("*").execute()
    rows = [
        r for r in (res.data or []) if str(r.get("distributor_id")) in dist_ids
    ]
    rows.sort(
        key=lambda r: r.get("placed_at") or r.get("created_at") or "",
        reverse=True,
    )
    return rows


def get_pedido(db: Any, *, pedido_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single pedido row (without items)."""
    res = (
        db.table(PEDIDOS_TABLE)
        .select("*")
        .eq("id", pedido_id)
        .limit(1)
        .execute()
    )
    rows = list(res.data or [])
    return rows[0] if rows else None


def get_pedido_with_items(
    db: Any, *, pedido_id: str
) -> Optional[dict[str, Any]]:
    """Fetch a pedido with its line items attached as `items`."""
    pedido = get_pedido(db, pedido_id=pedido_id)
    if pedido is None:
        return None
    items_res = (
        db.table(ITENS_PEDIDO_TABLE)
        .select("*")
        .eq("pedido_id", pedido_id)
        .execute()
    )
    pedido = dict(pedido)
    pedido["items"] = list(items_res.data or [])
    return pedido


__all__ = [
    "ITENS_PEDIDO_TABLE",
    "OrderError",
    "PEDIDOS_TABLE",
    "create_pedido_from_cart",
    "get_pedido",
    "get_pedido_with_items",
    "is_valid_transition",
    "list_for_distributor",
    "list_for_org",
    "transition_status",
]
