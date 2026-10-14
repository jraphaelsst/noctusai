"""`finance_migration` -- snapshot, structure, CONTRACT §3.2 column parity, RLS on every table."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from noctusai_lib.domain.finance import APPEND_ONLY_TABLES, FINANCE_TABLES, FinanceConfig, finance_migration
from noctusai_lib.domain.finance.types import (
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
    TaxRegime,
    values,
)
from noctusai_lib.domain.finance.types import CategoryBehavior, DreLine
from noctusai_lib.testing.migration_parser import parse_sql

SNAPSHOT = Path(__file__).parent / "snapshots" / "finance_migration.sql"
CFG = FinanceConfig(schema="commerce")
SQL = finance_migration(CFG, "commerce")

#: CONTRACT §3.2 key columns, written out independently of the generator (unprefixed table names).
CONTRACT_COLUMNS = {
    "accounts": {
        "id", "org_id", "name", "kind", "bank_code", "agency", "number", "opening_balance_cents",
        "opening_date", "gateway", "active",
    },
    "categories": {"id", "org_id", "parent_id", "name", "direction", "is_default", "active", "dre_line", "behavior", "is_das"},
    "cost_centers": {"id", "org_id", "code", "name", "active"},
    "entries": {
        "id", "org_id", "direction", "status", "description", "counterparty_name", "counterparty_doc",
        "category_id", "cost_center_id", "expected_account_id", "competence_month", "due_date", "amount_cents",
        "settled_cents", "source", "source_ref", "recurrence_id", "installment_group_id", "installment_n",
        "installment_total", "notes", "created_at", "updated_at",
    },
    "recurrences": {"id", "org_id", "template", "frequency", "next_date", "end_date", "active"},
    "settlements": {
        "id", "org_id", "entry_id", "account_id", "kind", "settled_on", "amount_cents", "fee_cents", "method",
        "external_ref", "statement_line_id", "created_by", "reversed_at", "reversed_by", "reversal_reason",
    },
    "ledger": {
        "id", "org_id", "account_id", "occurred_on", "direction", "amount_cents", "origin", "settlement_id",
        "transfer_group", "reverses_id", "description",
    },
    "statement_imports": {
        "id", "org_id", "account_id", "format", "filename", "sha256", "period_start", "period_end", "imported_by", "at",
    },
    "statement_lines": {
        "id", "org_id", "import_id", "account_id", "posted_on", "amount_cents", "description", "fitid",
        "match_status", "ledger_id", "suggested_entry_id",
    },
    "attachments": {
        "id", "org_id", "entry_id", "storage_path", "filename", "content_type", "size_bytes", "uploaded_by", "at",
    },
    "gateway_sync": {"account_id", "cursor", "last_synced_at", "last_error"},
    # CONTRACT §10.5 (the shape of the per-choice confirmation is the `choice_meta` JSON, documented in dre_settings.py).
    "dre_settings": {
        "id", "org_id", "tax_regime", "das_split_irpj_csll", "das_irpj_csll_share_bps", "gateway_fee_line",
        "anticipation_fee_line", "chargeback_line", "chargeback_fee_line", "installment_interest_line", "choice_meta",
    },
}


def _block(table: str, sql: str = SQL, schema: str = "commerce") -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {schema}\.{table} \((.*?)\n\);", sql, re.S)
    assert match, f"{table} not emitted"
    return match.group(1)


def test_snapshot_is_current():
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(SQL)
    assert SNAPSHOT.read_text() == SQL, "finance_migration output changed: regenerate with UPDATE_SNAPSHOTS=1 and REVIEW the diff"


def test_generator_is_deterministic_and_schema_parametric():
    assert finance_migration(CFG, "commerce") == SQL
    other = finance_migration(FinanceConfig(schema="igig"), "igig")
    assert "igig.fin_entries" in other and "commerce.fin_entries" not in other


def test_prefix_is_configurable_and_applied_everywhere():
    sql = finance_migration(FinanceConfig(schema="x", table_prefix="fx_"), "x")
    assert "x.fx_entries" in sql and "x.fin_entries" not in sql
    assert re.search(r"REFERENCES x\.fx_accounts\(id\)", sql)


def test_every_contract_table_is_emitted_and_listed():
    emitted = set(re.findall(r"CREATE TABLE IF NOT EXISTS commerce\.(\w+) \(", SQL))
    assert {f"fin_{t}" for t in FINANCE_TABLES} == emitted
    assert set(CONTRACT_COLUMNS) == set(FINANCE_TABLES)
    assert set(APPEND_ONLY_TABLES) <= set(FINANCE_TABLES)


@pytest.mark.parametrize("table", FINANCE_TABLES)
def test_contract_columns_present(table):
    parsed = parse_sql(SQL, source_label="finance_migration")
    cols = {c.lower() for c in parsed[f"commerce.fin_{table}"]}
    missing = CONTRACT_COLUMNS[table] - cols
    assert not missing, f"{table} lacks contract columns: {sorted(missing)}"


@pytest.mark.parametrize("table", FINANCE_TABLES)
def test_every_table_is_org_scoped_with_rls(table):
    name = f"fin_{table}"
    assert re.search(r"\borg_id\s+UUID", _block(name)), f"{name} has no org_id"
    assert f"ALTER TABLE commerce.{name} ENABLE ROW LEVEL SECURITY" in SQL
    assert f'"{name}_select_own_org"' in SQL
    assert re.search(rf'CREATE POLICY "service_role_bypass"\s+ON commerce\.{name}\b', SQL)
    # No authenticated WRITE policy anywhere: the backend writes through the service role.
    assert not re.search(rf"ON commerce\.{name}\s+FOR (INSERT|UPDATE|DELETE)", SQL)


def test_org_id_expr_defaults_to_org_picker_aware_function_and_is_overridable():
    assert "org_id = (SELECT public.current_org_id_for('commerce'))" in SQL
    custom = finance_migration(FinanceConfig(schema="commerce", org_id_expr="public.current_org_id()"), "commerce")
    assert "org_id = (SELECT public.current_org_id())" in custom


def test_enum_checks_match_the_python_enums():
    for table, col, enum in (
        ("fin_accounts", "kind", AccountKind),
        ("fin_categories", "direction", CategoryDirection),
        ("fin_entries", "direction", EntryDirection),
        ("fin_entries", "status", EntryStatus),
        ("fin_entries", "source", EntrySource),
        ("fin_recurrences", "frequency", Frequency),
        ("fin_settlements", "kind", SettlementKind),
        ("fin_ledger", "direction", LedgerDirection),
        ("fin_ledger", "origin", LedgerOrigin),
        ("fin_statement_imports", "format", StatementFormat),
        ("fin_statement_lines", "match_status", MatchStatus),
    ):
        check = f"{col}" + r"\s+TEXT[^,\n]*CHECK \(" + col + r" IN \(([^)]*)\)\)"
        found = re.search(check, _block(table))
        assert found, f"{table}.{col} CHECK missing"
        assert tuple(re.findall(r"'([^']+)'", found.group(1))) == values(enum)


def test_dre_columns_are_additive_and_rerunnable():
    # Tables created by an OLDER generator gain the columns on re-run: ADD COLUMN IF NOT EXISTS, never a bare ADD.
    assert not re.search(r"ADD COLUMN (?!IF NOT EXISTS)", SQL)
    for col in ("dre_line", "behavior", "is_das"):
        assert f"ALTER TABLE commerce.fin_categories ADD COLUMN IF NOT EXISTS {col} " in SQL


def test_dre_enum_checks_match_the_python_enums():
    cat = re.search(r"ADD COLUMN IF NOT EXISTS dre_line TEXT\s+CHECK \(dre_line IN \(([^)]*)\)\)", SQL)
    assert cat and tuple(re.findall(r"'([^']+)'", cat.group(1))) == values(DreLine)
    beh = re.search(r"ADD COLUMN IF NOT EXISTS behavior TEXT\s+CHECK \(behavior IN \(([^)]*)\)\)", SQL)
    assert beh and tuple(re.findall(r"'([^']+)'", beh.group(1))) == values(CategoryBehavior)
    block = _block("fin_dre_settings")
    regime = re.search(r"tax_regime\s+TEXT[^\n]*CHECK \(tax_regime IN \(([^)]*)\)\)", block)
    assert regime and tuple(re.findall(r"'([^']+)'", regime.group(1))) == values(TaxRegime)
    real = tuple(v for v in values(DreLine) if v != "unclassified")
    for col in ("gateway_fee_line", "anticipation_fee_line", "chargeback_line", "chargeback_fee_line", "installment_interest_line"):
        found = re.search(rf"{col}\s+TEXT[^\n]*CHECK \({col} IN \(([^)]*)\)\)", block)
        assert found, col
        assert tuple(re.findall(r"'([^']+)'", found.group(1))) == real  # a choice may never be 'unclassified'


def test_dre_settings_is_one_row_per_org_with_the_documented_defaults():
    block = _block("fin_dre_settings")
    assert re.search(r"org_id\s+UUID NOT NULL UNIQUE", block)
    for col, default in (
        ("gateway_fee_line", "selling_expenses"), ("anticipation_fee_line", "financial_expenses"),
        ("chargeback_line", "deductions"), ("chargeback_fee_line", "selling_expenses"),
        ("installment_interest_line", "gross_revenue"), ("tax_regime", "unknown"),
    ):
        assert re.search(rf"{col}\s+TEXT NOT NULL DEFAULT '{default}'", block), col


def test_money_is_bigint_cents_and_positive_where_it_must_be():
    assert "amount_cents         BIGINT NOT NULL CHECK (amount_cents > 0)" in _block("fin_entries")
    assert "amount_cents      BIGINT NOT NULL CHECK (amount_cents > 0)" in _block("fin_settlements")
    assert "fee_cents         BIGINT NOT NULL DEFAULT 0 CHECK (fee_cents >= 0)" in _block("fin_settlements")
    assert "amount_cents   BIGINT NOT NULL CHECK (amount_cents > 0)" in _block("fin_ledger")


@pytest.mark.parametrize(
    "fragment",
    [
        # accounts: one gateway account per (org, gateway)
        r"uq_fin_accounts_gateway ON commerce\.fin_accounts \(org_id, gateway\)\s+WHERE kind = 'gateway'",
        # categories: unique (org, parent, lower(name)) -- NULL parent handled
        r"uq_fin_categories_name ON commerce\.fin_categories\s+\(org_id, COALESCE\(parent_id, '0{8}-0{4}-0{4}-0{4}-0{12}'::uuid\), lower\(name\)\)",
        # cost centers: code unique per org
        r"UNIQUE \(org_id, code\)",
        # entries: source_ref unique per (org, source); recurrence idempotency; installment uniqueness
        r"uq_fin_entries_source_ref ON commerce\.fin_entries \(org_id, source, source_ref\)\s+WHERE source_ref IS NOT NULL",
        r"uq_fin_entries_recurrence_due ON commerce\.fin_entries \(recurrence_id, due_date\)\s+WHERE recurrence_id IS NOT NULL",
        r"uq_fin_entries_installment ON commerce\.fin_entries \(installment_group_id, installment_n\)",
        # settlements: (kind, external_ref) when not null
        r"uq_fin_settlements_external ON commerce\.fin_settlements \(org_id, kind, external_ref\)\s+WHERE external_ref IS NOT NULL",
        # ledger: one row per (settlement, origin) unless it is a reversal; a row is reversed at most once
        r"uq_fin_ledger_settlement_origin ON commerce\.fin_ledger \(settlement_id, origin\)\s+WHERE settlement_id IS NOT NULL AND reverses_id IS NULL",
        r"uq_fin_ledger_reverses ON commerce\.fin_ledger \(reverses_id\)",
        # statements: sha256 unique per account; fitid unique per account; a ledger row matches one line
        r"UNIQUE \(account_id, sha256\)",
        r"UNIQUE \(account_id, fitid\)",
        r"uq_fin_statement_lines_ledger ON commerce\.fin_statement_lines \(ledger_id\)\s+WHERE ledger_id IS NOT NULL",
    ],
)
def test_contract_uniqueness_is_emitted(fragment):
    assert re.search(fragment, SQL), fragment


def test_statement_line_ledger_fk_closes_the_cycle_idempotently():
    assert "fin_statement_lines_ledger_id_fkey" in SQL
    assert "IF NOT EXISTS" in SQL.split("DO $fin_fk$")[1]


def test_migration_is_rerunnable_text():
    # Every statement is guarded for the chain replay's second application.
    for stmt in re.findall(r"^CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", SQL, re.M):
        pytest.fail(f"unguarded index: {stmt}")
    assert not re.search(r"^CREATE TABLE (?!IF NOT EXISTS)", SQL, re.M)
    for table in FINANCE_TABLES:
        assert f'DROP POLICY IF EXISTS "fin_{table}_select_own_org"' in SQL


def test_attachments_bucket_is_private():
    assert "VALUES ('finance-attachments', 'finance-attachments', false)" in SQL


def test_config_validation():
    with pytest.raises(ValueError):
        FinanceConfig(schema="Bad-Schema")
    with pytest.raises(ValueError):
        FinanceConfig(schema="ok", table_prefix="Fin-")
    with pytest.raises(ValueError):
        FinanceConfig(schema="ok", signed_url_ttl_seconds=601)  # contract: <= 10 minutes
    with pytest.raises(ValueError):
        FinanceConfig(schema="ok", org_id_expr="  ")
    with pytest.raises(ValueError):
        finance_migration(CFG, " ")
