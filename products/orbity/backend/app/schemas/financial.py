"""
Pydantic schemas for the /api/financial endpoints.

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).

Covers: contracts, expenses, revenues, and the monthly cash-flow summary.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

ContractStatusLiteral = Literal["active", "paused", "ended"]
RecurrenceLiteral     = Literal["none", "monthly", "installment"]
RevenueStatusLiteral  = Literal["pending", "paid", "overdue", "canceled"]


# ---------------------------------------------------------------------------
# contracts — inbound
# ---------------------------------------------------------------------------

class ContractCreate(StrictHttpModel):
    client_id:     Optional[UUID] = None
    title:         str            = Field(..., min_length=1, max_length=500)
    monthly_value: float          = Field(..., ge=0)
    billing_day:   int            = Field(default=1, ge=1, le=31)
    start_date:    str            = Field(...)          # ISO date string YYYY-MM-DD
    end_date:      Optional[str]  = None
    status:        ContractStatusLiteral = "active"
    notes:         Optional[str]  = Field(default=None, max_length=5000)


class ContractUpdate(StrictHttpModel):
    client_id:     Optional[UUID]                      = None
    title:         Optional[str]  = Field(default=None, min_length=1, max_length=500)
    monthly_value: Optional[float]= Field(default=None, ge=0)
    billing_day:   Optional[int]  = Field(default=None, ge=1, le=31)
    start_date:    Optional[str]  = None
    end_date:      Optional[str]  = None
    status:        Optional[ContractStatusLiteral]     = None
    notes:         Optional[str]  = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# expenses — inbound
# ---------------------------------------------------------------------------

class ExpenseCreate(StrictHttpModel):
    category:           str              = Field(default="other", max_length=200)
    description:        str              = Field(..., min_length=1, max_length=500)
    amount:             float            = Field(..., gt=0)
    due_date:           str              = Field(...)          # ISO date YYYY-MM-DD
    paid:               bool             = False
    paid_at:            Optional[str]    = None
    recurrence:         RecurrenceLiteral = "none"
    installments_total: Optional[int]    = Field(default=None, ge=1)
    installment_n:      Optional[int]    = Field(default=None, ge=1)


class ExpenseUpdate(StrictHttpModel):
    category:           Optional[str]              = Field(default=None, max_length=200)
    description:        Optional[str]              = Field(default=None, min_length=1, max_length=500)
    amount:             Optional[float]            = Field(default=None, gt=0)
    due_date:           Optional[str]              = None
    paid:               Optional[bool]             = None
    paid_at:            Optional[str]              = None
    recurrence:         Optional[RecurrenceLiteral] = None
    installments_total: Optional[int]              = Field(default=None, ge=1)
    installment_n:      Optional[int]              = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# revenues — inbound
# ---------------------------------------------------------------------------

class RevenueCreate(StrictHttpModel):
    client_id:       Optional[UUID] = None
    contract_id:     Optional[UUID] = None
    reference_month: str            = Field(...)   # ISO date, first day of month
    amount:          float          = Field(..., gt=0)
    status:          RevenueStatusLiteral = "pending"
    due_date:        str            = Field(...)   # ISO date YYYY-MM-DD
    paid_at:         Optional[str]  = None


class RevenueUpdate(StrictHttpModel):
    client_id:       Optional[UUID]                    = None
    contract_id:     Optional[UUID]                    = None
    reference_month: Optional[str]                     = None
    amount:          Optional[float]                   = Field(default=None, gt=0)
    status:          Optional[RevenueStatusLiteral]    = None
    due_date:        Optional[str]                     = None
    paid_at:         Optional[str]                     = None


# ---------------------------------------------------------------------------
# Outbound (extra="ignore" — DB may return extra columns safely)
# ---------------------------------------------------------------------------

class ContractOut(StrictHttpModel):
    id:            UUID
    org_id:        UUID
    client_id:     Optional[UUID] = None
    title:         str
    monthly_value: float
    billing_day:   int
    start_date:    str
    end_date:      Optional[str]  = None
    status:        ContractStatusLiteral
    notes:         Optional[str]  = None
    created_at:    str
    updated_at:    str

    model_config = {"extra": "ignore"}


class ExpenseOut(StrictHttpModel):
    id:                 UUID
    org_id:             UUID
    category:           str
    description:        str
    amount:             float
    due_date:           str
    paid:               bool
    paid_at:            Optional[str]  = None
    recurrence:         RecurrenceLiteral
    installments_total: Optional[int]  = None
    installment_n:      Optional[int]  = None
    created_at:         str
    updated_at:         str

    model_config = {"extra": "ignore"}


class RevenueOut(StrictHttpModel):
    id:              UUID
    org_id:          UUID
    client_id:       Optional[UUID] = None
    contract_id:     Optional[UUID] = None
    reference_month: str
    amount:          float
    status:          RevenueStatusLiteral
    due_date:        str
    paid_at:         Optional[str]  = None
    created_at:      str
    updated_at:      str

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Cash-flow summary — outbound
# ---------------------------------------------------------------------------

class MonthlyCashFlowOut(StrictHttpModel):
    """Aggregate cash-flow for a single calendar month.

    Both paid_revenues and paid_expenses are cash-basis (only status='paid'
    or paid=true rows). net is the simple difference.
    """
    reference_month:  str    # YYYY-MM-DD (first day of month)
    paid_revenues:    float  # Σ revenues.amount WHERE status='paid'
    paid_expenses:    float  # Σ expenses.amount WHERE paid=true
    net:              float  # paid_revenues − paid_expenses
    pending_revenues: float  # Σ revenues.amount WHERE status='pending'
    overdue_revenues: float  # Σ revenues.amount WHERE status='overdue'

    model_config = {"extra": "ignore"}
