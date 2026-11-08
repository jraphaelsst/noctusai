"""The noc_funnel migration (NoctusAI's own funnel on website_leads): the generated section equals the seed
generator's output, the hand-written section keeps the platform tier, and the scope id in SQL is the one
the Python config uses."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

MIG = Path(__file__).resolve().parents[1] / "migrations"
SQL = migration_sql(MIG, "noc_funnel")
FLAT = " ".join(SQL.split())


def test_generated_section_is_the_organs_renderer_output():
    from app.noc_funnel import render_migration

    assert render_migration() in SQL, (
        "noc_funnel.sql drifted from noctusai_lib pipeline_migration -- regenerate section 1 "
        "(app.noc_funnel.render_migration); never hand-edit it"
    )


def test_scope_id_in_sql_is_the_configs_platform_org_id():
    from app.noc_funnel import FUNNEL, NOC_FUNNEL_ORG_ID

    assert FUNNEL.tenancy == "platform" and FUNNEL.platform_org_id == NOC_FUNNEL_ORG_ID
    ids = set(re.findall(r"'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'", SQL))
    assert ids == {NOC_FUNNEL_ORG_ID}


def test_default_stages_match_the_gate_roles():
    from app.noc_funnel import STAGE_ROLES

    papeis = re.findall(r"'funil_noc', '(\w+)', '[^']+', '\w+', \d, '(\w+)'\)", FLAT)
    assert [p for _slug, p in papeis] == list(STAGE_ROLES)


def test_platform_tier_and_no_browser_grants():
    for table in ("pipeline_stages", "pipeline_movimentos"):
        assert f"COMMENT ON TABLE public.{table} IS 'tier:platform'" in FLAT
        assert f"REVOKE ALL ON public.{table} FROM anon, authenticated" in FLAT
        assert f"REVOKE ALL ON public.{table} FROM PUBLIC" in FLAT
    for table in ("website_leads", "website_lead_activities"):
        assert f"REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated" in FLAT
        assert f"COMMENT ON TABLE public.{table} IS 'tier:platform'" in FLAT
    assert not re.search(r"GRANT [A-Z, ]+ ON [\w.]+ TO (anon|authenticated|PUBLIC)", FLAT)
    assert not re.search(r"CREATE POLICY[^;]+TO (anon|authenticated)", FLAT)


def test_every_security_definer_function_is_revoked_from_browser_roles():
    # The generator's touch function is SECURITY INVOKER with an empty search_path (seed
    # funnel follow-ups); any DEFINER function that remains must still be revoked.
    assert re.search(r"FUNCTION public\.\w*updated_at\w*\(\)[^$]*?SECURITY INVOKER SET search_path = ''", SQL)
    fns = re.findall(r"CREATE OR REPLACE FUNCTION (public\.\w+)\(\)[^$]*?SECURITY DEFINER", SQL)
    for fn in fns:
        assert f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC, anon, authenticated" in FLAT


def test_lead_to_card_triggers_and_legacy_stage_kept():
    assert "BEFORE INSERT ON public.website_leads" in FLAT
    assert "AFTER INSERT ON public.website_leads" in FLAT
    assert not re.search(r"DROP COLUMN", FLAT), "expand only: the legacy stage column stays (N-1 image)"
    assert "SET lock_timeout" in FLAT


def test_entry_history_row_is_written_by_the_trigger_only():
    """The trigger owns `entrada` (public lead path), so the organ must not write a second one."""
    from app.noc_funnel import FUNNEL

    assert FUNNEL.record_entry_on_create is False
    assert "AFTER INSERT ON public.website_leads" in FLAT and "'entrada'" in FLAT
