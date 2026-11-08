"""Static checks for the plans/subscriptions service-only migration.

Structural only (no live DB); the core policies it drops are asserted to exist so the test cannot go
vacuous if the core schema changes."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
MIG = ROOT / "products/core/backend/migrations"
SQL = migration_sql(MIG, "plans_subscriptions_writes_service_only")
FLAT = " ".join(SQL.split())
BASE = " ".join(migration_sql(MIG, "noctusai_core").split())
SVC = " ".join(migration_sql(MIG, "service_role_bypass_backfill").split())


def test_core_schema_really_created_the_unscoped_for_all_policies():
    assert re.search(r'CREATE POLICY "plans_admin_write" ON plans FOR ALL USING', BASE)
    assert re.search(r'CREATE POLICY "subscriptions_admin_all" ON subscriptions FOR ALL USING', BASE)


def test_both_policies_are_dropped():
    assert 'DROP POLICY IF EXISTS "plans_admin_write" ON public.plans' in FLAT
    assert 'DROP POLICY IF EXISTS "subscriptions_admin_all" ON public.subscriptions' in FLAT


def test_browser_roles_lose_write_grants():
    for t in ("plans", "subscriptions"):
        assert f"REVOKE INSERT, UPDATE, DELETE ON public.{t} FROM anon, authenticated" in FLAT


def test_no_new_write_policy_for_non_service_roles():
    assert not re.search(r"CREATE POLICY", FLAT)
    assert not re.search(r"GRANT (INSERT|UPDATE|DELETE|ALL)", FLAT)


def test_service_role_bypass_and_reads_survive():
    for t in ("plans", "subscriptions"):
        assert f'CREATE POLICY "service_role_bypass" ON public.{t} FOR ALL TO service_role' in SVC
    assert '"plans_read_all"' in BASE and 'DROP POLICY IF EXISTS "plans_read_all"' not in FLAT
