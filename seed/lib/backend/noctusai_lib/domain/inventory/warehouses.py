"""Warehouses (depósitos). Never deleted: deactivated, and only when empty.

The default warehouse is where an order line without an explicit warehouse reserves from. The first
warehouse an org creates becomes its default; `is_default` is unique per org (partial index).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Mapping, Optional

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, dec, first, new_id, now_iso
from .errors import DEPOSITO_COM_ESTOQUE, DEPOSITO_DUPLICADO, conflict, invalid

logger = logging.getLogger(__name__)

_FIELDS = ("name", "code", "address", "active")


def _clean(data: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in data.items() if k in _FIELDS}
    if "code" in out and out["code"] is not None:
        out["code"] = str(out["code"]).strip()
    if "name" in out and out["name"] is not None:
        out["name"] = str(out["name"]).strip()
    return out


def list_warehouses(s: Scope, *, active: Optional[bool] = None) -> list[dict]:
    rows = s.rows("warehouses", eq={"active": active} if active is not None else None)
    rows.sort(key=lambda r: (not r.get("is_default"), str(r.get("name", "")).lower(), str(r["id"])))
    return rows


def get_warehouse(s: Scope, warehouse_id: Any) -> dict:
    return s.get("warehouses", warehouse_id, what="Depósito")


def default_warehouse(s: Scope) -> Optional[dict]:
    rows = s.rows("warehouses", eq={"is_default": True})
    return rows[0] if rows else None


def require_usable_warehouse(s: Scope, warehouse_id: Any, *, field: str) -> dict:
    """A warehouse of THIS org that is active (422 on the field, not 404)."""
    row = s.find("warehouses", warehouse_id)
    if row is None:
        raise invalid(field, "Depósito não encontrado.", code="deposito_invalido")
    if not row.get("active", True):
        raise invalid(field, "O depósito está inativo.", code="deposito_inativo")
    return row


def _clear_default(s: Scope) -> None:
    s.tbl("warehouses").update({"is_default": False, "updated_at": now_iso()}).eq("org_id", s.org_id).eq("is_default", True).execute()


def create_warehouse(s: Scope, data: Mapping[str, Any], *, make_default: bool = False) -> dict:
    row = _clean(data)
    if not row.get("name") or not row.get("code"):
        raise invalid("name", "Informe nome e código do depósito.")
    row.setdefault("address", {})
    row.setdefault("active", True)
    first_one = default_warehouse(s) is None
    want_default = bool(make_default or first_one) and row["active"]
    if want_default and not first_one:
        _clear_default(s)
    now = now_iso()
    row.update({"id": new_id(), "org_id": s.org_id, "is_default": want_default, "created_at": now, "updated_at": now})
    try:
        saved = first(s.tbl("warehouses").insert(row).execute())
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if is_unique_violation(exc):
            raise conflict(DEPOSITO_DUPLICADO, "Já existe um depósito com este código.") from exc
        raise
    return saved or row


def _on_hand_in(s: Scope, warehouse_id: Any) -> Decimal:
    return sum((dec(r.get("on_hand")) for r in s.rows("stock_balances", eq={"warehouse_id": str(warehouse_id)}, order_col="item_id")), Decimal(0))


def update_warehouse(s: Scope, warehouse_id: Any, patch: Mapping[str, Any], *, make_default: Optional[bool] = None) -> dict:
    current = get_warehouse(s, warehouse_id)
    changes = _clean(patch)
    if changes.get("active") is False:
        if _on_hand_in(s, warehouse_id) > 0:
            raise conflict(DEPOSITO_COM_ESTOQUE, "O depósito ainda tem estoque: transfira antes de desativar.")
        if current.get("is_default"):
            raise invalid("active", "Defina outro depósito padrão antes de desativar este.", code="deposito_padrao")
    if make_default:
        if not changes.get("active", current.get("active", True)):
            raise invalid("is_default", "Um depósito inativo não pode ser o padrão.", code="deposito_inativo")
        _clear_default(s)
        changes["is_default"] = True
    elif make_default is False and current.get("is_default"):
        raise invalid("is_default", "Escolha outro depósito como padrão em vez de remover o atual.", code="deposito_padrao")
    if not changes:
        return current
    changes["updated_at"] = now_iso()
    try:
        s.tbl("warehouses").update(changes).eq("org_id", s.org_id).eq("id", str(warehouse_id)).execute()
    except Exception as exc:  # noqa: BLE001 - narrowed below
        if is_unique_violation(exc):
            raise conflict(DEPOSITO_DUPLICADO, "Já existe um depósito com este código.") from exc
        raise
    return get_warehouse(s, warehouse_id)


__all__ = ["create_warehouse", "default_warehouse", "get_warehouse", "list_warehouses", "require_usable_warehouse", "update_warehouse"]
