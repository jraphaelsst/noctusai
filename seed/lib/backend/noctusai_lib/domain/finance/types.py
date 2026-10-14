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


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    """The wire values of an enum, in declaration order (SQL CHECKs + parity tests)."""
    return tuple(member.value for member in enum_cls)


__all__ = [
    "AccountKind",
    "CategoryDirection",
    "EntryDirection",
    "EntrySource",
    "EntryStatus",
    "Frequency",
    "LedgerDirection",
    "LedgerOrigin",
    "MatchStatus",
    "SettlementKind",
    "StatementFormat",
    "values",
]
