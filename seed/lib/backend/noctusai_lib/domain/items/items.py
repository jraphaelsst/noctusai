"""Item services: create / read / update / archive / search.

`normalize_item(...)` is the ONE validation path (HTTP bodies and CSV rows both go through it): it
returns the canonical column dict or raises `ItemsError`. Items are never hard-deleted -- other organs
(inventory, purchasing, commerce) will reference them -- they are ARCHIVED (`is_active=false`).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from noctusai_lib.integrations.persistence.table_reads import IN_FILTER_BATCH
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, first, like_term, new_id, now_iso
from .categories import descendant_ids
from .errors import CAMPO_OBRIGATORIO, SKU_DUPLICADO, conflict, invalid, not_found
from .types import Unit, values
from .validators import (
    normalize_cest,
    normalize_cfop,
    normalize_gtin,
    normalize_ncm,
    normalize_origem,
    normalize_sku,
)

#: Columns a caller may write (everything else -- id, org_id, timestamps -- is the service's).
WRITABLE = (
    "sku", "name", "description", "item_type", "unit", "category_id", "ncm", "cest", "cfop_default", "origem",
    "gtin", "cost_cents", "price_cents", "weight_g", "length_mm", "width_mm", "height_mm", "is_active",
)
_NOT_NULL = ("sku", "name", "item_type", "unit", "cost_cents", "is_active")
_NON_NEGATIVE_INTS = ("cost_cents", "price_cents", "weight_g", "length_mm", "width_mm", "height_mm")
_DUP_MSG = "Já existe um item com este SKU."


def _plain(value: Any) -> Any:
    return getattr(value, "value", value)


def _non_negative_int(field: str, value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise invalid(field, "Informe um número inteiro.")
    if value < 0:
        raise invalid(field, "O valor não pode ser negativo.")
    return value


def normalize_item(s: Scope, data: Mapping[str, Any], *, partial: bool) -> dict[str, Any]:
    """Validate + canonicalise the caller's fields. `partial=True` only touches the keys present."""
    out: dict[str, Any] = {}
    for key in data:
        if key not in WRITABLE:
            raise invalid(key, "Campo desconhecido.")
    present = {k: data[k] for k in WRITABLE if k in data}
    if not partial:
        present.setdefault("item_type", "goods")
        present.setdefault("unit", "UN")
        present.setdefault("cost_cents", 0)
        present.setdefault("is_active", True)
    for key in _NOT_NULL:
        if key in present and present[key] is None:
            raise invalid(key, "Campo obrigatório.", CAMPO_OBRIGATORIO)
    if not partial and not present.get("sku"):
        raise invalid("sku", "Informe o SKU.", CAMPO_OBRIGATORIO)
    if not partial and not str(present.get("name") or "").strip():
        raise invalid("name", "Informe o nome do item.", CAMPO_OBRIGATORIO)

    if "sku" in present:
        out["sku"] = normalize_sku(present["sku"])
    if "name" in present:
        name = str(present["name"]).strip()
        if not name:
            raise invalid("name", "Informe o nome do item.", CAMPO_OBRIGATORIO)
        out["name"] = name
    if "description" in present:
        text = None if present["description"] is None else str(present["description"]).strip()
        out["description"] = text or None
    if "item_type" in present:
        item_type = str(_plain(present["item_type"]))
        if item_type not in s.cfg.item_types:
            raise invalid("item_type", f"Tipo de item inválido. Use: {', '.join(s.cfg.item_types)}.")
        out["item_type"] = item_type
    if "unit" in present:
        unit = str(_plain(present["unit"])).strip().upper()
        if unit not in values(Unit):
            raise invalid("unit", f"Unidade inválida. Use: {', '.join(values(Unit))}.")
        out["unit"] = unit
    if "category_id" in present:
        cid = present["category_id"]
        if cid:
            s.require_owned("item_categories", cid, what="Categoria", field="category_id")
            out["category_id"] = str(cid)
        else:
            out["category_id"] = None
    if "ncm" in present:
        out["ncm"] = normalize_ncm(present["ncm"])
    if "cest" in present:
        out["cest"] = normalize_cest(present["cest"])
    if "cfop_default" in present:
        out["cfop_default"] = normalize_cfop(present["cfop_default"])
    if "origem" in present:
        out["origem"] = normalize_origem(present["origem"])
    if "gtin" in present:
        out["gtin"] = normalize_gtin(present["gtin"])
    for key in _NON_NEGATIVE_INTS:
        if key in present:
            out[key] = _non_negative_int(key, present[key])
    if "is_active" in present:
        out["is_active"] = bool(present["is_active"])
    return out


def sku_taken(s: Scope, sku: str, *, except_id: Any = None) -> bool:
    """SKUs are stored upper-cased (`normalize_sku`), so an exact match IS the case-insensitive match."""
    resp = s.tbl("items").select("id").eq("org_id", s.org_id).eq("sku", sku.upper()).execute()
    return any(except_id is None or str(r["id"]) != str(except_id) for r in (resp.data or []))


def build_row(fields: Mapping[str, Any], org_id: str) -> dict:
    """A full insert row from normalized fields (nullable columns default to None)."""
    now = now_iso()
    row: dict[str, Any] = {col: None for col in WRITABLE}
    row.update(fields)
    row.update({"id": new_id(), "org_id": org_id, "created_at": now, "updated_at": now})
    return row


def get_item(s: Scope, item_id: Any) -> dict:
    return s.get("items", item_id, what="Item")


def create_item(s: Scope, data: Mapping[str, Any]) -> dict:
    fields = normalize_item(s, data, partial=False)
    if sku_taken(s, fields["sku"]):
        raise conflict(SKU_DUPLICADO, _DUP_MSG)
    row = build_row(fields, s.org_id)
    try:
        return first(s.tbl("items").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):  # lost a race with a concurrent create of the same SKU
            raise conflict(SKU_DUPLICADO, _DUP_MSG) from exc
        raise


def update_item(s: Scope, item_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_item(s, item_id)
    patch = normalize_item(s, data, partial=True)
    if not patch:
        return current
    if "sku" in patch and sku_taken(s, patch["sku"], except_id=item_id):
        raise conflict(SKU_DUPLICADO, _DUP_MSG)
    patch["updated_at"] = now_iso()
    try:
        s.tbl("items").update(patch).eq("org_id", s.org_id).eq("id", str(item_id)).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            raise conflict(SKU_DUPLICADO, _DUP_MSG) from exc
        raise
    return {**current, **patch}


def set_active(s: Scope, item_id: Any, active: bool) -> dict:
    """Archive (`active=False`) or restore an item. Idempotent."""
    current = get_item(s, item_id)
    if bool(current.get("is_active", True)) == active:
        return current
    patch = {"is_active": active, "updated_at": now_iso()}
    s.tbl("items").update(patch).eq("org_id", s.org_id).eq("id", str(item_id)).execute()
    return {**current, **patch}


def list_items(
    s: Scope,
    *,
    q: Optional[str] = None,
    item_type: Optional[str] = None,
    category_id: Optional[Any] = None,
    active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int, int, int]:
    if item_type is not None and item_type not in s.cfg.item_types:
        raise invalid("item_type", "Tipo de item inválido.")
    category_ids = None
    if category_id:
        s.get("item_categories", category_id, what="Categoria")
        category_ids = descendant_ids(s, category_id)
        if len(category_ids) > IN_FILTER_BATCH:
            raise invalid("category_id", "A categoria tem subcategorias demais para filtrar de uma vez.", "categoria_ampla_demais")
    term = like_term(q) if q and q.strip() else None

    def refine(query):
        if item_type:
            query = query.eq("item_type", item_type)
        if active is not None:
            query = query.eq("is_active", active)
        if category_ids:
            # postgrest-unbounded-ok: a category subtree, capped at IN_FILTER_BATCH just above (422 beyond it)
            query = query.in_("category_id", category_ids)
        if term:
            query = query.or_(f'sku.ilike."{term}",name.ilike."{term}",gtin.ilike."{term}"')
        return query

    return s.page("items", page=page, page_size=page_size, refine=refine, order=(("name", False), ("id", False)))


__all__ = [
    "WRITABLE",
    "build_row",
    "create_item",
    "get_item",
    "list_items",
    "normalize_item",
    "set_active",
    "sku_taken",
    "update_item",
]
