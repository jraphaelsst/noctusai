"""`contracts_migration` -- structure, RLS on every table, enum parity, composite org FKs, config validation."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.domain.contracts import CONTRACTS_TABLES, ContractsConfig, contracts_migration
from noctusai_lib.domain.contracts.types import (
    AttachmentKind, BillingFrequency, BillingKind, BillingModel, ContractStatus, ReadjustmentIndex, SignatureStatus, VersionKind,
    values,
)
from noctusai_lib.domain.finance.types import EntrySource
from noctusai_lib.testing.migration_parser import parse_sql

CFG = ContractsConfig(schema="erp", with_parties=True, with_items=True)
SQL = contracts_migration(CFG, "erp")


def _block(table: str) -> str:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS erp\.{table} \((.*?)\n\);", SQL, re.S)
    assert m, f"{table} not emitted"
    return m.group(1)


def test_every_table_is_emitted_and_listed():
    assert {f"ctr_{t}" for t in CONTRACTS_TABLES} == set(re.findall(r"CREATE TABLE IF NOT EXISTS erp\.(\w+) \(", SQL))


def test_generator_is_deterministic_and_prefix_configurable():
    assert contracts_migration(CFG, "erp") == SQL
    other = contracts_migration(ContractsConfig(schema="x", table_prefix="cx_"), "x")
    assert "x.cx_contracts" in other and "x.ctr_contracts" not in other


@pytest.mark.parametrize("table", CONTRACTS_TABLES)
def test_every_table_is_org_scoped_with_rls_and_no_write_policy(table):
    name = f"ctr_{table}"
    assert re.search(r"\borg_id\s+UUID NOT NULL", _block(name))
    assert f"ALTER TABLE erp.{name} ENABLE ROW LEVEL SECURITY" in SQL
    assert f'"{name}_select_own_org"' in SQL
    if table != "contracts":  # the doc-bearing table has no authenticated read path (see the dedicated test below)
        assert f"GRANT SELECT ON erp.{name} TO authenticated;" in SQL
    assert re.search(rf'CREATE POLICY "service_role_bypass"\s+ON erp\.{name}\b', SQL)
    assert not re.search(rf"ON erp\.{name}\s+FOR (INSERT|UPDATE|DELETE)", SQL)


@pytest.mark.parametrize("child", [t for t in CONTRACTS_TABLES if t != "contracts"])
def test_children_name_their_contract_through_a_composite_org_fk(child):
    assert "FOREIGN KEY (contract_id, org_id) REFERENCES erp.ctr_contracts(id, org_id)" in _block(f"ctr_{child}")


def test_party_and_item_links_are_composite_and_optional():
    assert "FOREIGN KEY (party_id, org_id) REFERENCES erp.pty_parties(id, org_id)" in _block("ctr_contracts")
    assert "FOREIGN KEY (org_id, item_id) REFERENCES erp.itm_items(org_id, id)" in _block("ctr_contract_lines")
    bare = contracts_migration(ContractsConfig(schema="erp"), "erp")
    assert "pty_parties" not in bare and "itm_items" not in bare


def test_money_is_integer_cents_and_percentages_basis_points():
    cols = parse_sql(SQL, source_label="x")
    assert not [c for c in cols["erp.ctr_contracts"] if c.endswith("_percent") or c in ("amount", "price")]
    assert re.search(r"amount_cents\s+BIGINT", SQL) and re.search(r"unit_price_cents\s+BIGINT", SQL)
    assert "NUMERIC" not in SQL.upper().replace("NUMERIC_", "")


@pytest.mark.parametrize("enum_cls, column", [
    (ContractStatus, "status"), (BillingModel, "billing_model"), (BillingFrequency, "frequency"),
    (ReadjustmentIndex, "readjustment_index"), (SignatureStatus, "signature_status"), (VersionKind, "kind"),
    (BillingKind, "kind"), (AttachmentKind, "kind"),
])
def test_enum_values_match_the_checks(enum_cls, column):
    literal = "(" + ", ".join(f"'{v}'" for v in values(enum_cls)) + ")"
    assert f"{column}" in SQL and f"IN {literal}" in SQL


def test_finance_source_check_is_widened_to_admit_contracts_guarded():
    assert "'contracts'" in SQL and "to_regclass('erp.fin_entries')" in SQL
    assert EntrySource.CONTRACTS.value == "contracts"
    for v in values(EntrySource):
        assert f"'{v}'" in SQL
    assert "fin_entries" not in contracts_migration(ContractsConfig(schema="erp", finance_entries_table=None), "erp")


def test_idempotent_text():
    assert "IF NOT EXISTS" in SQL and 'DROP POLICY IF EXISTS "service_role_bypass"' in SQL
    assert SQL.count("CREATE TABLE") == SQL.count("CREATE TABLE IF NOT EXISTS")


@pytest.mark.parametrize("bad", [
    dict(schema="Bad"), dict(schema="a", table_prefix="X-"), dict(schema="a", org_id_expr="  "), dict(schema="a", billing_lead_days=-1),
    dict(schema="a", bucket="Bad Bucket"), dict(schema="a", finance_entries_table="a;b"), dict(schema="a", signed_url_ttl_seconds=601),
])
def test_config_validation(bad):
    with pytest.raises(ValueError):
        ContractsConfig(**bad)


def test_empty_schema_is_refused():
    with pytest.raises(ValueError):
        contracts_migration(CFG, " ")


def test_contracts_table_has_no_authenticated_read_path_but_the_children_keep_theirs():
    """`ctr_contracts.party_doc` is a CPF/CNPJ the API masks per role; a direct `authenticated` SELECT would bypass it."""
    assert "GRANT SELECT ON erp.ctr_contracts TO authenticated" not in SQL
    assert 'CREATE POLICY "ctr_contracts_select_own_org"' not in SQL
    assert "REVOKE ALL ON erp.ctr_contracts FROM PUBLIC, anon, authenticated;" in SQL
    assert 'CREATE POLICY "ctr_contract_lines_select_own_org"' in SQL


def test_signature_envelope_is_unique_across_orgs():
    """The webhook finds the contract by `(provider, external_id)` with no org in the call: the pair must be unambiguous."""
    assert re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS uq_ctr_contracts_signature ON erp\.ctr_contracts "
        r"\(signature_provider, signature_external_id\) WHERE signature_external_id IS NOT NULL;", SQL)
