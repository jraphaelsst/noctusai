"""
Products service — pure-ish query layer for the catalog domain.

Owns:
  • Product list/get against `adconnect.products`.
  • Per-distributor preferential pricing application (joins
    `precos_distribuidor` when caller is a distributor user; brand admin
    always sees `base_price`).
  • Filter/sort/search over products.
  • Category list with per-category product counts.

The router is responsible for:
  • Auth + role resolution (deciding `distributor_id` vs brand admin).
  • Mapping query-params to filter kwargs.
  • Returning the response envelope `{"data": [...]}`.

Pricing rule: if `distributor_id` is given, replace `base_price` with the
matching `preferential_price` row from `precos_distribuidor`; else keep
`base_price`. The output field surfaces as `effective_price` so callers
don't have to overwrite an existing column.

Schema source-of-truth: `migrations/001_adconnect.sql`. Cashback was on the
mock JSON (`products[i].cashback`) but lives in `adconnect.regras_recompensa`
in the canonical schema — sort-by-cashback is therefore deferred until the
rewards-domain Phase 4 lands.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal:
    """Coerce DB numeric values (str / float / Decimal) to Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _apply_filters(
    rows: list[dict[str, Any]],
    *,
    categoria_id: Optional[str] = None,
    search: Optional[str] = None,
    in_stock_only: bool = False,
) -> list[dict[str, Any]]:
    """Apply filter predicates client-side.

    Service-side filtering keeps the Supabase query simple and lets us
    mirror the legacy mock router's filter semantics exactly.
    """
    out = list(rows)
    if categoria_id and categoria_id != "all":
        out = [r for r in out if str(r.get("categoria_id") or "") == str(categoria_id)]
    if search and search.strip():
        ql = search.lower()
        out = [
            r
            for r in out
            if ql in (r.get("nome") or "").lower() or ql in (r.get("sku") or "").lower()
        ]
    if in_stock_only:
        out = [r for r in out if r.get("in_stock", True)]
    return out


def _apply_sort(rows: list[dict[str, Any]], sort: Optional[str]) -> list[dict[str, Any]]:
    """Sort by `name` (default) or `price` (ascending effective_price)."""
    out = list(rows)
    if sort == "price":
        out.sort(key=lambda r: _to_decimal(r.get("effective_price") or r.get("base_price")))
    else:  # default → name
        out.sort(key=lambda r: (r.get("nome") or "").lower())
    return out


def _apply_preferential_pricing(
    products: list[dict[str, Any]],
    preco_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Layer per-distributor preferential prices onto product rows.

    Adds an `effective_price` field on each product:
      • preferential_price when a `precos_distribuidor` row matches; else
      • base_price.
    Does NOT mutate the inputs in place — returns new dicts.
    """
    by_product: dict[str, Decimal] = {}
    for row in preco_rows:
        pid = row.get("product_id")
        price = row.get("preferential_price")
        if pid is not None and price is not None:
            by_product[str(pid)] = _to_decimal(price)

    enriched: list[dict[str, Any]] = []
    for p in products:
        product = dict(p)
        base = _to_decimal(product.get("base_price"))
        product["effective_price"] = by_product.get(str(product.get("id")), base)
        enriched.append(product)
    return enriched


def _set_brand_admin_pricing(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Brand admin always sees base_price as effective_price."""
    out: list[dict[str, Any]] = []
    for p in products:
        product = dict(p)
        product["effective_price"] = _to_decimal(product.get("base_price"))
        out.append(product)
    return out


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def list_products(
    db: Any,
    *,
    org_id: str,
    distributor_id: Optional[str] = None,
    categoria_id: Optional[str] = None,
    search: Optional[str] = None,
    in_stock_only: bool = False,
    sort: Optional[str] = None,
    only_active: bool = True,
) -> list[dict[str, Any]]:
    """List products in the brand catalog with per-distributor pricing applied.

    Args:
        db: Supabase client (admin or user-scoped — RLS still applies on
            user-scoped).
        org_id: brand org id (the catalog's owner).
        distributor_id: when present, applies preferential pricing for this
            distributor; None = brand admin view (sees base_price).
        categoria_id: filter by `products.categoria_id` (UUID).
        search: substring match on `nome` or `sku` (case-insensitive).
        in_stock_only: filter `in_stock = true`.
        sort: one of "name" (default), "price".
        only_active: filter `ativo = true`.

    Returns:
        List of product rows with `effective_price` populated.
    """
    query = db.table("products").select("*").eq("org_id", org_id)
    if only_active:
        query = query.eq("ativo", True)
    result = query.execute()
    products = list(result.data or [])

    if distributor_id:
        preco_q = (
            db.table("precos_distribuidor")
            .select("product_id, preferential_price")
            .eq("distributor_id", distributor_id)
        )
        preco_result = preco_q.execute()
        products = _apply_preferential_pricing(products, list(preco_result.data or []))
    else:
        products = _set_brand_admin_pricing(products)

    products = _apply_filters(
        products,
        categoria_id=categoria_id,
        search=search,
        in_stock_only=in_stock_only,
    )
    return _apply_sort(products, sort)


def get_product(
    db: Any,
    *,
    product_id: str,
    org_id: str,
    distributor_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Fetch a single product with effective pricing applied.

    Returns None if not found (router maps to 404).
    """
    result = (
        db.table("products")
        .select("*")
        .eq("id", product_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    if not rows:
        return None
    product = rows[0]

    if distributor_id:
        preco_result = (
            db.table("precos_distribuidor")
            .select("product_id, preferential_price")
            .eq("product_id", product_id)
            .eq("distributor_id", distributor_id)
            .execute()
        )
        product = _apply_preferential_pricing([product], list(preco_result.data or []))[0]
    else:
        product = _set_brand_admin_pricing([product])[0]
    return product


def list_categories(
    db: Any,
    *,
    org_id: str,
    only_active: bool = True,
) -> list[dict[str, Any]]:
    """List categories with per-category product counts.

    Mirrors the mock router's response shape — each row includes a `count`
    field with the number of products in the category. Schema column for
    "active" on categorias is `ativa` (not `ativo`); we use it correctly.
    """
    cat_q = db.table("categorias").select("*").eq("org_id", org_id)
    if only_active:
        cat_q = cat_q.eq("ativa", True)
    cat_result = cat_q.execute()
    categories = list(cat_result.data or [])

    prod_result = (
        db.table("products")
        .select("id, categoria_id")
        .eq("org_id", org_id)
        .execute()
    )
    products = list(prod_result.data or [])

    counts: dict[str, int] = {}
    for p in products:
        cid = str(p.get("categoria_id") or "")
        if cid:
            counts[cid] = counts.get(cid, 0) + 1

    return [
        {**c, "count": counts.get(str(c.get("id") or ""), 0)}
        for c in categories
    ]


__all__ = [
    "list_products",
    "get_product",
    "list_categories",
]
