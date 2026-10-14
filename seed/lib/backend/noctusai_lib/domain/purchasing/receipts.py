"""Receipts (partial receipts allowed) and their two idempotent posting legs.

`receive` = ONE RPC (`pur_receive`: lock the order, validate against the open balance, write the receipt + lines + the
order's new status, with the landed cost already prorated -- see `sql.py`) followed by `post_receipt`:

  1. STOCK  -- one inventory `receive_stock` per receipt line at the line's `landed_unit_cost_cents`,
               `source='purchasing'`, `source_ref=<receipt line id>`  (the kardex's own unique key makes a retry a replay);
  2. FINANCE -- the AP entries (`FinanceBooking.book_payable`), `source='purchasing'`,
               `source_ref=<receipt id>` (one installment) or `<receipt id>:<k>` (k-th of n).

The two legs are not one transaction (different organs, PostgREST), so each is idempotent and marked on the receipt
(`stock_posted_at` / `finance_posted_at`). A domain failure in a leg is recorded as `posting_error` on the receipt and
returned with it (the receipt itself is committed and the order status is right); `post_receipt` re-runs ONLY the legs
not yet marked -- the retry endpoint and the next `receive` replay both land there. Anything unexpected propagates.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Mapping, Optional

from noctusai_lib.domain.finance.entries import split_installments
from noctusai_lib.domain.inventory.port import StockPort
from noctusai_lib.domain.finance.booking import FinanceBooking
from noctusai_lib.primitives.exceptions import AppException

from . import orders as orders_svc
from ._common import Scope, now_iso, qty_str
from .types import SOURCE

logger = logging.getLogger(__name__)


def _lines(s: Scope, receipt_id: Any) -> list[dict]:
    rows = s.rows("receipt_lines", eq={"receipt_id": str(receipt_id)})
    rows.sort(key=lambda r: str(r["id"]))
    return rows


def present_receipt(s: Scope, receipt: Mapping[str, Any]) -> dict:
    out = {**receipt, "lines": _lines(s, receipt["id"])}
    out["posted"] = bool(receipt.get("stock_posted_at") and receipt.get("finance_posted_at"))
    return out


def list_for_order(s: Scope, order_id: Any) -> list[dict]:
    rows = s.rows("receipts", eq={"order_id": str(order_id)})
    rows.sort(key=lambda r: (int(r.get("receipt_no") or 0), str(r["id"])))
    return [present_receipt(s, r) for r in rows]


def get_receipt(s: Scope, receipt_id: Any) -> dict:
    return present_receipt(s, s.get("receipts", receipt_id, what="Recebimento"))


def list_receipts(
    s: Scope, *, order_id: Optional[str] = None, pending_only: bool = False, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int, int, int]:
    """Every receipt of the org, newest first (headers only; `pending_only` = a posting leg is still open)."""

    def refine(query):
        if order_id:
            query = query.eq("order_id", str(order_id))
        if pending_only:
            query = query.or_("stock_posted_at.is.null,finance_posted_at.is.null")
        return query

    return s.page("receipts", page=page, page_size=page_size, refine=refine, order=(("created_at", True), ("id", False)))


def receive(
    s: Scope, order_id: Any, data: Mapping[str, Any], *, user_id: Optional[str], stock: StockPort, booking: FinanceBooking
) -> dict:
    """Receive (part of) an order: write the receipt, then post stock + AP. Returns the receipt with its posting state."""
    row = {
        "received_on": data["received_on"].isoformat() if data.get("received_on") else None,
        "note": data.get("note"),
        "idempotency_key": data.get("idempotency_key"),
        "created_by": user_id,
        "lines": [{"order_line_id": str(line["order_line_id"]), "qty": qty_str(line["qty"])} for line in data["lines"]],
    }
    verdict = orders_svc._rpc(s, "receive", {"p_org": s.org_id, "p_order_id": str(order_id), "p_row": row})
    result = post_receipt(s, verdict["receipt_id"], user_id=user_id, stock=stock, booking=booking)
    return {**result, "replayed": verdict["status"] == "replayed", "order_status": verdict.get("order_status")}


def _due_dates(base: date, first_days: int, interval: int, n: int) -> list[date]:
    return [base + timedelta(days=first_days + k * interval) for k in range(n)]


def _post_stock(s: Scope, receipt: dict, order: dict, stock: StockPort, user_id: Optional[str]) -> None:
    if s.cfg.with_inventory:
        order_lines = {str(l["id"]): l for l in orders_svc.list_lines(s, order["id"])}
        for rl in _lines(s, receipt["id"]):
            ol = order_lines[str(rl["order_line_id"])]
            stock.receive_stock(
                s.org_id,
                item_id=str(ol["item_id"]),
                warehouse_id=str(order["warehouse_id"]),
                qty=rl["qty"],
                unit_cost_cents=int(rl["landed_unit_cost_cents"]),
                source=SOURCE,
                source_ref=str(rl["id"]),
                user_id=user_id,
                note=f"Pedido #{order['number']} - recebimento {receipt['receipt_no']}",
            )
    s.tbl("receipts").update({"stock_posted_at": now_iso(), "posting_error": None}).eq("org_id", s.org_id).eq("id", str(receipt["id"])).execute()


def _post_finance(s: Scope, receipt: dict, order: dict, booking: FinanceBooking) -> None:
    total = int(receipt["total_cents"])
    if total > 0:
        party = orders_svc.get_party(s, order.get("party_id"))
        n = max(1, min(int(order["installments_count"]), total))
        amounts = split_installments(total, n)
        dues = _due_dates(date.fromisoformat(str(receipt["received_on"])[:10]), int(order["first_due_days"]), int(order["interval_days"]), n)
        for k, (amount, due) in enumerate(zip(amounts, dues), start=1):
            booking.book_payable(
                s.org_id,
                source=SOURCE,
                source_ref=str(receipt["id"]) if n == 1 else f"{receipt['id']}:{k}",
                description=f"Compra #{order['number']} - recebimento {receipt['receipt_no']}" + (f" ({k}/{n})" if n > 1 else ""),
                counterparty_name=order["supplier_name"],
                counterparty_doc=(party or {}).get("doc"),
                amount_cents=amount,
                competence_month=date.fromisoformat(str(receipt["received_on"])[:10]),
                due_date=due,
                category_hint=s.cfg.default_category_hint,
                party_id=str(order["party_id"]) if order.get("party_id") else None,
                notes=receipt.get("note"),
            )
    s.tbl("receipts").update({"finance_posted_at": now_iso(), "posting_error": None}).eq("org_id", s.org_id).eq("id", str(receipt["id"])).execute()


def post_receipt(s: Scope, receipt_id: Any, *, user_id: Optional[str], stock: StockPort, booking: FinanceBooking) -> dict:
    """Run the posting legs not yet marked on the receipt. Idempotent; a domain failure is recorded, not hidden."""
    receipt = s.get("receipts", receipt_id, what="Recebimento")
    order = s.get("orders", receipt["order_id"], what="Pedido de compra")
    error: Optional[str] = None
    try:
        if not receipt.get("stock_posted_at"):
            _post_stock(s, receipt, order, stock, user_id)
        if not receipt.get("finance_posted_at"):
            _post_finance(s, receipt, order, booking)
    except AppException as exc:
        error = f"{exc.code}: {exc.message}"
        logger.warning("purchasing receipt %s posting incomplete: %s", receipt_id, error)
        s.tbl("receipts").update({"posting_error": error}).eq("org_id", s.org_id).eq("id", str(receipt_id)).execute()
    return {**get_receipt(s, receipt_id), "posting_error": error or None}


__all__ = ["get_receipt", "list_for_order", "list_receipts", "post_receipt", "present_receipt", "receive"]
