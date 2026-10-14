"""Stock mutations: thin, org-scoped callers of the row-locked RPCs, plus the refusal -> HTTP mapping.

The RPCs are the authority (lock + kardex + balance in one transaction). Python only validates
shape and resolves ids to this org; it never reads-then-writes a balance.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Sequence

from ._common import Scope, dec, qty_str
from .errors import QUANTIDADE_INVALIDA, TRANSFERENCIA_MESMO_DEPOSITO, from_refusal, invalid

logger = logging.getLogger(__name__)

SOURCE_MANUAL = "manual"
SOURCE_ORDER = "order"


def _rpc(s: Scope, name: str, params: dict) -> dict:
    """Call an inventory RPC and unwrap its jsonb verdict; a refusal raises, an unknown shape is loud."""
    resp = s.db.rpc(s.cfg.rpc(name), params).execute()
    payload = getattr(resp, "data", None)
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict) or "status" not in payload:
        raise RuntimeError(f"inventory RPC {name} answered an unexpected payload: {payload!r}")
    if payload["status"] == "refused":
        raise from_refusal(payload)
    return payload


def _positive(value: Any, field: str = "qty") -> str:
    q = dec(value)
    if q <= 0:
        raise invalid(field, "A quantidade deve ser maior que zero.", code=QUANTIDADE_INVALIDA)
    return qty_str(q)


def _row(s: Scope, data: Mapping[str, Any], **extra: Any) -> dict:
    row = {k: v for k, v in data.items() if v is not None}
    for key in ("item_id", "warehouse_id", "from_warehouse_id", "to_warehouse_id", "created_by"):
        if key in row:
            row[key] = str(row[key])
    row.update({k: v for k, v in extra.items() if v is not None})
    return row


def receive(s: Scope, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Stock in (purchase receipt, return, opening balance) at `unit_cost_cents`; recomputes the moving average."""
    row = _row(s, data, qty=_positive(data.get("qty")), created_by=user_id)
    row.setdefault("source", SOURCE_MANUAL)
    return _rpc(s, "receive", {"p_org": s.org_id, "p_row": row})


def issue(s: Scope, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Stock out at the CURRENT average cost; refuses past `on_hand - reserved`."""
    row = _row(s, data, qty=_positive(data.get("qty")), created_by=user_id)
    row.pop("unit_cost_cents", None)
    row.setdefault("source", SOURCE_MANUAL)
    return _rpc(s, "issue", {"p_org": s.org_id, "p_row": row})


def adjust(s: Scope, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Inventory count: set `on_hand` to `counted_qty`; the signed delta is booked as one `adjust` move."""
    counted = dec(data.get("counted_qty"))
    if data.get("counted_qty") is None or counted < 0:
        raise invalid("counted_qty", "A quantidade contada não pode ser negativa.", code=QUANTIDADE_INVALIDA)
    row = _row(s, data, counted_qty=qty_str(counted), created_by=user_id)
    row.setdefault("source", SOURCE_MANUAL)
    return _rpc(s, "adjust", {"p_org": s.org_id, "p_row": row})


def transfer(s: Scope, data: Mapping[str, Any], *, user_id: Optional[str] = None) -> dict:
    """Move stock between two warehouses at the origin's average cost (two kardex rows, one `transfer_group`)."""
    if str(data.get("from_warehouse_id")) == str(data.get("to_warehouse_id")):
        raise invalid("to_warehouse_id", "Origem e destino são o mesmo depósito.", code=TRANSFERENCIA_MESMO_DEPOSITO)
    row = _row(s, data, qty=_positive(data.get("qty")), created_by=user_id)
    row.setdefault("source", SOURCE_MANUAL)
    return _rpc(s, "transfer", {"p_org": s.org_id, "p_row": row})


def _lines(lines: Sequence[Mapping[str, Any]], *, need_qty: bool) -> list[dict]:
    out = []
    for line in lines:
        item = {"item_id": str(line["item_id"])}
        if line.get("warehouse_id"):
            item["warehouse_id"] = str(line["warehouse_id"])
        if need_qty or line.get("qty") is not None:
            item["qty"] = _positive(line.get("qty"))
        out.append(item)
    return out


def reserve(s: Scope, order_ref: str, lines: Sequence[Mapping[str, Any]], *, user_id: Optional[str] = None, source: str = SOURCE_ORDER) -> dict:
    """Reserve every line or none (one transaction); idempotent on `(source, order_ref, item, warehouse)`."""
    if not lines:
        raise invalid("lines", "Informe ao menos uma linha.", code=QUANTIDADE_INVALIDA)
    return _rpc(s, "reserve", {"p_org": s.org_id, "p_order_ref": order_ref, "p_lines": _lines(lines, need_qty=True), "p_user": user_id, "p_source": source})


def commit(s: Scope, order_ref: str, lines: Optional[Sequence[Mapping[str, Any]]] = None, *, user_id: Optional[str] = None, source: str = SOURCE_ORDER) -> dict:
    """Convert the order's reservation into a stock-out at the average cost; `lines=None` = the whole order."""
    return _rpc(s, "commit", {"p_org": s.org_id, "p_order_ref": order_ref, "p_lines": _lines(lines or [], need_qty=False), "p_user": user_id, "p_source": source})


def release(s: Scope, order_ref: str, lines: Optional[Sequence[Mapping[str, Any]]] = None, *, user_id: Optional[str] = None, source: str = SOURCE_ORDER) -> dict:
    """Free the order's reservation (expired / revoked). Nothing reserved is a no-op, not an error."""
    return _rpc(s, "release", {"p_org": s.org_id, "p_order_ref": order_ref, "p_lines": _lines(lines or [], need_qty=False), "p_user": user_id, "p_source": source})


__all__ = ["SOURCE_MANUAL", "SOURCE_ORDER", "adjust", "commit", "issue", "receive", "release", "reserve", "transfer"]
