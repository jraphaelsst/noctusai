"""Fiscal DDL generator: shape, RLS, regime CHECK, idempotence."""
from __future__ import annotations

from noctusai_lib.domain.commerce.fiscal_sql import INVOICE_TABLE, PROFILE_FISCAL_COLUMNS, commerce_fiscal_migration

from .conftest import CFG, SCHEMA


def test_deterministic_and_rls_on_invoices():
    sql = commerce_fiscal_migration(CFG, SCHEMA)
    assert sql == commerce_fiscal_migration(CFG, SCHEMA)
    assert f"ALTER TABLE {SCHEMA}.{INVOICE_TABLE} ENABLE ROW LEVEL SECURITY" in sql
    assert f"org_id = (SELECT {CFG.org_id_expr})" in sql
    assert "service_role_bypass" in sql


def test_every_profile_fiscal_column_is_added_idempotently():
    sql = commerce_fiscal_migration(CFG, SCHEMA)
    for col in PROFILE_FISCAL_COLUMNS:
        assert f"ADD COLUMN IF NOT EXISTS {col} " in sql
    assert set(PROFILE_FISCAL_COLUMNS) == {
        "inscricao_municipal", "inscricao_estadual", "municipio_ibge", "nfse_mode", "nfse_cutover",
        "invoice_company_ref", "certificate_valid_until", "certificate_cnpj", "auto_issue_invoices",
    }


def test_regime_rule_is_a_database_check():
    sql = commerce_fiscal_migration(CFG, SCHEMA)
    assert "DROP CONSTRAINT IF EXISTS commerce_store_profiles_nfse_regime_ck" in sql
    assert "tax_regime IN ('mei', 'simples') AND nfse_mode = 'municipal'" in sql


def test_ref_unique_per_org_and_seq_per_order_kind():
    sql = commerce_fiscal_migration(CFG, SCHEMA)
    assert "UNIQUE (org_id, ref)" in sql and "UNIQUE (order_id, kind, seq)" in sql


def test_reuses_the_commerce_bucket_unless_a_dedicated_one_is_asked():
    assert "storage.buckets" not in commerce_fiscal_migration(CFG, SCHEMA)
    assert "invoice-copies" in commerce_fiscal_migration(CFG, SCHEMA, bucket="invoice-copies")
