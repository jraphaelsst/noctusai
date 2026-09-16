"""Structural (parse-based) tests for `046_permissions_fx_cost_ledger.sql`.

No database required — reads the migration as text and asserts the
structural elements the seed's `noctusai_lib.domain.permissions.repo` /
`noctusai_lib.integrations.fx.types` / `cost_ledger`'s fx_pending contract
rely on. Parity with `products/social-wiring/backend/tests/
test_migration_114_termos_negocio.py`'s fixture shape.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "046_permissions_fx_cost_ledger.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


# ─── 1. user_permission_grants + has_permission() ──────────────────────────


def test_user_permission_grants_shape_matches_the_seed_docstring(flat: str):
    assert "CREATE TABLE IF NOT EXISTS public.user_permission_grants" in flat
    assert "user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE" in flat
    assert "permission TEXT NOT NULL" in flat
    assert "UNIQUE (user_id, permission)" in flat


def test_has_permission_signature_matches_repo_py(flat: str):
    # Byte-shape verified against
    # noctusai_lib.domain.permissions.repo.RealSupabasePermissionGrantRepository's
    # docstring.
    assert "CREATE OR REPLACE FUNCTION public.has_permission(" in flat
    assert "p_user_id UUID," in flat
    assert "p_permission TEXT" in flat
    assert "RETURNS BOOLEAN" in flat
    assert "LANGUAGE sql STABLE SECURITY DEFINER" in flat
    assert "WHERE user_id = p_user_id AND permission = p_permission" in flat


def test_user_permission_grants_rls_is_own_row_or_platform_admin(flat: str):
    assert "ALTER TABLE public.user_permission_grants ENABLE ROW LEVEL SECURITY" in flat
    assert "USING (user_id = (SELECT auth.uid()))" in flat
    assert "USING (public.is_platform_admin())" in flat
    assert 'CREATE POLICY "service_role_bypass" ON public.user_permission_grants' in flat


# ─── 2. fx_rates ─────────────────────────────────────────────────────────


def test_fx_rates_shape_matches_ptax_rate(flat: str):
    assert "CREATE TABLE IF NOT EXISTS public.fx_rates" in flat
    assert "pair TEXT NOT NULL DEFAULT 'USD/BRL'" in flat
    assert "quote_date DATE NOT NULL" in flat
    assert "rate NUMERIC(12, 5) NOT NULL CHECK (rate > 0)" in flat
    assert "bulletin_at TIMESTAMPTZ NOT NULL" in flat
    assert "source TEXT NOT NULL" in flat
    assert "UNIQUE (pair, quote_date)" in flat


def test_fx_rates_is_readable_but_service_role_writes(flat: str):
    assert "ALTER TABLE public.fx_rates ENABLE ROW LEVEL SECURITY" in flat
    assert 'CREATE POLICY "fx_rates_select_authenticated" ON public.fx_rates' in flat
    assert "FOR SELECT TO authenticated" in flat
    assert 'CREATE POLICY "service_role_bypass" ON public.fx_rates' in flat


# ─── 3. cost_ledger ─────────────────────────────────────────────────────


def test_cost_ledger_columns(flat: str):
    assert "CREATE TABLE IF NOT EXISTS public.cost_ledger" in flat
    for col in (
        "org_id UUID NOT NULL",
        "category TEXT NOT NULL",
        "amount_native NUMERIC(14, 6) NOT NULL",
        "currency TEXT NOT NULL",
        "fx_rate NUMERIC(12, 5)",
        "fx_quote_date DATE",
        "amount_brl NUMERIC(14, 6)",
        "fx_pending BOOLEAN NOT NULL DEFAULT false",
    ):
        assert col in flat, col


def test_cost_ledger_fx_pending_check_forbids_half_resolved_rows(flat: str):
    """The CHECK must make the half-resolved state (e.g. amount_brl set
    but fx_rate NULL) structurally impossible — never merely
    discouraged."""
    assert "CHECK (" in flat
    # BRL-native branch: no pending, amount_brl equals amount_native, no
    # fx metadata.
    assert "(currency = 'BRL' AND fx_pending = false AND amount_brl = amount_native" in flat
    # Foreign-currency pending branch: nothing resolved yet.
    assert (
        "(currency <> 'BRL' AND fx_pending = true "
        "AND amount_brl IS NULL AND fx_rate IS NULL AND fx_quote_date IS NULL)"
    ) in flat
    # Foreign-currency resolved branch: everything present.
    assert (
        "(currency <> 'BRL' AND fx_pending = false "
        "AND amount_brl IS NOT NULL AND fx_rate IS NOT NULL AND fx_quote_date IS NOT NULL)"
    ) in flat


def test_cost_ledger_never_uses_a_silent_fallback_rate(code: str):
    """`code` strips comment lines — the header legitimately QUOTES the
    plan's `LLM_USD_TO_BRL` rule as rationale; only the actual DDL must
    never reference it (e.g. as a DEFAULT)."""
    assert "LLM_USD_TO_BRL" not in code


def test_cost_ledger_rls_scoped_by_org_and_platform_admin(flat: str):
    assert "ALTER TABLE public.cost_ledger ENABLE ROW LEVEL SECURITY" in flat
    assert "USING (org_id = public.current_org_id())" in flat
    assert 'CREATE POLICY "cost_ledger_select_platform_admin" ON public.cost_ledger' in flat
    assert 'CREATE POLICY "service_role_bypass" ON public.cost_ledger' in flat


def test_cost_ledger_has_fx_pending_backfill_index(flat: str):
    assert "CREATE INDEX IF NOT EXISTS ix_cost_ledger_fx_pending" in flat
    assert "WHERE fx_pending = true" in flat


# ─── numbering ──────────────────────────────────────────────────────────


def test_header_explains_the_045_renumbering(sql: str):
    """Core 045 is a HELD file (noctusai-36's cutover, deliberately
    unapplied) — the header must explain why this migration is 046, not
    045, so a future reader never "fixes" the number back. Checked
    against the raw comment text (the `code`/`flat` fixtures strip
    comment lines entirely); the filename is split across a line wrap in
    the header prose, so matched as two joined fragments."""
    assert "noctusai-36" in sql
    assert "045_academia_agents_live_" in sql
    assert "scope.sql" in sql
