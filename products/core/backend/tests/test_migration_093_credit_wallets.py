"""Static checks for core's prepaid AI credit wallet migration (093).

No live database here: the SQL is asserted structurally. Behaviour (append-only,
the GUC carve-out, double-debit refusal, the balance guard) is executed against
production by `noctus.dev.verify_db_guards` (credit_* probes)."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
SQL = migration_sql(ROOT / "products/core/backend/migrations", "credit_wallets")
FLAT = " ".join(SQL.split())
APPLY = SQL[SQL.index("CREATE OR REPLACE FUNCTION public.credit_apply_entry("):SQL.index("-- ── 7. access")]
TABLES = ("credit_pricing", "credit_wallets", "credit_entries", "credit_purchases")


def test_tables_are_idempotent_and_rls_enabled():
    for t in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS public.{t}" in FLAT
        assert f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY" in FLAT


def test_apply_function_is_the_only_writer_serialised_per_org():
    assert "SECURITY DEFINER" in APPLY
    assert "SET search_path = public, pg_temp" in APPLY
    assert "pg_advisory_xact_lock(hashtextextended('credit_wallet:' || p_org_id::text, 0))" in APPLY
    assert "set_config('noctus.credit_wallet_write', 'on', true)" in APPLY
    assert re.search(r"REVOKE ALL ON FUNCTION public\.credit_apply_entry\(.*?\) FROM PUBLIC, anon, authenticated",
                     FLAT)
    assert re.search(r"GRANT EXECUTE ON FUNCTION public\.credit_apply_entry\(.*?\) TO service_role", FLAT)


def test_debits_and_payments_are_unique():
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_entries_ai_usage" in FLAT
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_entries_payment" in FLAT


def test_entries_are_never_written_directly():
    assert "GRANT SELECT ON public.credit_entries TO service_role" in FLAT
    assert "guard_credit_entries_append_only" in FLAT
    assert "guard_credit_wallet_balance" in FLAT
    assert "guard_credit_pricing_insert_only" in FLAT


def test_authenticated_reads_only_and_never_writes():
    assert re.search(r"GRANT SELECT ON public\.credit_pricing, public\.credit_wallets, public\.credit_entries, "
                     r"public\.credit_purchases TO authenticated", FLAT)
    assert not re.search(r"GRANT (INSERT|UPDATE|DELETE)[^;]* TO authenticated", FLAT)


def test_seeded_pricing_v1_is_present():
    assert "INSERT INTO public.credit_pricing" in FLAT
    assert "ON CONFLICT" in FLAT[FLAT.index("INSERT INTO public.credit_pricing"):]
