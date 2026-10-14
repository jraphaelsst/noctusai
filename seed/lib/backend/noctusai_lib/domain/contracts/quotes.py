"""`ContractFromQuote` -- the seam the quotes organ's accept step uses to open a contract.

A plain dataclass on purpose: contracts does NOT import the quotes organ (they are built in
parallel and either may be mounted without the other). The quotes side builds a `ContractFromQuote`
from the accepted quote and calls `create_contract_from_quote`; the contract is a DRAFT (the
operator reviews, renders and activates it), idempotent per `quote_id` -- accepting the same quote
twice returns the same contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ._common import Scope, first
from .contracts import create_contract
from .types import BillingModel


@dataclass(frozen=True)
class QuoteLine:
    description: str
    unit_price_cents: int
    quantity: int = 1
    item_id: Optional[str] = None


@dataclass(frozen=True)
class ContractFromQuote:
    """What an accepted quote hands to contracts. Billing fields are the operator's/quote's choice, defaulted."""

    quote_id: str
    title: str
    lines: tuple[QuoteLine, ...]
    party_id: Optional[str] = None
    party_name: Optional[str] = None
    party_doc: Optional[str] = None
    billing_model: BillingModel = BillingModel.ONE_TIME
    first_due_date: Optional[date] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    installments_count: Optional[int] = None
    due_day: Optional[int] = None
    notes: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


def create_contract_from_quote(s: Scope, quote: ContractFromQuote, *, user_id: Optional[str] = None) -> tuple[dict, bool]:
    """`(contract, created)` -- the existing contract when this quote already produced one."""
    quote_id = str(quote.quote_id)
    existing = first(s.tbl("contracts").select("*").eq("org_id", s.org_id).eq("source_quote_id", quote_id).limit(1).execute())
    if existing is not None:
        return existing, False
    data = {
        "title": quote.title, "party_id": quote.party_id, "party_name": quote.party_name, "party_doc": quote.party_doc,
        "billing_model": quote.billing_model, "first_due_date": quote.first_due_date, "start_date": quote.start_date,
        "end_date": quote.end_date, "installments_count": quote.installments_count, "due_day": quote.due_day,
        "notes": quote.notes,
        "lines": [{"description": ln.description, "quantity": ln.quantity, "unit_price_cents": ln.unit_price_cents,
                   "item_id": ln.item_id} for ln in quote.lines],
        **quote.extra,
    }
    data = {k: v for k, v in data.items() if v is not None}
    return create_contract(s, data, user_id=user_id, source_quote_id=quote_id), True


__all__ = ["ContractFromQuote", "QuoteLine", "create_contract_from_quote"]
