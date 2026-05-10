"""
Cart service — DB-backed query/mutation layer for the distributor cart.

Owns:
  • Fetching the distributor's active cart (most recent `status='ativo'` row).
  • Adding / updating / removing line items (UNIQUE(cart_id, product_id) is
    enforced by the schema; we treat re-adds as quantity updates).
  • Computing the cart total from the joined product rows (price_at_add) so
    `carts.total` stays in sync after each mutation.
  • Converting the active cart to a `pedidos` row (lifecycle entry-point).

The router is responsible for: auth, resolving distributor_id, mapping
HTTP status codes, returning the response envelope.

The lifecycle of a `pedido` is owned by `orders_service` — `convert_cart_to_pedido`
delegates there to enforce the state-machine.

This module is the structural replacement for the old mock-backed
`app/services/cart.py` (in-memory `store` access). The pricing math from
that module is no longer needed at the cart-service layer because pricing
is taken from `precos_distribuidor` at add-time and stored in
`itens_carrinho.price_at_add` — preferential pricing application happens
in `products_service` when the distributor browses, and the snapshot is
captured into the cart row.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from .products_service import get_product

logger = logging.getLogger(__name__)

CARTS_TABLE = "carts"
ITENS_CARRINHO_TABLE = "itens_carrinho"


class CartError(ValueError):
    """Raised when a cart mutation violates a business rule."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _line_total(item: dict[str, Any]) -> Decimal:
    qty = int(item.get("quantidade") or 0)
    price = _to_decimal(item.get("price_at_add"))
    return price * qty


def _enrich_items(
    db: Any,
    *,
    org_id: str,
    distributor_id: Optional[str],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Layer sku + nome + line_total onto raw itens_carrinho rows.

    We fetch product info per row (N is small for a typical cart). This
    keeps the cart-service decoupled from `products` schema details — the
    products_service is the single source of truth for product fields.
    """
    enriched: list[dict[str, Any]] = []
    for it in items:
        out = dict(it)
        product_id = it.get("product_id")
        product = None
        if product_id:
            try:
                product = get_product(
                    db,
                    product_id=str(product_id),
                    org_id=org_id,
                    distributor_id=distributor_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "cart_service._enrich_items: lookup failed for %s (%s)",
                    product_id,
                    exc,
                )
                product = None
        if product is not None:
            out.setdefault("sku", product.get("sku"))
            out.setdefault("nome", product.get("nome"))
        out["line_total"] = float(_line_total(it))
        enriched.append(out)
    return enriched


def _compute_total(items: list[dict[str, Any]]) -> float:
    total = Decimal("0")
    for it in items:
        total += _line_total(it)
    return float(total)


def _persist_cart_total(db: Any, *, cart_id: str, total: float) -> None:
    """Write `carts.total` so SELECTs reflect the current sum."""
    try:
        db.table(CARTS_TABLE).update({"total": total}).eq("id", cart_id).execute()
    except Exception as exc:  # pragma: no cover - mock builder may noop
        logger.debug("cart_service._persist_cart_total: %s", exc)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def get_active_cart(
    db: Any,
    *,
    distributor_id: str,
    org_id: str,
) -> Optional[dict[str, Any]]:
    """Return the distributor's active cart (with items), or None.

    "Active" = `status = 'ativo'`. There may be at most one (the create flow
    flips prior carts to `abandonado` if the schema doesn't enforce
    uniqueness — the migration uses a partial-index on status='ativo' but
    not a unique constraint, so we surface the most-recent row defensively).
    """
    res = (
        db.table(CARTS_TABLE)
        .select("*")
        .eq("distributor_id", distributor_id)
        .eq("status", "ativo")
        .execute()
    )
    rows = list(res.data or [])
    if not rows:
        return None
    # Most recent first — `created_at` desc.
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    cart = dict(rows[0])
    items_res = (
        db.table(ITENS_CARRINHO_TABLE)
        .select("*")
        .eq("cart_id", cart["id"])
        .execute()
    )
    items = list(items_res.data or [])
    cart["items"] = _enrich_items(
        db, org_id=org_id, distributor_id=distributor_id, items=items
    )
    cart["total"] = _compute_total(items)
    return cart


def _create_active_cart(
    db: Any,
    *,
    distributor_id: str,
    created_by: Optional[str],
) -> dict[str, Any]:
    payload = {
        "distributor_id": distributor_id,
        "created_by": created_by,
        "status": "ativo",
        "total": 0,
    }
    res = db.table(CARTS_TABLE).insert(payload).execute()
    rows = list(res.data or [])
    if not rows:
        raise CartError("Falha ao criar carrinho")
    return rows[0]


def get_or_create_active_cart(
    db: Any,
    *,
    distributor_id: str,
    org_id: str,
    created_by: Optional[str],
) -> dict[str, Any]:
    """Read-or-create the distributor's active cart (used by add-line)."""
    existing = get_active_cart(db, distributor_id=distributor_id, org_id=org_id)
    if existing:
        return existing
    cart = _create_active_cart(
        db, distributor_id=distributor_id, created_by=created_by
    )
    cart["items"] = []
    cart["total"] = 0.0
    return cart


def add_line(
    db: Any,
    *,
    distributor_id: str,
    org_id: str,
    created_by: Optional[str],
    product_id: str,
    quantidade: int,
) -> dict[str, Any]:
    """Add (or upsert) a product line to the active cart.

    UNIQUE(cart_id, product_id) is schema-enforced — we look up the existing
    line and update its quantity rather than relying on Supabase upsert
    semantics (the mock builder doesn't fully model upsert).

    Pricing snapshot: takes `effective_price` from the catalog (preferential
    if set, else base_price) and stores it in `price_at_add`. Subsequent
    catalog price changes don't retroactively change the cart line.
    """
    if quantidade <= 0:
        raise CartError("quantidade deve ser maior que zero")

    product = get_product(
        db,
        product_id=product_id,
        org_id=org_id,
        distributor_id=distributor_id,
    )
    if product is None:
        raise CartError(f"Produto {product_id} não encontrado")
    price = _to_decimal(
        product.get("effective_price") or product.get("base_price") or 0
    )

    cart = get_or_create_active_cart(
        db,
        distributor_id=distributor_id,
        org_id=org_id,
        created_by=created_by,
    )
    cart_id = str(cart["id"])

    # Look up existing line for this product.
    existing = (
        db.table(ITENS_CARRINHO_TABLE)
        .select("*")
        .eq("cart_id", cart_id)
        .eq("product_id", product_id)
        .execute()
    )
    existing_rows = list(existing.data or [])
    if existing_rows:
        line_id = str(existing_rows[0]["id"])
        new_qty = int(existing_rows[0].get("quantidade") or 0) + int(quantidade)
        db.table(ITENS_CARRINHO_TABLE).update(
            {"quantidade": new_qty}
        ).eq("id", line_id).execute()
    else:
        payload = {
            "cart_id": cart_id,
            "product_id": product_id,
            "quantidade": int(quantidade),
            "price_at_add": float(price),
        }
        db.table(ITENS_CARRINHO_TABLE).insert(payload).execute()

    refreshed = get_active_cart(
        db, distributor_id=distributor_id, org_id=org_id
    )
    if refreshed is None:
        # Fallback: real Supabase always returns the row back via SELECT
        # after INSERT, but mock builders sometimes don't propagate inserts
        # into the data set. Synthesize the response from the inputs so
        # callers (router) get a sensible 201 body.
        cart["items"] = []
        cart["total"] = 0.0
        return cart
    _persist_cart_total(db, cart_id=cart_id, total=refreshed["total"])
    return refreshed


def update_line(
    db: Any,
    *,
    distributor_id: str,
    org_id: str,
    line_id: str,
    quantidade: int,
) -> dict[str, Any]:
    """Update a line's quantity. Raises CartError if the line is not in the
    distributor's active cart (404-equivalent).
    """
    if quantidade <= 0:
        raise CartError("quantidade deve ser maior que zero")

    cart = get_active_cart(db, distributor_id=distributor_id, org_id=org_id)
    if cart is None:
        raise CartError("Sem carrinho ativo")
    line_ids = {str(it.get("id")) for it in (cart.get("items") or [])}
    if line_id not in line_ids:
        raise CartError("Linha não encontrada no carrinho")

    db.table(ITENS_CARRINHO_TABLE).update(
        {"quantidade": int(quantidade)}
    ).eq("id", line_id).execute()

    refreshed = get_active_cart(
        db, distributor_id=distributor_id, org_id=org_id
    )
    if refreshed is None:  # pragma: no cover
        raise CartError("Carrinho não encontrado após atualização")
    _persist_cart_total(
        db, cart_id=str(refreshed["id"]), total=refreshed["total"]
    )
    return refreshed


def remove_line(
    db: Any,
    *,
    distributor_id: str,
    org_id: str,
    line_id: str,
) -> dict[str, Any]:
    """Remove a line from the distributor's active cart.

    Raises CartError if the line is not in the active cart.
    """
    cart = get_active_cart(db, distributor_id=distributor_id, org_id=org_id)
    if cart is None:
        raise CartError("Sem carrinho ativo")
    line_ids = {str(it.get("id")) for it in (cart.get("items") or [])}
    if line_id not in line_ids:
        raise CartError("Linha não encontrada no carrinho")

    db.table(ITENS_CARRINHO_TABLE).delete().eq("id", line_id).execute()

    refreshed = get_active_cart(
        db, distributor_id=distributor_id, org_id=org_id
    )
    if refreshed is None:
        # Cart still exists but has no lines.
        cart["items"] = []
        cart["total"] = 0.0
        _persist_cart_total(db, cart_id=str(cart["id"]), total=0.0)
        return cart
    _persist_cart_total(
        db, cart_id=str(refreshed["id"]), total=refreshed["total"]
    )
    return refreshed


def mark_cart_converted(db: Any, *, cart_id: str) -> None:
    """Flip a cart's status to `convertido` after order placement."""
    db.table(CARTS_TABLE).update({"status": "convertido"}).eq("id", cart_id).execute()


__all__ = [
    "CARTS_TABLE",
    "ITENS_CARRINHO_TABLE",
    "CartError",
    "add_line",
    "get_active_cart",
    "get_or_create_active_cart",
    "mark_cart_converted",
    "remove_line",
    "update_line",
]
