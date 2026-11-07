"""Static checks for the billing-reads-platform-staff migration (no live DB)."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
MIG = ROOT / "products/core/backend/migrations"
FLAT = " ".join(migration_sql(MIG, "billing_reads_platform_staff").split())
BILLING = " ".join(migration_sql(MIG, "billing_gateways").split())
MEMBER = " ".join(migration_sql(MIG, "member_access_rules").split())


def test_helper_mirrors_platform_staff_role():
    assert "CREATE OR REPLACE FUNCTION public.is_platform_staff()" in FLAT
    assert "public.platform_staff_role((SELECT auth.uid())) IS NOT NULL" in FLAT
    assert "FUNCTION public.platform_staff_role(p_user_id uuid)" in MEMBER


def test_secdef_helper_is_locked_down():
    assert "SECURITY DEFINER" in FLAT and "SET search_path = public, pg_temp" in FLAT
    assert re.search(r"REVOKE ALL ON FUNCTION public\.is_platform_staff\(\) FROM PUBLIC, anon", FLAT)
    assert "GRANT EXECUTE ON FUNCTION public.is_platform_staff() TO authenticated, service_role" in FLAT


def test_billing_read_policies_switched_to_staff():
    for t in ("billing_customers", "billing_payments"):
        assert (f'CREATE POLICY "{t}_select_own_org" ON public.{t} FOR SELECT TO authenticated '
                "USING (org_id = public.current_org_id() OR public.is_platform_staff())") in FLAT
        assert f'{t}_select_own_org" ON public.{t} FOR SELECT TO authenticated USING (org_id = public.current_org_id() OR public.is_platform_admin())' in BILLING


def test_is_platform_admin_untouched_and_no_writes_opened():
    assert "public.is_platform_admin()" not in FLAT
    assert "FUNCTION public.is_platform_admin" not in FLAT
    assert not re.search(r"GRANT (INSERT|UPDATE|DELETE|ALL)", FLAT)
