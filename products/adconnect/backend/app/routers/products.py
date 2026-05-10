"""
AdConnect Products Router — Supabase-backed catalog query surface.

Replaces the mock-JSON-backed shape (was `from ..data.store import store`).
The route shape is preserved verbatim so the frontend can drop in the new
backend without changes.

Endpoints:
  • GET /products                   — list with filter/sort/search/inStock
  • GET /products/categories        — list categories with product counts
  • GET /products/{product_id}      — fetch one product (preferential pricing
    applied when caller is a distributor user)

Auth + pricing rule:
  • Brand admin (role="admin") sees `effective_price = base_price`.
  • Distributor user (role="customer" + distributorId set) sees the matching
    `precos_distribuidor.preferential_price` row when one exists, else
    `base_price`.

The service layer (`app.services.products_service`) owns the actual queries
and pricing logic; this router handles auth + query-param mapping + envelope.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth_deps import get_current_user
from ..database import get_admin_client
from ..services import products_service

# Prefix is set here (rather than via main.py's router.prefix-after-construction
# loop, which is a no-op for routes already added — see findings.md).
router = APIRouter(prefix="/products", tags=["products"])


# ---------------------------------------------------------------------------
# Auth-derived helpers
# ---------------------------------------------------------------------------


def _resolve_org_id(user: dict[str, Any]) -> str:
    """Brand `org_id` for the catalog query.

    The custom JWT carries `org_id` when set; otherwise we fall back to a
    deterministic dev org (single-instance V1 — see PROJECT.md §4 "Multi-brand
    multi-tenancy is V2"). The fallback ensures local dev / unauth-token
    flows still serve a catalog without a Supabase org row provisioning step.
    """
    org_id = user.get("org_id") or user.get("orgId")
    if org_id:
        return str(org_id)
    # Single-instance V1: derive a stable org_id so queries return rows
    # seeded under a known UUID. Tests override via mocks.
    return "00000000-0000-0000-0000-000000000001"


def _resolve_distributor_id(user: dict[str, Any]) -> Optional[str]:
    """Return the caller's `distributor_id` if they're a distributor user."""
    role = (user.get("role") or "").lower()
    if role == "admin":
        return None  # Brand admin sees base_price
    did = user.get("distributorId") or user.get("distributor_id")
    return str(did) if did else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
def list_products(
    category: str | None = None,
    q: str | None = None,
    sort: str | None = Query(None, pattern="^(name|price)$"),
    inStockOnly: bool | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List products with filter / search / sort / in-stock filtering.

    Query params (preserved from mock router where the canonical schema
    permits — `cashback` sort is dropped since cashback now lives on
    `regras_recompensa`, not on `products`):
      • category: categoria_id (UUID) or "all" / omitted.
      • q: substring search on `nome` or `sku` (case-insensitive).
      • sort: "name" (default) | "price".
      • inStockOnly: filter to in-stock products only.
    """
    db = get_admin_client()
    org_id = _resolve_org_id(user)
    distributor_id = _resolve_distributor_id(user)
    items = products_service.list_products(
        db,
        org_id=org_id,
        distributor_id=distributor_id,
        categoria_id=category,
        search=q,
        in_stock_only=bool(inStockOnly),
        sort=sort,
    )
    return {"data": items}


@router.get("/categories")
def list_categories(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List categories with per-category product counts."""
    db = get_admin_client()
    org_id = _resolve_org_id(user)
    items = products_service.list_categories(db, org_id=org_id)
    return {"data": items}


@router.get("/{product_id}")
def get_product(
    product_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch a single product with effective pricing applied."""
    db = get_admin_client()
    org_id = _resolve_org_id(user)
    distributor_id = _resolve_distributor_id(user)
    product = products_service.get_product(
        db,
        product_id=product_id,
        org_id=org_id,
        distributor_id=distributor_id,
    )
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    return product
