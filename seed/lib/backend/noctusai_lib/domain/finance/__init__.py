"""Finance -- the generic financial core, as an L1 seed organ.

Accounts (bank / cash / gateway), a category tree + cost centers, payable / receivable
entries (installment groups, recurrences), settlements with an append-only ledger and
reversal, transfers, and the reports a small business asks for first: cash flow
(realized + projected), the structured DRE (NBC TG 1002 lines, per-store mapping, guidance), the Simples tax base,
receivables aging. Money is integer
cents; `overdue` is computed on read; `counterparty_doc` (CPF/CNPJ) is masked for
non-admins (LGPD).

Mount it from a product:

    cfg = FinanceConfig(schema="commerce")
    sql = finance_migration(cfg, "commerce")                  # -> migrations/0NN_finance.sql
    app.include_router(make_finance_router(cfg, auth_dependency, admin_dependency,
                                           resolve_context=..., get_db=..., get_storage=...))
    booking = make_finance_booking("supabase", db=..., cfg=cfg)   # the seam other organs book through

Slice D adds (new files): statement import (`statements`, `ofx`, `csv_import`), reconciliation
(`matching`), gateway sync (`gateway_sync`) and exports (`exports`), served by a SECOND router the
host mounts next to the first:

    app.include_router(make_finance_reconciliation_router(cfg, auth, admin, resolve_context=..., get_db=...,
                                                          get_storage=..., get_charge_operations=...))
    max_body_path_overrides[STATEMENT_UPLOAD_PATH_PATTERN] = STATEMENT_UPLOAD_MAX_BYTES
    register_gateway_sync(cfg, get_db=..., operations_for=...)        # job `finance_gateway_sync`, every 6 h

Accountant additions (E16/E21): budget vs actual (`budgets`), the Livro Caixa (`livro_caixa`), the MEI Relatório Mensal (`mei`), the
Domínio export (`dominio`, layout notes in `DOMINIO-LAYOUT.md`) and a READ-only accountant grant -- pass
`accountant_dependency=` (org admin OR the PER-ORG permission `finance.accountant_read:<org_id>`) to both routers.

Billing reminders (dunning, WhatsApp): see `reminders/__init__.py` (job `finance_billing_reminders`, organ `finance_reminders`).

Contract: `projects/commerce-seed-p4/CONTRACT.md §3`. Jobs the host registers:
`finance_generate_recurrences` (daily, `recurrences.generate_due_recurrences`).
"""
from . import (
    accountant,
    accounts,
    attachments,
    booking,
    budgets,
    categories,
    dominio,
    dre,
    dre_settings,
    entries,
    exports,
    gateway_sync,
    livro_caixa,
    matching,
    mei,
    recurrences,
    reminders,
    reports,
    settlements,
    simples_base,
    statements,
)
from .attachments import ATTACHMENT_UPLOAD_MAX_BYTES, ATTACHMENT_UPLOAD_PATH_PATTERN
from .booking import (
    FakeFinanceBooking,
    FinanceBooking,
    NoopFinanceBooking,
    SupabaseFinanceBooking,
    make_finance_booking,
)
from .config import ACCOUNTANT_READ_PERMISSION, FinanceConfig, FinanceContext, accountant_permission_for
from .entries import mask_doc
from .errors import FinanceError
from .gateway_sync import register_gateway_sync, run_gateway_sync_all
from .recurrences import calcular_proxima_data, generate_due_recurrences
from .reconciliation_router import make_finance_reconciliation_router
from .router import make_finance_router
from .statements import STATEMENT_UPLOAD_MAX_BYTES, STATEMENT_UPLOAD_PATH_PATTERN
from .sql import APPEND_ONLY_TABLES, FINANCE_TABLES, finance_migration
from .types import (
    AccountKind,
    ActivityKind,
    CategoryBehavior,
    CategoryDirection,
    DreLine,
    EntryDirection,
    EntrySource,
    EntryStatus,
    Frequency,
    LedgerDirection,
    LedgerOrigin,
    MatchStatus,
    SettlementKind,
    StatementFormat,
    TaxRegime,
)

__all__ = [
    "ACCOUNTANT_READ_PERMISSION",
    "APPEND_ONLY_TABLES",
    "ATTACHMENT_UPLOAD_MAX_BYTES",
    "ATTACHMENT_UPLOAD_PATH_PATTERN",
    "AccountKind",
    "ActivityKind",
    "CategoryBehavior",
    "CategoryDirection",
    "DreLine",
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
    "STATEMENT_UPLOAD_MAX_BYTES",
    "STATEMENT_UPLOAD_PATH_PATTERN",
    "SettlementKind",
    "StatementFormat",
    "SupabaseFinanceBooking",
    "TaxRegime",
    "accountant",
    "accountant_permission_for",
    "accounts",
    "attachments",
    "booking",
    "budgets",
    "calcular_proxima_data",
    "categories",
    "dominio",
    "dre",
    "dre_settings",
    "entries",
    "exports",
    "finance_migration",
    "gateway_sync",
    "generate_due_recurrences",
    "livro_caixa",
    "make_finance_booking",
    "make_finance_reconciliation_router",
    "make_finance_router",
    "mask_doc",
    "matching",
    "mei",
    "recurrences",
    "register_gateway_sync",
    "reminders",
    "reports",
    "run_gateway_sync_all",
    "settlements",
    "simples_base",
    "statements",
]
