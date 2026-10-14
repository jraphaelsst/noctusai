"""`purchasing_migration` -- structure, RLS on every table, the guards the organ promises, config validation."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.domain.purchasing import PURCHASING_TABLES, PurchasingConfig, purchasing_migration
from noctusai_lib.domain.purchasing.types import OrderStatus, values
from noctusai_lib.testing.migration_parser import parse_sql

CFG = PurchasingConfig(schema="erp")
SQL = purchasing_migration(CFG, "erp")
BARE = purchasing_migration(PurchasingConfig(schema="erp", with_parties=False, with_items=False, with_inventory=False), "erp")


@pytest.mark.parametrize("sql", [SQL, BARE], ids=["full", "bare"])
@pytest.mark.parametrize("name", PURCHASING_TABLES)
def test_every_table_has_rls_org_policy_grants_and_service_role_bypass(name, sql):
    t = f"pur_{name}"
    assert f"ALTER TABLE erp.{t} ENABLE ROW LEVEL SECURITY;" in sql
    assert re.search(rf'CREATE POLICY "{t}_select_own_org" ON erp\.{t}\s+FOR SELECT', sql), t
    assert f'CREATE POLICY "service_role_bypass" ON erp.{t} FOR ALL TO service_role' in sql
    assert f"GRANT SELECT ON erp.{t} TO authenticated;" in sql and f"GRANT ALL ON erp.{t} TO service_role;" in sql
    assert re.search(rf"CREATE TABLE IF NOT EXISTS erp\.{t} \(.*?org_id\s+UUID", sql, re.S), f"{t} needs org_id"


def test_parser_sees_every_table_and_the_contract_columns():
    tables = parse_sql(SQL, source_label="purchasing")
    assert {f"erp.pur_{n}" for n in PURCHASING_TABLES} <= set(tables)
    assert {"number", "status", "party_id", "supplier_name", "warehouse_id", "installments_count", "first_due_days",
            "interval_days", "freight_cents", "discount_cents", "other_cents", "goods_cents", "total_cents",
            "approved_by", "approved_at"} <= tables["erp.pur_orders"]
    assert {"item_id", "qty", "unit_cost_cents", "received_qty"} <= tables["erp.pur_order_lines"]
    assert {"stock_posted_at", "finance_posted_at", "idempotency_key", "adjustment_cents"} <= tables["erp.pur_receipts"]
    assert {"landed_unit_cost_cents", "order_line_id"} <= tables["erp.pur_receipt_lines"]


def test_statuses_match_the_enum():
    assert values(OrderStatus) == ("draft", "approved", "sent", "partially_received", "received", "cancelled")
    for status in values(OrderStatus):
        assert f"'{status}'" in SQL


def test_composite_org_foreign_keys_make_cross_tenant_links_impossible():
    assert "FOREIGN KEY (party_id, org_id) REFERENCES erp.pty_parties(id, org_id)" in SQL
    assert "FOREIGN KEY (order_id, org_id) REFERENCES erp.pur_orders(id, org_id)" in SQL
    assert "FOREIGN KEY (receipt_id, org_id) REFERENCES erp.pur_receipts(id, org_id)" in SQL
    assert "FOREIGN KEY (order_line_id, org_id) REFERENCES erp.pur_order_lines(id, org_id)" in SQL
    assert "UNIQUE (org_id, number)" in SQL


def test_cross_organ_references_follow_the_with_flags():
    assert "REFERENCES erp.inv_warehouses(id)" in SQL and "REFERENCES erp.itm_items(id)" in SQL
    for needle in ("pty_parties", "inv_warehouses", "itm_items"):
        assert needle not in BARE


def test_received_quantity_is_bounded_and_money_is_cents():
    assert "received_qty <= qty" in SQL and "NUMERIC(18,3)" in SQL
    assert "total_cents       BIGINT NOT NULL" in SQL and "approval_threshold_cents BIGINT" in SQL


def test_every_secdef_function_pins_search_path_locks_the_order_and_revokes_clients():
    funcs = [f for f in re.findall(r"CREATE OR REPLACE FUNCTION erp\.(pur_\w+)\(", SQL) if not f.endswith("_append_only")]  # the audit trigger fn is not SECURITY DEFINER
    assert sorted(funcs) == ["pur_receive", "pur_save_order", "pur_set_approver", "pur_set_threshold", "pur_transition"]
    for f in funcs:
        assert re.search(rf"FUNCTION erp\.{f}\([^)]*\) FROM PUBLIC, anon, authenticated;", SQL), f
        assert re.search(rf"GRANT EXECUTE ON FUNCTION erp\.{f}\([^)]*\) TO service_role;", SQL), f
    assert SQL.count("SET search_path = pg_catalog, erp, pg_temp") == 5
    assert SQL.count("FROM erp.pur_orders WHERE id = ") >= 2 and "FOR UPDATE" in SQL


def test_the_legacy_unguarded_transition_overload_is_dropped_and_the_audit_log_is_append_only():
    assert "DROP FUNCTION IF EXISTS erp.pur_transition(UUID, UUID, TEXT, UUID, TEXT);" in SQL
    assert SQL.index("DROP FUNCTION IF EXISTS erp.pur_transition") < SQL.index("CREATE OR REPLACE FUNCTION erp.pur_transition(")
    assert "BEFORE UPDATE OR DELETE ON erp.pur_settings_log" in SQL and "BEFORE TRUNCATE ON erp.pur_settings_log" in SQL
    assert "PRIMARY KEY (org_id, user_id)" in SQL


def test_receipts_are_idempotent_by_key_and_unique_per_order():
    assert "(org_id, idempotency_key) WHERE idempotency_key IS NOT NULL" in SQL
    assert "UNIQUE (order_id, receipt_no)" in SQL


def test_generator_is_deterministic_and_validates_its_schema():
    assert purchasing_migration(CFG, "erp") == SQL
    with pytest.raises(ValueError):
        purchasing_migration(CFG, "other")
    with pytest.raises(ValueError):
        purchasing_migration(CFG, "  ")


@pytest.mark.parametrize("kw", [{"schema": "Bad-Name"}, {"schema": "erp", "table_prefix": "x-"}, {"schema": "erp", "org_id_expr": " "}])
def test_config_rejects_bad_identifiers(kw):
    with pytest.raises(ValueError):
        PurchasingConfig(**kw)
