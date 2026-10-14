"""`inventory_migration` -- structure, RLS on every table, the guards the organ promises, config validation."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.domain.inventory import APPEND_ONLY_TABLES, INVENTORY_TABLES, InventoryConfig, inventory_migration
from noctusai_lib.domain.inventory.types import MoveKind, values
from noctusai_lib.testing.migration_parser import parse_sql

CFG = InventoryConfig(schema="erp")
SQL = inventory_migration(CFG, "erp")


@pytest.mark.parametrize("name", INVENTORY_TABLES)
def test_every_table_has_rls_org_policy_and_service_role_bypass(name):
    t = f"inv_{name}"
    assert f"ALTER TABLE erp.{t} ENABLE ROW LEVEL SECURITY;" in SQL
    assert re.search(rf'CREATE POLICY "{t}_select_own_org" ON erp\.{t}\s+FOR SELECT', SQL), t
    assert "public.current_org_id_for('erp')" in SQL
    assert f'ON erp.{t}' in SQL and "service_role_bypass" in SQL
    assert re.search(rf"CREATE TABLE IF NOT EXISTS erp\.{t} \(.*?org_id\s+UUID NOT NULL", SQL, re.S), f"{t} needs org_id"


def test_parser_sees_every_table_and_the_kardex_columns():
    tables = parse_sql(SQL, source_label="inventory")
    assert {f"erp.inv_{n}" for n in INVENTORY_TABLES} <= set(tables)
    assert {"seq", "on_hand_after", "reserved_after", "avg_cost_after_cents", "source", "source_ref", "transfer_group"} <= tables["erp.inv_stock_moves"]
    assert {"on_hand", "reserved", "avg_cost_cents"} <= tables["erp.inv_stock_balances"]


def test_balance_checks_and_quantity_precision():
    assert "CHECK (on_hand - reserved >= 0)" in SQL.replace("CONSTRAINT inv_stock_balances_available_nonneg ", "")
    assert "reserved >= 0" in SQL
    assert "NUMERIC(18,3)" in SQL and "qty                   NUMERIC(18,3)" in SQL


def test_kardex_is_append_only_and_idempotent_by_key():
    assert APPEND_ONLY_TABLES == ("stock_moves",)
    assert "BEFORE UPDATE OR DELETE ON erp.inv_stock_moves" in SQL and "BEFORE TRUNCATE ON erp.inv_stock_moves" in SQL
    assert "(org_id, source, source_ref, kind, item_id, warehouse_id) WHERE source_ref IS NOT NULL" in SQL


def test_kinds_match_the_enum():
    assert values(MoveKind) == ("in", "out", "adjust", "transfer_in", "transfer_out", "reserve", "release", "commit")
    for kind in values(MoveKind):
        assert f"'{kind}'" in SQL


def test_every_secdef_function_pins_search_path_and_revokes_clients():
    funcs = re.findall(r"CREATE OR REPLACE FUNCTION erp\.(inv_\w+)\(", SQL)
    secdef = [f for f in funcs if f != "inv_stock_moves_append_only"]
    assert len(secdef) == 9
    for f in secdef:
        assert re.search(rf"FUNCTION erp\.{f}\([^)]*\) FROM PUBLIC, anon, authenticated;", SQL), f
        assert re.search(rf"GRANT EXECUTE ON FUNCTION erp\.{f}\([^)]*\) TO service_role;", SQL), f
    assert SQL.count("SET search_path = pg_catalog, erp, pg_temp") == 10
    assert "SELECT * INTO v_bal FROM erp.inv_stock_balances" in SQL and "FOR UPDATE" in SQL


def test_average_cost_only_never_lifo():
    assert "avg_cost_cents" in SQL
    assert "lifo" not in SQL.lower() and "fifo" not in SQL.lower()


def test_with_items_toggles_the_fk_and_the_org_check():
    assert "REFERENCES erp.itm_items(id)" in SQL and "itm_items WHERE id = p_item AND org_id = p_org" in SQL
    off = inventory_migration(InventoryConfig(schema="erp", with_items=False), "erp")
    assert "itm_items" not in off


def test_custom_prefix_and_org_expression():
    cfg = InventoryConfig(schema="x", table_prefix="stk_", org_id_expr="public.my_org()")
    sql = inventory_migration(cfg, "x")
    assert "x.stk_stock_moves" in sql and "x.stk_receive(" in sql and "inv_" not in sql
    assert "public.my_org()" in sql


def test_migration_is_deterministic_and_re_runnable_shape():
    assert inventory_migration(CFG, "erp") == SQL
    assert "CREATE TABLE IF NOT EXISTS" in SQL and "DROP TRIGGER IF EXISTS" in SQL and "CREATE OR REPLACE FUNCTION" in SQL


@pytest.mark.parametrize("kw", [{"schema": "Bad-Schema"}, {"schema": "ok", "table_prefix": "Inv"}, {"schema": "ok", "org_id_expr": "  "}])
def test_config_validation(kw):
    with pytest.raises(ValueError):
        InventoryConfig(**kw)


def test_schema_must_match_config():
    with pytest.raises(ValueError):
        inventory_migration(CFG, "other")
    with pytest.raises(ValueError):
        inventory_migration(CFG, " ")
