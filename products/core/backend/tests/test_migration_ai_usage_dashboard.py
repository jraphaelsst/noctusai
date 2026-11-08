"""Migration 112 (AI usage dashboard): platform tier, RLS on with NO policy, no browser grant, replace-window
functions not executable by PUBLIC/anon/authenticated, additive-only on dev_telemetry_claude."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql

MIG = Path(__file__).resolve().parents[1] / "migrations"
SQL = migration_sql(MIG, "ai_usage_dashboard")
FLAT = " ".join(SQL.split())
NEW_TABLES = ["ai_anthropic_usage_daily", "ai_anthropic_cost_daily", "ai_anthropic_rate_limits",
              "ai_source_sync_runs", "dev_deliveries"]


@pytest.mark.parametrize("table", NEW_TABLES)
def test_table_is_platform_tier_rls_on_revoked_and_has_no_policy(table):
    assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in FLAT
    assert re.search(rf"REVOKE ALL ON public\.{table}\s+FROM PUBLIC, anon, authenticated", FLAT)
    assert f"COMMENT ON TABLE public.{table} IS 'tier:platform'" in FLAT


def test_no_policy_and_no_grant_to_browser_roles():
    assert "CREATE POLICY" not in SQL.upper()
    assert not re.search(r"GRANT\s+[^;]*\bTO\s+[^;]*\b(anon|authenticated)\b", SQL, re.I)


def test_replace_window_functions_are_service_role_only():
    for fn in ("ai_replace_anthropic_usage_window", "ai_replace_anthropic_cost_window", "ai_replace_anthropic_rate_limits"):
        assert re.search(rf"REVOKE ALL ON FUNCTION public\.{fn}\([^)]*\)\s+FROM PUBLIC, anon, authenticated", FLAT)
        assert re.search(rf"GRANT EXECUTE ON FUNCTION public\.{fn}\([^)]*\)\s+TO service_role", FLAT)
    assert "SECURITY DEFINER" not in SQL.upper()


def test_cost_is_decimal_cents_usd_only_and_dev_columns_are_additive():
    assert "amount_cents        numeric(20,6)" in SQL and "CHECK (currency = 'USD')" in SQL
    alters = re.findall(r"ALTER TABLE public\.dev_telemetry_claude\s+ADD COLUMN IF NOT EXISTS (\w+) text NOT NULL DEFAULT '(\w+)'", SQL)
    assert alters == [("ambiente", "local"), ("origem", "desconhecido")]
    assert "DROP " not in SQL.upper().replace("DROP POLICY", "")
