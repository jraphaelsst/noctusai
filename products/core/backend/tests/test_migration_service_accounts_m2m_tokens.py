"""Static checks for the service-accounts / M2M-token migration (no live DB here; the chain replay gate runs it)."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
# By name, never by number: a renumber at integrate must not break this test.
SQL = migration_sql(ROOT / "products/core/backend/migrations", "service_accounts_m2m_tokens")
FLAT = " ".join(SQL.split())


def test_service_accounts_table_is_service_role_only_like_api_tokens():
    assert "CREATE TABLE IF NOT EXISTS public.service_accounts" in FLAT
    assert "ALTER TABLE public.service_accounts ENABLE ROW LEVEL SECURITY" in FLAT
    assert "ON public.service_accounts FOR ALL TO service_role" in FLAT
    assert "TO authenticated" not in SQL and "TO anon" not in SQL


def test_api_tokens_gets_a_nullable_fk_idempotently():
    assert "ADD COLUMN IF NOT EXISTS service_account_id UUID REFERENCES public.service_accounts(id)" in FLAT
    assert "service_account_id UUID NOT NULL" not in FLAT


def test_noc_agent_is_seeded_and_the_mfa_switch_ships_off():
    assert "'noc-agent'" in SQL and "ON CONFLICT (slug) DO NOTHING" in FLAT
    assert "('exigir_mfa_para_tokens', 'false'" in FLAT and "ON CONFLICT (key) DO NOTHING" in FLAT
