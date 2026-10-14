"""`parties_migration` -- structure, RLS on every table, enum parity, re-runnable text, config validation."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.domain.parties import PARTIES_TABLES, PartiesConfig, parties_migration
from noctusai_lib.domain.parties.types import PartyKind, PartyRole, values
from noctusai_lib.testing.migration_parser import parse_sql

CFG = PartiesConfig(schema="erp")
SQL = parties_migration(CFG, "erp")

CONTRACT_COLUMNS = {
    "parties": {
        "id", "org_id", "kind", "doc", "legal_name", "trade_name", "email", "phones", "address",
        "state_registration", "municipal_registration", "notes", "is_active", "created_at", "updated_at",
    },
    "party_roles": {"id", "org_id", "party_id", "role", "created_at"},
}


def _block(table: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS erp\.{table} \((.*?)\n\);", SQL, re.S)
    assert match, f"{table} not emitted"
    return match.group(1)


def test_generator_is_deterministic_and_schema_parametric():
    assert parties_migration(CFG, "erp") == SQL
    other = parties_migration(PartiesConfig(schema="igig"), "igig")
    assert "igig.pty_parties" in other and "erp.pty_parties" not in other


def test_prefix_is_configurable_and_applied_everywhere():
    sql = parties_migration(PartiesConfig(schema="x", table_prefix="px_"), "x")
    assert "x.px_parties" in sql and "x.pty_parties" not in sql
    assert re.search(r"REFERENCES x\.px_parties\(id, org_id\)", sql)


def test_every_table_is_emitted_and_listed():
    emitted = set(re.findall(r"CREATE TABLE IF NOT EXISTS erp\.(\w+) \(", SQL))
    assert {f"pty_{t}" for t in PARTIES_TABLES} == emitted
    assert set(CONTRACT_COLUMNS) == set(PARTIES_TABLES)


@pytest.mark.parametrize("table", PARTIES_TABLES)
def test_contract_columns_present(table):
    parsed = parse_sql(SQL, source_label="parties_migration")
    cols = {c.lower() for c in parsed[f"erp.pty_{table}"]}
    assert not CONTRACT_COLUMNS[table] - cols


@pytest.mark.parametrize("table", PARTIES_TABLES)
def test_every_table_is_org_scoped_with_rls(table):
    name = f"pty_{table}"
    assert re.search(r"\borg_id\s+UUID NOT NULL", _block(name)), f"{name} has no org_id"
    assert f"ALTER TABLE erp.{name} ENABLE ROW LEVEL SECURITY" in SQL
    assert f'"{name}_select_own_org"' in SQL
    assert re.search(rf'CREATE POLICY "service_role_bypass"\s+ON erp\.{name}\b', SQL)
    assert f"GRANT SELECT ON erp.{name} TO authenticated;" in SQL
    # No authenticated WRITE policy anywhere: the backend writes through the service role.
    assert not re.search(rf"ON erp\.{name}\s+FOR (INSERT|UPDATE|DELETE)", SQL)
    assert f'DROP POLICY IF EXISTS "{name}_select_own_org"' in SQL


def test_org_id_expr_defaults_to_org_picker_aware_function_and_is_overridable():
    assert "org_id = (SELECT public.current_org_id_for('erp'))" in SQL
    custom = parties_migration(PartiesConfig(schema="erp", org_id_expr="public.current_org_id()"), "erp")
    assert "org_id = (SELECT public.current_org_id())" in custom


def test_enum_checks_match_the_python_enums():
    for table, col, enum in (("pty_parties", "kind", PartyKind), ("pty_party_roles", "role", PartyRole)):
        found = re.search(rf"{col}\s+TEXT[^,\n]*CHECK \({col} IN \(([^)]*)\)\)", _block(table))
        assert found, f"{table}.{col} CHECK missing"
        assert tuple(re.findall(r"'([^']+)'", found.group(1))) == values(enum)


@pytest.mark.parametrize(
    "fragment",
    [
        r"uq_pty_parties_doc ON erp\.pty_parties \(org_id, doc\) WHERE doc IS NOT NULL",
        r"UNIQUE \(party_id, role\)",
        r"UNIQUE \(id, org_id\)",
        r"FOREIGN KEY \(party_id, org_id\) REFERENCES erp\.pty_parties\(id, org_id\) ON DELETE CASCADE",
    ],
)
def test_uniqueness_and_tenant_fk_are_emitted(fragment):
    assert re.search(fragment, SQL), fragment


def test_no_foreign_key_outward():
    # The finance / purchasing links are composite FKs emitted by THEIR generators onto UNIQUE (id, org_id).
    assert "fin_" not in SQL


def test_migration_is_rerunnable_text():
    for stmt in re.findall(r"^CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", SQL, re.M):
        pytest.fail(f"unguarded index: {stmt}")
    assert not re.search(r"^CREATE TABLE (?!IF NOT EXISTS)", SQL, re.M)


def test_config_validation():
    with pytest.raises(ValueError):
        PartiesConfig(schema="Bad-Schema")
    with pytest.raises(ValueError):
        PartiesConfig(schema="ok", table_prefix="Pty-")
    with pytest.raises(ValueError):
        PartiesConfig(schema="ok", org_id_expr="  ")
    with pytest.raises(ValueError):
        PartiesConfig(schema="ok", reference_tables=(("fin entries", "party_id"),))
    with pytest.raises(ValueError):
        parties_migration(CFG, " ")
