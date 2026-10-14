"""Request bodies for the finance routes (`StrictHttpModel`, `extra="forbid"`).

Pydantic's silent drop of unknown keys would swallow a misspelled field on a WRITE;
forbidding extras turns it into a 422. Responses are plain dicts inside the seed
envelopes (card_hub / commerce convention). Money is integer cents everywhere.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from .entries import MAX_INSTALLMENTS
from .types import (
    AccountKind,
    ActivityKind,
    CategoryBehavior,
    CategoryDirection,
    DreLine,
    EntryDirection,
    Frequency,
    SettlementKind,
    TaxRegime,
)

#: Sanity bound (R$ 100 bi), not a business rule: keeps a typo from becoming a BIGINT-sized lie.
MAX_CENTS = 10_000_000_000_000


class AccountBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    kind: AccountKind
    bank_code: Optional[str] = Field(default=None, max_length=10)
    agency: Optional[str] = Field(default=None, max_length=20)
    number: Optional[str] = Field(default=None, max_length=40)
    opening_balance_cents: int = Field(default=0, ge=-MAX_CENTS, le=MAX_CENTS)
    opening_date: Optional[date] = None
    gateway: Optional[str] = Field(default=None, min_length=1, max_length=40)
    accounting_code: Optional[str] = Field(default=None, max_length=40)


class AccountPatch(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    bank_code: Optional[str] = Field(default=None, max_length=10)
    agency: Optional[str] = Field(default=None, max_length=20)
    number: Optional[str] = Field(default=None, max_length=40)
    opening_balance_cents: Optional[int] = Field(default=None, ge=-MAX_CENTS, le=MAX_CENTS)
    opening_date: Optional[date] = None
    gateway: Optional[str] = Field(default=None, min_length=1, max_length=40)
    active: Optional[bool] = None
    accounting_code: Optional[str] = Field(default=None, max_length=40)


class CategoryBody(StrictHttpModel):
    name: str = Field(min_length=1, max_length=80)
    direction: CategoryDirection
    parent_id: Optional[UUID] = None
    dre_line: Optional[DreLine] = None
    behavior: Optional[CategoryBehavior] = None
    is_das: bool = False
    accounting_code: Optional[str] = Field(default=None, max_length=40)
    activity_kind: Optional[ActivityKind] = None


class CategoryPatch(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    parent_id: Optional[UUID] = None
    active: Optional[bool] = None
    #: Explicit null is meaningful (unclassify / back to the line default): the route dumps with `exclude_unset`.
    dre_line: Optional[DreLine] = None
    behavior: Optional[CategoryBehavior] = None
    is_das: Optional[bool] = None
    accounting_code: Optional[str] = Field(default=None, max_length=40)
    activity_kind: Optional[ActivityKind] = None


class CostCenterBody(StrictHttpModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)


class CostCenterPatch(StrictHttpModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=30)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    active: Optional[bool] = None


class EntryBody(StrictHttpModel):
    direction: EntryDirection
    description: str = Field(min_length=1, max_length=300)
    counterparty_name: Optional[str] = Field(default=None, max_length=200)
    counterparty_doc: Optional[str] = Field(default=None, max_length=24)
    category_id: Optional[UUID] = None
    cost_center_id: Optional[UUID] = None
    expected_account_id: Optional[UUID] = None
    party_id: Optional[UUID] = None
    competence_month: Optional[date] = None
    due_date: date
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    installments: int = Field(default=1, ge=1, le=MAX_INSTALLMENTS)
    source: Literal["manual", "external"] = "manual"
    source_ref: Optional[str] = Field(default=None, min_length=1, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)
    #: Did this sale carry a nota fiscal? Feeds the MEI Relatório Mensal (null = not informed).
    has_invoice: Optional[bool] = None


class EntryPatch(StrictHttpModel):
    description: Optional[str] = Field(default=None, min_length=1, max_length=300)
    counterparty_name: Optional[str] = Field(default=None, max_length=200)
    counterparty_doc: Optional[str] = Field(default=None, max_length=24)
    category_id: Optional[UUID] = None
    cost_center_id: Optional[UUID] = None
    expected_account_id: Optional[UUID] = None
    party_id: Optional[UUID] = None
    competence_month: Optional[date] = None
    due_date: Optional[date] = None
    amount_cents: Optional[int] = Field(default=None, gt=0, le=MAX_CENTS)
    notes: Optional[str] = Field(default=None, max_length=2000)
    has_invoice: Optional[bool] = None


class SettleBody(StrictHttpModel):
    account_id: UUID
    kind: SettlementKind = SettlementKind.PAYMENT
    settled_on: Optional[date] = None
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    fee_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    method: Optional[str] = Field(default=None, max_length=40)
    external_ref: Optional[str] = Field(default=None, min_length=1, max_length=120)


class ReverseBody(StrictHttpModel):
    reason: str = Field(min_length=3, max_length=500)


class RecurrenceTemplateBody(StrictHttpModel):
    direction: EntryDirection
    description: str = Field(min_length=1, max_length=300)
    counterparty_name: Optional[str] = Field(default=None, max_length=200)
    counterparty_doc: Optional[str] = Field(default=None, max_length=24)
    category_id: Optional[UUID] = None
    cost_center_id: Optional[UUID] = None
    expected_account_id: Optional[UUID] = None
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    notes: Optional[str] = Field(default=None, max_length=2000)


class RecurrenceTemplatePatch(StrictHttpModel):
    direction: Optional[EntryDirection] = None
    description: Optional[str] = Field(default=None, min_length=1, max_length=300)
    counterparty_name: Optional[str] = Field(default=None, max_length=200)
    counterparty_doc: Optional[str] = Field(default=None, max_length=24)
    category_id: Optional[UUID] = None
    cost_center_id: Optional[UUID] = None
    expected_account_id: Optional[UUID] = None
    amount_cents: Optional[int] = Field(default=None, gt=0, le=MAX_CENTS)
    notes: Optional[str] = Field(default=None, max_length=2000)


class RecurrenceBody(StrictHttpModel):
    template: RecurrenceTemplateBody
    frequency: Frequency
    next_date: date
    end_date: Optional[date] = None
    active: bool = True


class RecurrencePatch(StrictHttpModel):
    template: Optional[RecurrenceTemplatePatch] = None
    frequency: Optional[Frequency] = None
    next_date: Optional[date] = None
    end_date: Optional[date] = None
    active: Optional[bool] = None


class TransferBody(StrictHttpModel):
    from_account_id: UUID
    to_account_id: UUID
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    occurred_on: Optional[date] = None
    description: Optional[str] = Field(default=None, max_length=300)


class BudgetItemBody(StrictHttpModel):
    category_id: UUID
    month: date
    amount_cents: int = Field(ge=0, le=MAX_CENTS)


class BudgetsBody(StrictHttpModel):
    """`PUT /budgets` -- an upsert by `(category_id, month)`; at most one grid screen (12 months x 40 categories)."""

    items: list[BudgetItemBody] = Field(min_length=1, max_length=500)


_DRE_LINE_CHOICE = Optional[DreLine]


class DreChoiceMeta(StrictHttpModel):
    """Confirmation of ONE provisional choice. `confirmed=True` clears `provisional` (stamped server-side with the
    caller and the time); `confirmed=False` returns it to provisional."""

    confirmed: bool
    note: Optional[str] = Field(default=None, max_length=500)


class DreSettingsBody(StrictHttpModel):
    """`PUT /dre-settings` -- every field optional (a partial update); nothing here moves money."""

    tax_regime: Optional[TaxRegime] = None
    das_split_irpj_csll: Optional[bool] = None
    das_irpj_csll_share_bps: Optional[int] = Field(default=None, ge=0, le=10_000)
    gateway_fee_line: _DRE_LINE_CHOICE = None
    anticipation_fee_line: _DRE_LINE_CHOICE = None
    chargeback_line: _DRE_LINE_CHOICE = None
    chargeback_fee_line: _DRE_LINE_CHOICE = None
    installment_interest_line: _DRE_LINE_CHOICE = None
    #: `{choice name: {confirmed, note}}` -- the accountant's sign-off per provisional choice.
    confirmations: dict[str, DreChoiceMeta] = Field(default_factory=dict)


__all__ = [
    "AccountBody",
    "AccountPatch",
    "BudgetItemBody",
    "BudgetsBody",
    "CategoryBody",
    "CategoryPatch",
    "CostCenterBody",
    "CostCenterPatch",
    "DreChoiceMeta",
    "DreSettingsBody",
    "EntryBody",
    "EntryPatch",
    "MAX_CENTS",
    "RecurrenceBody",
    "RecurrencePatch",
    "RecurrenceTemplateBody",
    "RecurrenceTemplatePatch",
    "ReverseBody",
    "SettleBody",
    "TransferBody",
]
