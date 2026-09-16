"""Structural tests for `050_billing_gateways.sql` (no database needed).

The load-bearing assertions are the legacy backfill ones: every license
that exists at apply time becomes `source='legacy'`, the migration aborts
if the backfilled count differs from the pre-count, and the verification
queries the operator runs around the apply are in the file.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.sql import service_role_bypass

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "050_billing_gateways.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code
    assert "TRUNCATE" not in code
    assert not re.search(r"\bDELETE\s+FROM\b", code)


def test_only_number_050_in_this_file_name():
    siblings = [p.name for p in MIGRATION.parent.glob("050_*.sql")]
    assert siblings == [MIGRATION.name]


# ── licenses.source legacy backfill ────────────────────────────────────


def test_source_column_is_added_without_a_default_before_the_backfill(code: str):
    add = code.index("ADD COLUMN IF NOT EXISTS source TEXT;")
    backfill = code.index("UPDATE public.licenses SET source = 'legacy' WHERE source IS NULL")
    default = code.index("ALTER COLUMN source SET DEFAULT 'manual'")
    not_null = code.index("ALTER COLUMN source SET NOT NULL")
    # Pre-existing rows are NULL right after the ADD, so the backfill sees all
    # of them; the default/NOT NULL come only afterwards.
    assert add < backfill < default < not_null


def test_backfill_asserts_count_equals_pre_count(flat: str):
    assert "SELECT count(*) INTO v_pre FROM public.licenses WHERE source IS NULL;" in flat
    assert "GET DIAGNOSTICS v_updated = ROW_COUNT;" in flat
    assert "IF v_updated <> v_pre THEN RAISE EXCEPTION" in flat


def test_every_existing_license_becomes_legacy_no_status_filter(flat: str):
    # The backfill must not be narrowed to active rows: revoked/expired
    # history is legacy too.
    match = re.search(r"UPDATE public\.licenses SET source = 'legacy' WHERE ([^;]+);", flat)
    assert match and match.group(1).strip() == "source IS NULL"


def test_verification_queries_are_documented(sql: str):
    assert "pre_total" in sql and "pre_active" in sql
    assert "legacy_total = pre_total" in sql
    assert "legacy_active = pre_active" in sql
    assert "non_legacy = 0" in sql


def test_source_values_are_constrained(flat: str):
    assert "CHECK (source IN ('legacy', 'manual', 'subscription'))" in flat


# ── subscriptions ──────────────────────────────────────────────────────


def test_subscription_status_check_is_widened(flat: str):
    assert (
        "CHECK (status IN ('active', 'canceled', 'expired', 'trial', 'past_due', 'grace', 'incomplete'))"
        in flat
    )


def test_existing_subscriptions_stay_outside_the_automations(flat: str):
    assert "ADD COLUMN IF NOT EXISTS automation_managed BOOLEAN NOT NULL DEFAULT false" in flat
    # The legacy Stripe mirror update must not flip the flag.
    mirror = re.search(r"UPDATE public\.subscriptions SET (.+?) WHERE", flat)
    assert mirror and "automation_managed" not in mirror.group(1)


@pytest.mark.parametrize(
    "column",
    [
        "gateway", "gateway_mode", "gateway_subscription_id", "gateway_customer_id",
        "plan_price_id", "billing_cycle", "billing_method", "currency", "amount_cents",
        "current_period_start", "current_period_end", "trial_ends_at", "grace_ends_at",
        "past_due_since", "cancel_at_period_end", "payment_url",
    ],
)
def test_subscription_gateway_columns(flat: str, column: str):
    assert f"ALTER TABLE public.subscriptions ADD COLUMN IF NOT EXISTS {column} " in flat


def test_plans_columns(flat: str):
    for column in ("product_id", "audience", "trial_days", "grace_days"):
        assert f"ALTER TABLE public.plans ADD COLUMN IF NOT EXISTS {column} " in flat


# ── new tables ─────────────────────────────────────────────────────────


def test_payment_events_unique_gateway_event_id(flat: str):
    assert "CREATE TABLE IF NOT EXISTS public.payment_events" in flat
    assert "CONSTRAINT payment_events_gateway_event_id_key UNIQUE (gateway, event_id)" in flat


def test_payment_events_accepts_the_seed_inbox_insert(flat: str):
    # RealSupabaseEventInbox inserts only (gateway, event_id, claimed_at):
    # every other NOT NULL column needs a default.
    body = re.search(r"CREATE TABLE IF NOT EXISTS public\.payment_events \((.+?)\);", flat).group(1)
    for column in re.findall(r"(\w+) [A-Z]+[^,]*NOT NULL(?![^,]*DEFAULT)", body):
        assert column in {"gateway", "event_id"}, f"{column} is NOT NULL without a default"


def test_billing_payments_fee_invariant(flat: str):
    assert "CHECK (gross_cents = fee_cents + net_cents)" in flat
    assert "CONSTRAINT billing_payments_gateway_payment_key UNIQUE (gateway, gateway_payment_id)" in flat


def test_billing_customers_unique_per_org_gateway_mode(flat: str):
    assert "UNIQUE (org_id, gateway, gateway_mode)" in flat


def test_plan_prices_one_active_price_per_cycle(flat: str):
    assert "ON public.plan_prices (plan_id, billing_cycle, currency) WHERE ativo" in flat


def test_app_integration_config_is_service_role_only(flat: str):
    assert "encrypted_value TEXT NOT NULL" in flat
    assert not re.search(r"ON public\.app_integration_config\s+FOR SELECT TO authenticated", flat)


@pytest.mark.parametrize(
    "table",
    ["plan_prices", "billing_customers", "payment_events", "billing_payments",
     "app_integration_config", "storage_usage_snapshots"],
)
def test_rls_and_canonical_service_role_bypass(flat: str, table: str):
    assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in flat
    canonical = " ".join(service_role_bypass(table, schema="public").split())
    for statement in [s.strip() for s in canonical.split(";") if s.strip()]:
        assert statement in flat, statement


def test_storage_rpc_is_service_role_only(flat: str):
    assert "CREATE OR REPLACE FUNCTION public.storage_usage_by_prefix()" in flat
    assert "REVOKE ALL ON FUNCTION public.storage_usage_by_prefix() FROM anon, authenticated;" in flat
    assert "GRANT EXECUTE ON FUNCTION public.storage_usage_by_prefix() TO service_role;" in flat


def test_platform_settings_default_everything_off(flat: str):
    assert "('billing_automations_enabled', 'false'" in flat
    assert "('billing_gateway_mode', 'test'" in flat
    assert "('billing_stripe_enabled', 'false'" in flat
    assert "('billing_asaas_enabled', 'false'" in flat
    assert "ON CONFLICT (key) DO NOTHING" in flat
