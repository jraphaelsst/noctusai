"""Financial service -- the Orbity layer over the seed finance organ: cash flow + the charges list.

Receivables live in ``fin_entries`` (seed finance organ); the client a receivable belongs to and its gateway state live in
``billing_charges`` (this product's sidecar). Everything is read through the SERVICE-ROLE client with ``org_id`` filtered
on every query (the admin client does not carry RLS).

Cash-flow rule (upstream ``shouldIncludeOpenPayment``, the one that makes "inactivate a client but keep a charge" mean
something): ``paid`` always counts (immutable history), ``cancelled`` never, an OPEN charge counts when it was explicitly
KEPT after the client's inactivation or the client was still active in that month. A receivable with no client attached
(typed straight into the finance page) has nobody to be inactive and always counts.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from app.services.billing_charges import CHARGES, CLIENTS, ENTRIES

logger = logging.getLogger(__name__)

_OPEN = ("open", "partial")
_CHUNK = 100


# ── the rule (pure) ─────────────────────────────────────────────────────────────────────────────────────────


def month_bounds(reference_month: str) -> tuple[date, date]:
    """``YYYY-MM-DD`` (or ``YYYY-MM``) -> (first day, first day of the next month). ValueError when not a month."""
    text = str(reference_month).strip()
    try:
        first = date.fromisoformat(text[:7] + "-01")
    except ValueError as exc:
        raise ValueError(f"Invalid reference_month: {reference_month!r}") from exc
    nxt = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)
    return first, nxt


def _as_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def was_client_active_in_month(client: dict, month_first: date) -> bool:
    """Active now => yes. Inactive => only when the inactivation came AFTER the month ended."""
    if client.get("active"):
        return True
    inactivated = _as_datetime(client.get("inactivated_at"))
    if inactivated is None:
        return False
    _, nxt = month_bounds(month_first.isoformat())
    return inactivated.replace(tzinfo=None) >= datetime(nxt.year, nxt.month, nxt.day)


def should_include_open_payment(status: str, preserved: bool, client: Optional[dict], month_first: date) -> bool:
    if status == "paid":
        return True
    if status == "cancelled":
        return False
    if preserved:
        return True
    if client is None:
        return True
    return was_client_active_in_month(client, month_first)


def _cents_to_reais(cents: int) -> float:
    return round(cents / 100, 2)


def _chunks(items: list[str]):
    for i in range(0, len(items), _CHUNK):
        yield items[i:i + _CHUNK]


class FinancialService:
    def __init__(self, db: Any, org_id: UUID | str) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        return self._db.table(table)

    def _by_ids(self, table: str, ids: list[str], columns: str = "*") -> dict[str, dict]:
        out: dict[str, dict] = {}
        for chunk in _chunks(sorted(set(ids))):
            rows = self._t(table).select(columns).eq("org_id", self._org_id).in_("id", chunk).execute().data or []
            out.update({str(r["id"]): r for r in rows})
        return out

    # ── cash flow ────────────────────────────────────────────────────────────────────────────────────────

    def monthly_cash_flow(self, reference_month: str) -> dict[str, Any]:
        first, nxt = month_bounds(reference_month)
        def page(start: int, end: int):
            return (
                self._t(ENTRIES).select("id,direction,status,amount_cents,settled_cents,due_date,competence_month")
                .eq("org_id", self._org_id).eq("competence_month", first.isoformat()).order("id").range(start, end).execute().data
            )

        entries = list(iter_paged_rows(page, label="financial cash flow entries"))  # PostgREST silently caps a bare select at 1000
        receivables = [e for e in entries if e["direction"] == "receivable"]
        payables = [e for e in entries if e["direction"] == "payable"]

        charges: dict[str, dict] = {}
        for chunk in _chunks([str(e["id"]) for e in receivables]):
            rows = self._t(CHARGES).select("entry_id,client_id,preserved_after_deactivation").eq("org_id", self._org_id).in_("entry_id", chunk).execute().data or []
            charges.update({str(r["entry_id"]): r for r in rows})
        clients = self._by_ids(CLIENTS, [str(c["client_id"]) for c in charges.values() if c.get("client_id")], "id,active,inactivated_at")

        today = date.today()
        paid = pending = overdue = 0
        for e in receivables:
            charge = charges.get(str(e["id"]), {})
            client = clients.get(str(charge["client_id"])) if charge.get("client_id") else None
            if not should_include_open_payment(e["status"], bool(charge.get("preserved_after_deactivation")), client, first):
                continue
            if e["status"] == "paid":
                paid += int(e["amount_cents"])
            elif e["status"] in _OPEN:
                open_cents = int(e["amount_cents"]) - int(e.get("settled_cents") or 0)
                if date.fromisoformat(str(e["due_date"])[:10]) < today:
                    overdue += open_cents
                else:
                    pending += open_cents
        paid_expenses = sum(int(p["amount_cents"]) for p in payables if p["status"] == "paid")
        return {
            "reference_month": first.isoformat(),
            "paid_revenues": _cents_to_reais(paid),
            "paid_expenses": _cents_to_reais(paid_expenses),
            "net": _cents_to_reais(paid - paid_expenses),
            "pending_revenues": _cents_to_reais(pending),
            "overdue_revenues": _cents_to_reais(overdue),
        }

    # ── charges ──────────────────────────────────────────────────────────────────────────────────────────

    def present_charges(self, charges: list[dict]) -> list[dict]:
        """Join the sidecar rows with their entry + client name into the wire shape."""
        entries = self._by_ids(ENTRIES, [str(c["entry_id"]) for c in charges])
        clients = self._by_ids(CLIENTS, [str(c["client_id"]) for c in charges if c.get("client_id")], "id,name,legal_name")
        today = date.today()
        out = []
        for c in charges:
            e = entries.get(str(c["entry_id"]))
            if e is None:
                continue
            client = clients.get(str(c["client_id"])) if c.get("client_id") else None
            due = str(e["due_date"])[:10]
            out.append({
                "entry_id": str(c["entry_id"]), "client_id": str(c["client_id"]) if c.get("client_id") else None,
                "client_name": (client or {}).get("legal_name") or (client or {}).get("name"),
                "contract_id": str(c["contract_id"]) if c.get("contract_id") else None,
                "description": e["description"], "due_date": due, "amount_cents": int(e["amount_cents"]),
                "settled_cents": int(e.get("settled_cents") or 0), "entry_status": e["status"],
                "overdue": e["status"] in _OPEN and date.fromisoformat(due) < today,
                "generation_status": c["generation_status"], "generation_attempts": int(c.get("generation_attempts") or 0),
                "last_error": c.get("last_error"), "next_attempt_at": c.get("next_attempt_at"), "gateway": c.get("gateway"),
                "billing_method": c.get("billing_method"), "external_id": c.get("external_id"), "invoice_url": c.get("invoice_url"),
                "pix_payload": c.get("pix_payload"), "preserved_after_deactivation": bool(c.get("preserved_after_deactivation")),
                "gateway_cancel_status": c.get("gateway_cancel_status"), "gateway_cancel_error": c.get("gateway_cancel_error"),
            })
        return out

    def list_charges(self, *, client_id: Optional[str] = None, generation_status: Optional[str] = None,
                     page: int = 1, page_size: int = 50) -> dict[str, Any]:
        offset = (page - 1) * page_size
        q = self._t(CHARGES).select("*", count="exact").eq("org_id", self._org_id).order("created_at", desc=True)
        if client_id:
            q = q.eq("client_id", client_id)
        if generation_status:
            q = q.eq("generation_status", generation_status)
        res = q.range(offset, offset + page_size - 1).execute()
        rows = res.data or []
        return {"items": self.present_charges(rows), "total": res.count if res.count is not None else len(rows),
                "page": page, "page_size": page_size}

    def open_charges_of_client(self, client_id: str) -> list[dict]:
        """The client's receivables still open (pending + overdue, possibly partially paid), oldest first."""
        def page(start: int, end: int):
            return (self._t(CHARGES).select("*").eq("org_id", self._org_id).eq("client_id", client_id)
                    .order("id").range(start, end).execute().data)

        charges = list(iter_paged_rows(page, label="client charges"))
        presented = [c for c in self.present_charges(charges) if c["entry_status"] in _OPEN]
        presented.sort(key=lambda c: (c["due_date"], c["entry_id"]))
        return presented


__all__ = ["FinancialService", "month_bounds", "should_include_open_payment", "was_client_active_in_month"]
