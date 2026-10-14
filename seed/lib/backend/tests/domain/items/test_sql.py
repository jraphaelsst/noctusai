"""`items_migration` -- snapshot, structure, RLS on every table, enum parity, re-runnable text."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from noctusai_lib.domain.items import ITEMS_TABLES, ItemsConfig, items_migration
from noctusai_lib.domain.items.types import ItemType, Unit, values
from noctusai_lib.testing.migration_parser import parse_sql

SNAPSHOT = Path(__file__).parent / "snapshots" / "items_migration.sql"
CFG = ItemsConfig(schema="erp")
SQL = items_migration(CFG)

#: The model, written out independently of the generator (unprefixed table names).
EXPECTED_COLUMNS = {
    "item_categories": {"id", "org_id", "parent_id", "name", "is_active", "created_at", "updated_at"},
    "items": {
        "id", "org_id", "sku", "name", "description", "item_type", "unit", "category_id", "ncm", "cest",
        "cfop_default", "origem", "gtin", "cost_cents", "price_cents", "weight_g", "length_mm", "width_mm",
        "height_mm", "is_active", "created_at", "updated_at",
    },
}


def _block(table: str, sql: str = SQL, schema: str = "erp") -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {schema}\.{table} \((.*?)\n\);", sql, re.S)
    assert match, f"{table} not emitted"
    return match.group(1)


def test_snapshot_is_current():
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(SQL)
    assert SNAPSHOT.read_text() == SQL, "items_migration output changed: regenerate with UPDATE_SNAPSHOTS=1 and REVIEW the diff"


def test_generator_is_deterministic_schema_and_prefix_parametric():
    assert items_migration(CFG) == SQL
    other = items_migration(ItemsConfig(schema="igig", table_prefix="it_"))
    assert "igig.it_items" in other and "erp.itm_items" not in other
    assert re.search(r"REFERENCES igig\.it_item_categories \(org_id, id\)", other)


def test_every_table_is_emitted_and_columns_match_the_model():
    emitted = set(re.findall(r"CREATE TABLE IF NOT EXISTS erp\.(\w+) \(", SQL))
    assert {f"itm_{t}" for t in ITEMS_TABLES} == emitted and set(EXPECTED_COLUMNS) == set(ITEMS_TABLES)
    parsed = parse_sql(SQL, source_label="items_migration")
    for table, want in EXPECTED_COLUMNS.items():
        assert {c.lower() for c in parsed[f"erp.itm_{table}"]} == want


def test_no_stock_columns_live_in_items():
    assert not re.search(r"stock|quantity|qty|balance|reserved", _block("itm_items"), re.I)


@pytest.mark.parametrize("table", ITEMS_TABLES)
def test_every_table_is_org_scoped_with_rls(table):
    name = f"itm_{table}"
    assert re.search(r"\borg_id\s+UUID NOT NULL", _block(name))
    assert f"ALTER TABLE erp.{name} ENABLE ROW LEVEL SECURITY" in SQL
    assert f'"{name}_select_own_org"' in SQL and f'DROP POLICY IF EXISTS "{name}_select_own_org"' in SQL
    assert re.search(rf'CREATE POLICY "service_role_bypass"\s+ON erp\.{name}\b', SQL)
    # No authenticated WRITE policy anywhere: the backend writes through the service role.
    assert not re.search(rf"ON erp\.{name}\s+FOR (INSERT|UPDATE|DELETE)", SQL)


def test_org_id_expr_defaults_to_org_picker_aware_function_and_is_overridable():
    assert "org_id = (SELECT public.current_org_id_for('erp'))" in SQL
    custom = items_migration(ItemsConfig(schema="erp", org_id_expr="public.current_org_id()"))
    assert "org_id = (SELECT public.current_org_id())" in custom


def test_enum_checks_match_the_python_enums_and_the_vertical_seam():
    block = _block("itm_items")
    for col, vals in (("item_type", values(ItemType)), ("unit", values(Unit))):
        found = re.search(col + r"\s+TEXT[^,\n]*CHECK \(" + col + r" IN \(([^)]*)\)\)", block)
        assert found and tuple(re.findall(r"'([^']+)'", found.group(1))) == vals
    extended = items_migration(ItemsConfig(schema="erp", extra_item_types=("procedure",)))
    assert "'asset', 'procedure')" in extended


def test_money_is_bigint_cents_and_non_negative():
    block = _block("itm_items")
    assert "cost_cents    BIGINT NOT NULL DEFAULT 0 CHECK (cost_cents >= 0)" in block
    assert "price_cents   BIGINT CHECK (price_cents >= 0)" in block


def test_cross_tenant_references_are_refused_by_construction():
    assert "UNIQUE (org_id, id)" in _block("itm_item_categories")
    assert "FOREIGN KEY (org_id, category_id) REFERENCES erp.itm_item_categories (org_id, id)" in _block("itm_items")
    assert "FOREIGN KEY (org_id, parent_id) REFERENCES erp.itm_item_categories (org_id, id)" in _block("itm_item_categories")


@pytest.mark.parametrize("fragment", [
    r"uq_itm_items_sku ON erp\.itm_items \(org_id, lower\(sku\)\)",
    r"uq_itm_item_categories_name ON erp\.itm_item_categories\s+\(org_id, COALESCE\(parent_id, '0{8}-0{4}-0{4}-0{4}-0{12}'::uuid\), lower\(name\)\)",
])
def test_uniqueness_is_emitted(fragment):
    assert re.search(fragment, SQL), fragment


def test_migration_is_rerunnable_text():
    for stmt in re.findall(r"^CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", SQL, re.M):
        pytest.fail(f"unguarded index: {stmt}")
    assert not re.search(r"^CREATE TABLE (?!IF NOT EXISTS)", SQL, re.M)


def test_config_validation():
    for bad in (dict(schema="Bad-Schema"), dict(schema="ok", table_prefix="It-"), dict(schema="ok", org_id_expr="  "),
                dict(schema="ok", extra_item_types=("Goods",)), dict(schema="ok", extra_item_types=("service",))):
        with pytest.raises(ValueError):
            ItemsConfig(**bad)
