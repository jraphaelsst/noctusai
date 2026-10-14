"""`quotes_migration` -- structure, RLS on every table, enum parity, composite FKs, re-runnable text, config validation."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.domain.quotes import APPEND_ONLY_TABLES, QUOTES_TABLES, QuotesConfig, quotes_migration
from noctusai_lib.domain.quotes.sql import FROZEN_QUOTE_COLUMNS
from noctusai_lib.domain.quotes.types import (
    Channel, ConversionStatus, ConvertTo, Decision, EventKind, LineKind, QuoteStatus, values,
)
from noctusai_lib.testing.migration_parser import parse_sql

CFG = QuotesConfig(schema="erp")
SQL = quotes_migration(CFG, "erp")

CONTRACT_COLUMNS = {
    "counters": {"org_id", "last_number"},
    "quotes": {
        "id", "org_id", "number", "root_id", "version", "is_current", "party_id", "title", "status", "currency", "valid_until",
        "notes", "terms", "convert_to", "subtotal_cents", "discount_cents", "total_cents", "sent_at", "last_sent_to", "viewed_at",
        "accepted_at", "rejected_at", "expired_at", "rejection_reason", "conversion_status", "conversion_kind", "conversion_ref",
        "conversion_error", "signature_ref", "signature_status", "created_by", "created_at", "updated_at",
    },
    "lines": {"id", "org_id", "quote_id", "position", "item_id", "description", "unit", "kind", "qty", "unit_price_cents",
              "discount_cents", "total_cents"},
    "acceptances": {"id", "org_id", "quote_id", "decision", "channel", "signer_name", "reason", "consent_text", "content_sha256",
                    "ip", "user_agent", "decided_by", "decided_at"},
    "events": {"id", "seq", "org_id", "quote_id", "kind", "from_status", "to_status", "actor", "detail", "at"},
}


def _block(table: str, sql: str = SQL) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS erp\.{table} \((.*?)\n\);", sql, re.S)
    assert match, f"{table} not emitted"
    return match.group(1)


def test_generator_is_deterministic_and_schema_parametric():
    assert quotes_migration(CFG, "erp") == SQL
    other = quotes_migration(QuotesConfig(schema="igig"), "igig")
    assert "igig.quo_quotes" in other and "erp.quo_quotes" not in other


def test_schema_must_match_config():
    with pytest.raises(ValueError):
        quotes_migration(CFG, "other")
    with pytest.raises(ValueError):
        quotes_migration(CFG, " ")


def test_prefix_is_configurable_everywhere():
    sql = quotes_migration(QuotesConfig(schema="x", table_prefix="qt_"), "x")
    assert "x.qt_quotes" in sql and "x.quo_quotes" not in sql and "x.qt_next_number" in sql


def test_every_table_is_emitted_and_listed():
    emitted = set(re.findall(r"CREATE TABLE IF NOT EXISTS erp\.(\w+) \(", SQL))
    assert {f"quo_{t}" for t in QUOTES_TABLES} == emitted
    assert set(CONTRACT_COLUMNS) == set(QUOTES_TABLES)


@pytest.mark.parametrize("table", QUOTES_TABLES)
def test_contract_columns_present(table):
    cols = {c.lower() for c in parse_sql(SQL, source_label="quotes_migration")[f"erp.quo_{table}"]}
    assert not CONTRACT_COLUMNS[table] - cols


@pytest.mark.parametrize("table", QUOTES_TABLES)
def test_every_table_is_org_scoped_with_rls(table):
    name = f"quo_{table}"
    assert re.search(r"\borg_id\s+UUID", _block(name)), f"{name} has no org_id"
    assert f"ALTER TABLE erp.{name} ENABLE ROW LEVEL SECURITY" in SQL
    assert f'"{name}_select_own_org"' in SQL and '"service_role_bypass"' in SQL
    assert f"GRANT SELECT ON erp.{name} TO authenticated" in SQL and f"GRANT ALL ON erp.{name} TO service_role" in SQL
    assert "public.current_org_id_for('erp')" in SQL


def test_no_authenticated_write_policy_exists():
    assert not re.search(r"FOR (INSERT|UPDATE|DELETE|ALL)\s+TO authenticated", SQL, re.I)


def test_composite_org_foreign_keys_make_cross_tenant_references_impossible():
    assert "FOREIGN KEY (party_id, org_id) REFERENCES erp.pty_parties (id, org_id)" in SQL
    assert "FOREIGN KEY (quote_id, org_id) REFERENCES erp.quo_quotes (id, org_id)" in SQL
    assert "UNIQUE (id, org_id)" in _block("quo_quotes")


def test_cross_organ_fks_are_opt_out():
    bare = quotes_migration(QuotesConfig(schema="erp", with_parties=False, with_items=False), "erp")
    assert "pty_parties" not in bare and "itm_items" not in bare
    assert "REFERENCES erp.itm_items(id)" in SQL


def test_money_is_integer_cents_and_total_is_checked():
    block = _block("quo_quotes")
    for col in ("subtotal_cents", "discount_cents", "total_cents"):
        assert re.search(rf"{col}\s+BIGINT", block)
    assert "CHECK (total_cents = subtotal_cents - discount_cents)" in block
    assert not re.search(r"\b(NUMERIC|FLOAT|REAL|DOUBLE)\b.*(price|total)", SQL, re.I)


def test_version_chain_indexes():
    assert "uq_quo_quotes_version ON erp.quo_quotes (org_id, root_id, version)" in SQL
    assert "uq_quo_quotes_current ON erp.quo_quotes (org_id, root_id) WHERE is_current" in SQL
    assert "uq_quo_quotes_accepted ON erp.quo_quotes (org_id, root_id) WHERE status = 'accepted'" in SQL


def test_frozen_columns_are_exactly_the_commercial_ones():
    assert not {"status", "sent_at", "accepted_at", "signature_ref", "conversion_status", "is_current"} & set(FROZEN_QUOTE_COLUMNS)
    assert {"valid_until", "terms", "total_cents", "party_id", "number", "version"} <= set(FROZEN_QUOTE_COLUMNS)
    for col in FROZEN_QUOTE_COLUMNS:
        assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in SQL


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_history_tables_are_append_only(table):
    name = f"quo_{table}"
    assert f"BEFORE UPDATE OR DELETE ON erp.{name}" in SQL and f"BEFORE TRUNCATE ON erp.{name}" in SQL


def test_the_number_rpc_is_service_role_only():
    assert "REVOKE ALL ON FUNCTION erp.quo_next_number(UUID) FROM PUBLIC, anon, authenticated" in SQL
    assert "GRANT EXECUTE ON FUNCTION erp.quo_next_number(UUID) TO service_role" in SQL
    assert "SECURITY DEFINER" in SQL and "SET search_path = pg_catalog, erp, pg_temp" in SQL


@pytest.mark.parametrize(
    "enum_cls, table, column",
    [(QuoteStatus, "quotes", "status"), (ConvertTo, "quotes", "convert_to"), (ConversionStatus, "quotes", "conversion_status"),
     (LineKind, "lines", "kind"), (Decision, "acceptances", "decision"), (Channel, "acceptances", "channel"),
     (EventKind, "events", "kind")],
)
def test_enum_values_are_pinned_in_the_checks(enum_cls, table, column):
    block = _block(f"quo_{table}")
    match = re.search(rf"{column}\s+TEXT[^\n]*?IN \(([^)]*)\)", block)
    assert match, column
    assert tuple(v.strip().strip("'") for v in match.group(1).split(",")) == values(enum_cls)


def test_wire_vocabulary_is_stable():
    assert values(QuoteStatus) == ("draft", "sent", "viewed", "accepted", "rejected", "expired", "superseded")
    assert values(ConvertTo) == ("order", "contract", "none")


def test_statements_are_re_runnable():
    assert "CREATE TABLE IF NOT EXISTS" in SQL and "CREATE TABLE erp" not in SQL
    assert not re.findall(r"CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", SQL)
    assert SQL.count("CREATE POLICY") == SQL.count("DROP POLICY IF EXISTS")  # every policy is dropped before it is created
    assert SQL.count("DROP TRIGGER IF EXISTS") == SQL.count("CREATE TRIGGER")


@pytest.mark.parametrize(
    "kwargs",
    [{"schema": "Bad-Schema"}, {"schema": "erp", "table_prefix": "A_"}, {"schema": "erp", "currency": "brl"},
     {"schema": "erp", "number_pad": 0}, {"schema": "erp", "default_valid_days": 0}, {"schema": "erp", "org_id_expr": " "},
     {"schema": "erp", "number_prefix": "THIS-IS-WAY-TOO-LONG"}, {"schema": "erp", "utc_offset_hours": 99}],
)
def test_config_validates(kwargs):
    with pytest.raises(ValueError):
        QuotesConfig(**kwargs)


def test_number_format():
    assert CFG.format_number(42) == "ORC-00042"
    assert QuotesConfig(schema="erp", number_prefix="", number_pad=3).format_number(7) == "007"
