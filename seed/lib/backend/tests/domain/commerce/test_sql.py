"""`commerce_migration` -- snapshot, structure, and CONTRACT §2 column parity."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from noctusai_lib.domain.commerce import COMMERCE_TABLES, APPEND_ONLY_TABLES, CommerceConfig, commerce_migration
from noctusai_lib.testing.migration_parser import parse_sql

SNAPSHOT = Path(__file__).parent / "snapshots" / "commerce_migration.sql"
CFG = CommerceConfig(schema="commerce")
SQL = commerce_migration(CFG, "commerce")

#: CONTRACT §2 key columns, written out independently of the generator.
CONTRACT_COLUMNS = {
    "commerce_store_profiles": {
        "org_id", "version", "legal_name", "trade_name", "cnpj", "tax_regime", "tax_treatment", "locale",
        "currency", "brand_tokens", "address", "contact_email", "contact_phone", "platform_fee_bps",
        "updated_at", "updated_by",
    },
    "commerce_store_profile_versions": {"org_id", "version", "snapshot", "changed_by", "changed_at"},
    "commerce_storefront_hosts": {"hostname", "org_id", "is_primary"},
    "commerce_categories": {"id", "org_id", "slug", "name", "parent_id", "position"},
    "commerce_products": {
        "id", "org_id", "slug", "title", "description", "product_type", "fulfillment_type", "status",
        "category_id", "attributes", "tax_treatment_override", "created_at", "updated_at",
    },
    "commerce_offers": {"id", "org_id", "product_id", "name", "price_cents", "currency", "active", "position"},
    "commerce_media": {"id", "org_id", "product_id", "storage_path", "kind", "alt", "position"},
    "commerce_coupons": {
        "id", "org_id", "code", "kind", "value", "starts_at", "ends_at", "max_uses", "uses_count", "active",
    },
    "commerce_customers": {
        "id", "org_id", "email", "name", "doc", "phone", "address", "field_sources", "anonymized_at",
        "created_at", "updated_at",
    },
    "commerce_consents": {"id", "org_id", "customer_id", "order_id", "kind", "version", "granted", "ip", "user_agent", "at"},
    "commerce_privacy_requests": {
        "id", "org_id", "customer_id", "kind", "status", "verified_at", "created_at", "resolved_at",
    },
    "commerce_orders": {
        "id", "org_id", "token", "customer_id", "status", "subtotal_cents", "discount_cents", "total_cents",
        "currency", "coupon_id", "payment_method", "gateway", "gateway_charge_id", "checkout_url", "pix_qr",
        "expires_at", "paid_at", "platform_fee_cents", "created_at", "updated_at",
    },
    "commerce_order_items": {
        "id", "org_id", "order_id", "product_id", "offer_id", "title_snapshot", "product_type",
        "fulfillment_type", "unit_price_cents", "qty", "total_cents",
    },
    "commerce_order_events": {"id", "org_id", "order_id", "from_status", "to_status", "reason", "source", "at"},
}


def _table_block(table: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS commerce\.{table} \((.*?)\n\);", SQL, re.S)
    assert match, f"{table} not emitted"
    return match.group(1)


def test_snapshot_is_current():
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.write_text(SQL)
    assert SNAPSHOT.read_text() == SQL, "commerce_migration output changed: regenerate with UPDATE_SNAPSHOTS=1 and REVIEW the diff"


def test_generator_is_deterministic_and_schema_parametric():
    assert commerce_migration(CFG, "commerce") == SQL
    other = commerce_migration(CommerceConfig(schema="foto"), "foto")
    assert "foto.commerce_orders" in other and "commerce.commerce_orders" not in other


def test_every_contract_table_is_emitted_and_listed():
    emitted = set(re.findall(r"CREATE TABLE IF NOT EXISTS commerce\.(\w+) \(", SQL))
    assert set(COMMERCE_TABLES) <= emitted
    assert set(CONTRACT_COLUMNS) == set(COMMERCE_TABLES)
    assert {"credentials", "payment_gateway_events"} <= emitted
    assert emitted == set(COMMERCE_TABLES) | {"credentials", "payment_gateway_events"}


@pytest.mark.parametrize("table", COMMERCE_TABLES)
def test_every_commerce_table_has_org_id_and_rls_with_policies(table):
    assert re.search(r"\n\s+org_id\s+UUID", _table_block(table)), f"{table} lacks org_id"
    assert f"ALTER TABLE commerce.{table} ENABLE ROW LEVEL SECURITY;" in SQL
    assert f'CREATE POLICY "{table}_select_own_org" ON commerce.{table} FOR SELECT TO authenticated' in SQL
    assert f'CREATE POLICY "service_role_bypass" ON commerce.{table} FOR ALL TO service_role' in SQL


def test_credentials_table_is_org_scoped_with_rls():
    assert re.search(r"CREATE TABLE IF NOT EXISTS commerce\.credentials \(.*?org_id UUID NOT NULL", SQL, re.S)
    assert "ALTER TABLE commerce.credentials ENABLE ROW LEVEL SECURITY;" in SQL


def test_event_inbox_is_deny_all_to_authenticated():
    assert "ALTER TABLE commerce.payment_gateway_events ENABLE ROW LEVEL SECURITY;" in SQL
    assert "payment_gateway_events_select" not in SQL


def test_no_authenticated_write_policy_exists_anywhere():
    for match in re.finditer(r'CREATE POLICY "[^"]+" ON commerce\.\w+ FOR (\w+) TO authenticated', SQL):
        assert match.group(1) == "SELECT", match.group(0)


def test_migration_is_rerunnable():
    assert not re.search(r"CREATE TABLE (?!IF NOT EXISTS)", SQL)
    assert not re.search(r"CREATE (UNIQUE )?INDEX (?!IF NOT EXISTS)", SQL)
    for name, table in re.findall(r'CREATE POLICY "([^"]+)" ON ([\w.]+) ', SQL):
        assert f'DROP POLICY IF EXISTS "{name}" ON {table};' in SQL, name


@pytest.mark.parametrize("table", COMMERCE_TABLES)
def test_columns_cover_the_contract(table):
    parsed = parse_sql(SQL, source_label="commerce_migration")[f"commerce.{table}"]
    assert CONTRACT_COLUMNS[table] <= parsed, CONTRACT_COLUMNS[table] - parsed


def test_money_is_integer_cents_and_prices_are_positive():
    assert "price_cents INTEGER NOT NULL CHECK (price_cents > 0)" in SQL
    assert not re.search(r"(?i)\b(price|total|subtotal|discount|fee)\w*\s+(NUMERIC|DECIMAL|FLOAT|REAL|DOUBLE)", SQL)


def test_uniques_the_services_rely_on():
    assert "UNIQUE (org_id, slug)" in SQL  # categories + products
    assert "UNIQUE (org_id, email)" in SQL
    assert re.search(r"token\s+TEXT NOT NULL UNIQUE", SQL)
    assert "uq_commerce_coupons_org_code ON commerce.commerce_coupons (org_id, lower(code))" in SQL
    assert "PRIMARY KEY (org_id, version)" in SQL  # the 409 guard of the profile ledger
    assert "hostname    TEXT PRIMARY KEY" in SQL


def test_enum_checks_come_from_the_enums():
    assert "'print_on_demand'" in SQL and "'chargeback'" in SQL and "'immediate_delivery_waiver'" in SQL


def test_private_bucket_with_per_org_object_rls():
    assert "VALUES ('commerce-media', 'commerce-media', false)" in SQL
    assert "(storage.foldername(name))[1] = (SELECT public.current_org_id())::text" in SQL


def test_append_only_tables_are_a_subset_of_the_tables():
    assert set(APPEND_ONLY_TABLES) <= set(COMMERCE_TABLES)


def test_blank_schema_is_refused():
    with pytest.raises(ValueError):
        commerce_migration(CFG, " ")


def test_config_validation():
    with pytest.raises(ValueError):
        CommerceConfig(schema="Bad Schema")
    with pytest.raises(ValueError):
        CommerceConfig(schema="x", order_path_template="/pedido")
    with pytest.raises(ValueError):
        CommerceConfig(schema="x", bucket="Bad Bucket!")
