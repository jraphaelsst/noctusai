"""Pydantic schemas for /api/financial -- the Orbity-specific layer over the seed finance + contracts organs.

Contracts, receivables, payables and settlements are the organs' (``/api/contracts``, ``/api/finance``). What lives here
is only what the organs do not know: the cash-flow summary that honours the "kept after inactivation" rule, and the
gateway state of each charge (``billing_charges``).

StrictHttpModel (extra="forbid") on every inbound model.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class MonthlyCashFlowOut(StrictHttpModel):
    """One calendar month. Revenues follow ``financial_service.should_include_open_payment``: paid always counts,
    cancelled never, an open charge counts when it was kept after the client's inactivation or the client was active
    that month. Expenses are the month's payables (paid / still open)."""

    reference_month: str   # YYYY-MM-DD (first day of month)
    paid_revenues: float
    paid_expenses: float
    net: float             # paid_revenues - paid_expenses
    pending_revenues: float
    overdue_revenues: float

    model_config = {"extra": "ignore"}


class ChargeOut(StrictHttpModel):
    """A receivable + its gateway state. ``generation_status``: queued | generating | retrying | generated | failed | skipped."""

    entry_id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    contract_id: Optional[str] = None
    description: str
    due_date: str
    amount_cents: int
    settled_cents: int
    entry_status: str           # open | partial | paid | cancelled
    overdue: bool
    generation_status: str
    generation_attempts: int
    last_error: Optional[str] = None
    next_attempt_at: Optional[str] = None
    gateway: Optional[str] = None
    billing_method: Optional[str] = None
    external_id: Optional[str] = None
    invoice_url: Optional[str] = None
    pix_payload: Optional[str] = None
    preserved_after_deactivation: bool = False
    gateway_cancel_status: Optional[str] = None
    gateway_cancel_error: Optional[str] = None

    model_config = {"extra": "ignore"}


class ChargeListOut(StrictHttpModel):
    items: list[ChargeOut]
    total: int
    page: int
    page_size: int


class ExtraChargeCreate(StrictHttpModel):
    client_id: str
    description: str = Field(..., min_length=1, max_length=255)
    amount_cents: int = Field(..., gt=0)
    due_date: date
