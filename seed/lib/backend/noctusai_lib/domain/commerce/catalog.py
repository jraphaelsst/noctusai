"""Catalog -- categories, products, offers.

Every function takes the product's schema-scoped PostgREST `db` and the caller's
`org_id`, and EVERY query is filtered by that org: an id from another org is
indistinguishable from a missing one (404), never a cross-tenant read or write.
Unbounded reads page through the seed's shared pager (PostgREST silently caps a
response at 1 000 rows).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import first, get_row, like_term, new_id, now_iso, page_rows, slugify, tbl
from .errors import CommerceError, conflict, invalid, not_found
from .fees import fee_estimate
from .types import FulfillmentType, ProductStatus, ProductType

_CATEGORIES = "commerce_categories"
_PRODUCTS = "commerce_products"
_OFFERS = "commerce_offers"
_MEDIA = "commerce_media"

#: The fulfillment a product type gets when the author does not pick one.
DEFAULT_FULFILLMENT: dict[str, str] = {
    ProductType.DIGITAL.value: FulfillmentType.DIGITAL_DELIVERY.value,
    ProductType.PHYSICAL.value: FulfillmentType.SHIPPING.value,
    ProductType.SERVICE.value: FulfillmentType.NONE.value,
    ProductType.PRINT_ON_DEMAND.value: FulfillmentType.SHIPPING.value,
}


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def _clean(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        value = _plain(value)
        out[key] = str(value) if isinstance(value, UUID) else value
    return out


def _slug_taken(db: Any, table: str, org_id: Any, slug: str, *, except_id: Optional[str] = None) -> bool:
    rows = tbl(db, table).select("id").eq("org_id", str(org_id)).eq("slug", slug).execute().data or []
    return any(str(r["id"]) != str(except_id) for r in rows)


def _unique_slug(db: Any, table: str, org_id: Any, base: str) -> str:
    slug = base
    for n in range(2, 60):
        if not _slug_taken(db, table, org_id, slug):
            return slug
        slug = f"{base}-{n}"
    raise conflict("slug_em_uso", "Não foi possível gerar um endereço (slug) único.")


# ─── categories ──────────────────────────────────────────────────────────


def list_categories(db: Any, org_id: Any) -> list[dict]:
    rows = paged_rows(db, _CATEGORIES, org_id)
    return sorted(rows, key=lambda r: (r.get("position", 0), r.get("name", "")))


def _check_parent(db: Any, org_id: Any, parent_id: Optional[str], *, self_id: Optional[str] = None) -> None:
    if not parent_id:
        return
    if self_id and str(parent_id) == str(self_id):
        raise invalid("parent_id", "Uma categoria não pode ser pai de si mesma.")
    seen: set[str] = set()
    cursor: Optional[str] = str(parent_id)
    while cursor:
        if cursor in seen:
            break
        seen.add(cursor)
        node = get_row(db, _CATEGORIES, org_id, cursor)
        if node is None:
            raise invalid("parent_id", "Categoria pai inexistente.")
        if self_id and str(node.get("parent_id") or "") == str(self_id):
            raise invalid("parent_id", "Isso criaria um ciclo na árvore de categorias.")
        cursor = str(node["parent_id"]) if node.get("parent_id") else None


def create_category(db: Any, org_id: Any, data: Mapping[str, Any]) -> dict:
    d = _clean(data)
    slug = slugify(d.get("slug") or d["name"])
    if _slug_taken(db, _CATEGORIES, org_id, slug):
        raise conflict("slug_em_uso", "Já existe uma categoria com este endereço (slug).")
    _check_parent(db, org_id, d.get("parent_id"))
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "slug": slug,
        "name": d["name"],
        "parent_id": d.get("parent_id"),
        "position": d.get("position", 0),
        "created_at": now,
        "updated_at": now,
    }
    return first(tbl(db, _CATEGORIES).insert(row).execute()) or row


def update_category(db: Any, org_id: Any, category_id: Any, changes: Mapping[str, Any]) -> dict:
    current = get_row(db, _CATEGORIES, org_id, category_id)
    if current is None:
        raise not_found("Categoria")
    d = _clean(changes)
    patch: dict[str, Any] = {}
    if "name" in d and d["name"] is not None:
        patch["name"] = d["name"]
    if "slug" in d and d["slug"]:
        slug = slugify(d["slug"])
        if _slug_taken(db, _CATEGORIES, org_id, slug, except_id=str(category_id)):
            raise conflict("slug_em_uso", "Já existe uma categoria com este endereço (slug).")
        patch["slug"] = slug
    if "parent_id" in d:
        _check_parent(db, org_id, d["parent_id"], self_id=str(category_id))
        patch["parent_id"] = d["parent_id"]
    if "position" in d and d["position"] is not None:
        patch["position"] = d["position"]
    if not patch:
        return current
    patch["updated_at"] = now_iso()
    updated = (
        tbl(db, _CATEGORIES).update(patch).eq("org_id", str(org_id)).eq("id", str(category_id)).execute()
    )
    return first(updated) or {**current, **patch}


def delete_category(db: Any, org_id: Any, category_id: Any) -> None:
    if get_row(db, _CATEGORIES, org_id, category_id) is None:
        raise not_found("Categoria")
    tbl(db, _CATEGORIES).delete().eq("org_id", str(org_id)).eq("id", str(category_id)).execute()


# ─── products ────────────────────────────────────────────────────────────


def list_products(
    db: Any,
    org_id: Any,
    *,
    status: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int, int, int]:
    def refine(query):
        if q and q.strip():
            query = query.ilike("title", like_term(q))
        return query

    filters = {"status": ProductStatus(status).value} if status else None
    return page_rows(db, _PRODUCTS, org_id, page=page, page_size=page_size, refine=refine, eq_filters=filters)


def _category_ok(db: Any, org_id: Any, category_id: Optional[str]) -> None:
    if category_id and get_row(db, _CATEGORIES, org_id, category_id) is None:
        raise invalid("category_id", "Categoria inexistente.")


def create_product(db: Any, org_id: Any, data: Mapping[str, Any]) -> dict:
    d = _clean(data)
    if d.get("slug"):
        slug = slugify(d["slug"])
        if _slug_taken(db, _PRODUCTS, org_id, slug):
            raise conflict("slug_em_uso", "Já existe um produto com este endereço (slug).")
    else:
        slug = _unique_slug(db, _PRODUCTS, org_id, slugify(d["title"]))
    _category_ok(db, org_id, d.get("category_id"))
    ptype = d["product_type"]
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "slug": slug,
        "title": d["title"],
        "description": d.get("description", ""),
        "product_type": ptype,
        "fulfillment_type": d.get("fulfillment_type") or DEFAULT_FULFILLMENT[ptype],
        "status": ProductStatus.DRAFT.value,  # publishing is a guarded, separate act
        "category_id": d.get("category_id"),
        "attributes": d.get("attributes") or {},
        "tax_treatment_override": d.get("tax_treatment_override"),
        "created_at": now,
        "updated_at": now,
    }
    try:
        return first(tbl(db, _PRODUCTS).insert(row).execute()) or row
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if is_unique_violation(exc):
            raise conflict("slug_em_uso", "Já existe um produto com este endereço (slug).") from exc
        raise


def get_product(db: Any, org_id: Any, product_id: Any) -> dict:
    row = get_row(db, _PRODUCTS, org_id, product_id)
    if row is None:
        raise not_found("Produto")
    return row


def update_product(db: Any, org_id: Any, product_id: Any, changes: Mapping[str, Any]) -> dict:
    current = get_product(db, org_id, product_id)
    d = _clean(changes)
    d.pop("status", None)  # status only moves through set_product_status
    patch: dict[str, Any] = {}
    for key in ("title", "description", "product_type", "fulfillment_type", "attributes", "tax_treatment_override"):
        if key in d and (d[key] is not None or key == "tax_treatment_override"):
            patch[key] = d[key]
    if "slug" in d and d["slug"]:
        slug = slugify(d["slug"])
        if _slug_taken(db, _PRODUCTS, org_id, slug, except_id=str(product_id)):
            raise conflict("slug_em_uso", "Já existe um produto com este endereço (slug).")
        patch["slug"] = slug
    if "category_id" in d:
        _category_ok(db, org_id, d["category_id"])
        patch["category_id"] = d["category_id"]
    if not patch:
        return current
    patch["updated_at"] = now_iso()
    updated = tbl(db, _PRODUCTS).update(patch).eq("org_id", str(org_id)).eq("id", str(product_id)).execute()
    return first(updated) or {**current, **patch}


def active_offers(db: Any, org_id: Any, product_id: Any) -> list[dict]:
    rows = paged_rows(db, _OFFERS, org_id, eq_filters={"product_id": str(product_id)})
    return sorted([r for r in rows if r.get("active")], key=lambda r: (r.get("position", 0), r["id"]))


def set_product_status(db: Any, org_id: Any, product_id: Any, status: Any) -> dict:
    """Move a product through its lifecycle. Publishing needs >= 1 ACTIVE offer
    (a published product nobody can buy is a broken storefront card)."""
    target = ProductStatus(_plain(status))
    current = get_product(db, org_id, product_id)
    if target is ProductStatus.PUBLISHED and not active_offers(db, org_id, product_id):
        raise CommerceError(
            "sem_oferta_ativa", "Para publicar, o produto precisa de ao menos uma oferta ativa.", 422, field="status"
        )
    if current["status"] == target.value:
        return current
    patch = {"status": target.value, "updated_at": now_iso()}
    updated = tbl(db, _PRODUCTS).update(patch).eq("org_id", str(org_id)).eq("id", str(product_id)).execute()
    return first(updated) or {**current, **patch}


def delete_product_rows(db: Any, org_id: Any, product_id: Any) -> list[dict]:
    """Delete the product + its offers/media ROWS; returns the media rows so the
    caller can remove the storage objects. Order items keep their snapshot
    (`ON DELETE SET NULL` on the FKs)."""
    get_product(db, org_id, product_id)
    media = paged_rows(db, _MEDIA, org_id, eq_filters={"product_id": str(product_id)})
    tbl(db, _MEDIA).delete().eq("org_id", str(org_id)).eq("product_id", str(product_id)).execute()
    tbl(db, _OFFERS).delete().eq("org_id", str(org_id)).eq("product_id", str(product_id)).execute()
    tbl(db, _PRODUCTS).delete().eq("org_id", str(org_id)).eq("id", str(product_id)).execute()
    return media


# ─── offers ──────────────────────────────────────────────────────────────


def with_fee_estimate(offer: Mapping[str, Any]) -> dict:
    return {**offer, "fee_estimate": fee_estimate(int(offer["price_cents"]))}


def list_offers(db: Any, org_id: Any, product_id: Any) -> list[dict]:
    get_product(db, org_id, product_id)
    rows = paged_rows(db, _OFFERS, org_id, eq_filters={"product_id": str(product_id)})
    rows.sort(key=lambda r: (r.get("position", 0), str(r["id"])))
    return [with_fee_estimate(r) for r in rows]


def create_offer(db: Any, org_id: Any, product_id: Any, data: Mapping[str, Any]) -> dict:
    get_product(db, org_id, product_id)
    d = _clean(data)
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": str(org_id),
        "product_id": str(product_id),
        "name": d["name"],
        "price_cents": int(d["price_cents"]),
        "currency": d.get("currency", "BRL"),
        "active": bool(d.get("active", True)),
        "position": int(d.get("position", 0)),
        "created_at": now,
        "updated_at": now,
    }
    return with_fee_estimate(first(tbl(db, _OFFERS).insert(row).execute()) or row)


def _get_offer(db: Any, org_id: Any, product_id: Any, offer_id: Any) -> dict:
    row = get_row(db, _OFFERS, org_id, offer_id)
    if row is None or str(row["product_id"]) != str(product_id):
        raise not_found("Oferta")
    return row


def update_offer(db: Any, org_id: Any, product_id: Any, offer_id: Any, changes: Mapping[str, Any]) -> dict:
    current = _get_offer(db, org_id, product_id, offer_id)
    d = _clean(changes)
    patch = {k: d[k] for k in ("name", "price_cents", "currency", "active", "position") if d.get(k) is not None}
    if not patch:
        return with_fee_estimate(current)
    patch["updated_at"] = now_iso()
    updated = tbl(db, _OFFERS).update(patch).eq("org_id", str(org_id)).eq("id", str(offer_id)).execute()
    return with_fee_estimate(first(updated) or {**current, **patch})


def delete_offer(db: Any, org_id: Any, product_id: Any, offer_id: Any) -> None:
    _get_offer(db, org_id, product_id, offer_id)
    tbl(db, _OFFERS).delete().eq("org_id", str(org_id)).eq("id", str(offer_id)).execute()


__all__ = [
    "DEFAULT_FULFILLMENT",
    "active_offers",
    "create_category",
    "create_offer",
    "create_product",
    "delete_category",
    "delete_offer",
    "delete_product_rows",
    "get_product",
    "list_categories",
    "list_offers",
    "list_products",
    "set_product_status",
    "update_category",
    "update_offer",
    "update_product",
    "with_fee_estimate",
]
