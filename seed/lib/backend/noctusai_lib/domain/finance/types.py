"""Finance vocabulary -- every enum of `projects/commerce-seed-p4/CONTRACT.md §3.1`.

`str` Enums, so a value serialises as its bare string in JSON and compares equal
to the literal the frontend organ mirrors. Renaming a member is a wire-contract
change, never a refactor (`values()` feeds the SQL CHECKs and the parity tests).
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class AccountKind(_StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    GATEWAY = "gateway"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"


class EntryDirection(_StrEnum):
    PAYABLE = "payable"
    RECEIVABLE = "receivable"


class EntryStatus(_StrEnum):
    """Stored status. `overdue` is NEVER stored: it is computed on read (`overdue` flag)."""

    OPEN = "open"
    PARTIAL = "partial"
    PAID = "paid"
    CANCELLED = "cancelled"


class CategoryDirection(_StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class Frequency(_StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    BIMONTHLY = "bimonthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


class EntrySource(_StrEnum):
    MANUAL = "manual"
    RECURRENCE = "recurrence"
    INSTALLMENT = "installment"
    COMMERCE_ORDER = "commerce_order"
    IMPORT = "import"
    EXTERNAL = "external"


class SettlementKind(_StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"


class LedgerOrigin(_StrEnum):
    SETTLEMENT = "settlement"
    FEE = "fee"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    OPENING = "opening"


class LedgerDirection(_StrEnum):
    IN = "in"
    OUT = "out"


class StatementFormat(_StrEnum):
    OFX = "ofx"
    CSV = "csv"


class MatchStatus(_StrEnum):
    UNMATCHED = "unmatched"
    SUGGESTED = "suggested"
    MATCHED = "matched"
    IGNORED = "ignored"


class DreLine(_StrEnum):
    """DRE lines in STATEMENT ORDER (CONTRACT §10.1 / NBC TG 1002 §5.1). Subtotals are computed, never a member.

    `unclassified` is the block for money whose category has no line: shown apart, never dropped (D47)."""

    GROSS_REVENUE = "gross_revenue"
    DEDUCTIONS = "deductions"
    COST_OF_SALES = "cost_of_sales"
    SELLING_EXPENSES = "selling_expenses"
    ADMINISTRATIVE_EXPENSES = "administrative_expenses"
    OTHER_OPERATING = "other_operating"
    FINANCIAL_REVENUE = "financial_revenue"
    FINANCIAL_EXPENSES = "financial_expenses"
    INCOME_TAXES = "income_taxes"
    UNCLASSIFIED = "unclassified"


class TaxRegime(_StrEnum):
    """The store's tax regime (CONTRACT §10.5.1). `unknown` raises the `regime_nao_informado` warning."""

    MEI = "mei"
    SIMPLES = "simples"
    PRESUMIDO = "presumido"
    UNKNOWN = "unknown"


class CategoryBehavior(_StrEnum):
    """Managerial view (CONTRACT §10.5.6): does the cost move with sales (`variable`) or not (`fixed`)?"""

    VARIABLE = "variable"
    FIXED = "fixed"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    """The wire values of an enum, in declaration order (SQL CHECKs + parity tests)."""
    return tuple(member.value for member in enum_cls)


__all__ = [
    "AccountKind",
    "CategoryBehavior",
    "CategoryDirection",
    "DreLine",
    "EntryDirection",
    "EntrySource",
    "EntryStatus",
    "Frequency",
    "LedgerDirection",
    "LedgerOrigin",
    "MatchStatus",
    "SettlementKind",
    "StatementFormat",
    "TaxRegime",
    "values",
]
