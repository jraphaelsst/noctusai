"""Read models: balances, kardex (running balance + cost), valuation (moving average), low stock, thresholds."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from ._common import Scope, dec, first, now_iso
from .errors import invalid
from .warehouses import get_warehouse


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def present_balance(row: dict, min_qty: Optional[Any] = None) -> dict:
    on_hand, reserved = dec(row.get("on_hand")), dec(row.get("reserved"))
    out = dict(row)
    out["available"] = float(on_hand - reserved)
    out["value_cents"] = _cents(on_hand * dec(row.get("avg_cost_cents")))
    threshold = dec(min_qty) if min_qty is not None else None
    out["min_qty"] = float(threshold) if threshold is not None else None
    out["low_stock"] = bool(threshold is not None and threshold > 0 and (on_hand - reserved) <= threshold)
    return out


def _settings_map(s: Scope) -> dict[tuple[str, str], Any]:
    return {(str(r["item_id"]), str(r["warehouse_id"])): r["min_qty"] for r in s.rows("item_settings", order_col="item_id")}


def list_balances(
    s: Scope,
    *,
    item_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    include_zero: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int, int, int]:
    def refine(q: Any) -> Any:
        if item_id:
            q = q.eq("item_id", str(item_id))
        if warehouse_id:
            q = q.eq("warehouse_id", str(warehouse_id))
        if not include_zero:
            q = q.or_("on_hand.gt.0,reserved.gt.0")
        return q

    rows, total, page, size = s.page("stock_balances", page=page, page_size=page_size, refine=refine,
                                     order=(("item_id", False), ("warehouse_id", False)))
    settings = _settings_map(s)
    return [present_balance(r, settings.get((str(r["item_id"]), str(r["warehouse_id"])))) for r in rows], total, page, size


def kardex(
    s: Scope,
    item_id: str,
    *,
    warehouse_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int, int, int]:
    """The item's moves oldest-first. `on_hand_after` / `reserved_after` / `avg_cost_after_cents` ARE the running
    balance and cost (stamped by the RPC in the same transaction), so a page needs no replay of earlier pages."""

    def refine(q: Any) -> Any:
        q = q.eq("item_id", str(item_id))
        if warehouse_id:
            q = q.eq("warehouse_id", str(warehouse_id))
        if date_from:
            q = q.gte("occurred_at", date_from.isoformat())
        if date_to:
            q = q.lt("occurred_at", f"{date_to.isoformat()}T23:59:59.999999+00:00")
        return q

    return s.page("stock_moves", page=page, page_size=page_size, refine=refine, order=(("seq", False),))


def valuation(s: Scope, *, warehouse_id: Optional[str] = None) -> dict:
    """Σ on_hand × avg_cost (moving average), per warehouse and overall, in integer cents."""
    rows = s.rows("stock_balances", eq={"warehouse_id": str(warehouse_id)} if warehouse_id else None, order_col="item_id")
    by_wh: dict[str, dict] = {}
    for r in rows:
        bucket = by_wh.setdefault(str(r["warehouse_id"]), {"warehouse_id": str(r["warehouse_id"]), "value": Decimal(0), "items": 0, "units": Decimal(0)})
        on_hand = dec(r.get("on_hand"))
        if on_hand <= 0:
            continue
        bucket["value"] += on_hand * dec(r.get("avg_cost_cents"))
        bucket["items"] += 1
        bucket["units"] += on_hand
    groups = [
        {"warehouse_id": b["warehouse_id"], "value_cents": _cents(b["value"]), "items": b["items"], "units": float(b["units"])}
        for b in sorted(by_wh.values(), key=lambda b: b["warehouse_id"])
    ]
    return {
        "method": "average_cost",
        "total_cents": sum(g["value_cents"] for g in groups),
        "items": sum(g["items"] for g in groups),
        "by_warehouse": groups,
    }


def low_stock(s: Scope) -> list[dict]:
    """Every (item, warehouse) with a positive `min_qty` whose available stock is at or below it (no balance = 0)."""
    balances = {(str(r["item_id"]), str(r["warehouse_id"])): r for r in s.rows("stock_balances", order_col="item_id")}
    out = []
    for st in s.rows("item_settings", order_col="item_id"):
        threshold = dec(st["min_qty"])
        if threshold <= 0:
            continue
        key = (str(st["item_id"]), str(st["warehouse_id"]))
        bal = balances.get(key) or {"org_id": s.org_id, "item_id": key[0], "warehouse_id": key[1], "on_hand": 0, "reserved": 0, "avg_cost_cents": 0}
        view = present_balance(bal, threshold)
        if view["low_stock"]:
            out.append(view)
    out.sort(key=lambda v: (v["available"] - v["min_qty"], v["item_id"], v["warehouse_id"]))
    return out


def set_min_qty(s: Scope, item_id: str, warehouse_id: str, min_qty: Any) -> dict:
    qty = dec(min_qty)
    if qty < 0:
        raise invalid("min_qty", "O estoque mínimo não pode ser negativo.")
    get_warehouse(s, warehouse_id)
    existing = first(
        s.tbl("item_settings").select("*").eq("org_id", s.org_id).eq("item_id", str(item_id)).eq("warehouse_id", str(warehouse_id)).limit(1).execute()
    )
    row = {"min_qty": format(qty, "f"), "updated_at": now_iso()}
    if existing:
        s.tbl("item_settings").update(row).eq("org_id", s.org_id).eq("item_id", str(item_id)).eq("warehouse_id", str(warehouse_id)).execute()
    else:
        s.tbl("item_settings").insert({**row, "org_id": s.org_id, "item_id": str(item_id), "warehouse_id": str(warehouse_id)}).execute()
    return {"item_id": str(item_id), "warehouse_id": str(warehouse_id), "min_qty": float(qty)}


__all__ = ["kardex", "list_balances", "low_stock", "present_balance", "set_min_qty", "valuation"]
