"""Finance -- the generic financial core, as an L1 seed organ.

Accounts (bank / cash / gateway), a category tree + cost centers, payable / receivable
entries (installment groups, recurrences), settlements with an append-only ledger and
reversal, transfers, and the reports a small business asks for first: cash flow
(realized + projected), DRE by competence month, receivables aging. Money is integer
cents; `overdue` is computed on read; `counterparty_doc` (CPF/CNPJ) is masked for
non-admins (LGPD).

Mount it from a product:

    cfg = FinanceConfig(schema="commerce")
    sql = finance_migration(cfg, "commerce")                  # -> migrations/0NN_finance.sql
    app.include_router(make_finance_router(cfg, auth_dependency, admin_dependency,
                                           resolve_context=..., get_db=..., get_storage=...))
    booking = make_finance_booking("supabase", db=..., cfg=cfg)   # the seam other organs book through

Slice D (wave 2) adds, in new files of this package: statement import + reconciliation,
gateway sync and exports. Their tables are already in `finance_migration`.

Contract: `projects/commerce-seed-p4/CONTRACT.md §3`. Jobs the host registers:
`finance_generate_recurrences` (daily, `recurrences.generate_due_recurrences`).
"""
from . import (
    accounts,
    attachments,
    booking,
    categories,
    entries,
    recurrences,
    reports,
    settlements,
)
from .attachments import ATTACHMENT_UPLOAD_MAX_BYTES, ATTACHMENT_UPLOAD_PATH_PATTERN
from .booking import (
    FakeFinanceBooking,
    FinanceBooking,
    NoopFinanceBooking,
    SupabaseFinanceBooking,
    make_finance_booking,
)
from .config import FinanceConfig, FinanceContext
from .entries import mask_doc
from .errors import FinanceError
from .recurrences import calcular_proxima_data, generate_due_recurrences
from .router import make_finance_router
from .sql import APPEND_ONLY_TABLES, FINANCE_TABLES, finance_migration
from .types import (
    AccountKind,
    CategoryDirection,
    EntryDirection,
    EntrySource,
    EntryStatus,
    Frequency,
    LedgerDirection,
    LedgerOrigin,
    MatchStatus,
    SettlementKind,
    StatementFormat,
)

__all__ = [
    "APPEND_ONLY_TABLES",
    "ATTACHMENT_UPLOAD_MAX_BYTES",
    "ATTACHMENT_UPLOAD_PATH_PATTERN",
    "AccountKind",
    "CategoryDirection",
    "EntryDirection",
    "EntrySource",
    "EntryStatus",
    "FINANCE_TABLES",
    "FakeFinanceBooking",
    "FinanceBooking",
    "FinanceConfig",
    "FinanceContext",
    "FinanceError",
    "Frequency",
    "LedgerDirection",
    "LedgerOrigin",
    "MatchStatus",
    "NoopFinanceBooking",
    "SettlementKind",
    "StatementFormat",
    "SupabaseFinanceBooking",
    "accounts",
    "attachments",
    "booking",
    "calcular_proxima_data",
    "categories",
    "entries",
    "finance_migration",
    "generate_due_recurrences",
    "make_finance_booking",
    "make_finance_router",
    "mask_doc",
    "recurrences",
    "reports",
    "settlements",
]
