"""Core 078 ("every entry is a choice" at the PostgREST layer) on the REAL core chain on PGlite.

Every registered ``current_org_id_for.*`` GuardProbe runs against the replayed chain plus a
minimal fixture (platform org + staff, a customer org + ordinary user, a licensed product):

1. With 078 applied every probe is ``clean`` -- the new NULL-without-selection probes AND the
   unchanged ones (target on a valid selection, home for non-staff / not-ready product / aal1
   on a requires-2FA product, the pin-header narrowing).
2. With 078 dropped from the chain exactly the probes that encode 078 report ``violation``
   (the helper fell through to home) -- the probes are not vacuous.

The PGlite stub ``auth.uid()`` reads only ``request.jwt.claim.sub``; the fixture re-declares it
to also read ``request.jwt.claims ->> 'sub'`` (what the probes forge, as Supabase does), and adds
the ``auth.sessions`` table the helper checks.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_M078 = "products/core/backend/migrations/078_org_picker_postgrest_entry.sql"
_SENT = re.compile(r"NOC_PROBE:(\w+):")
_FIXTURE = "core-078-picker-fixture"

_FIXTURE_SQL = """
CREATE TABLE IF NOT EXISTS auth.sessions (id uuid PRIMARY KEY, user_id uuid);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
                  nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid $$;
SET session_replication_role = replica;
DO $$
DECLARE
  v_plat uuid := gen_random_uuid();
  v_cust uuid := gen_random_uuid();
  v_other uuid := gen_random_uuid();
  v_staff uuid := gen_random_uuid();
  v_plain uuid := gen_random_uuid();
  v_pid uuid;
BEGIN
  INSERT INTO public.organizations (id, nome, slug, is_platform) VALUES
    (v_plat, 'NoctusAI', 'noc-probe-plat', true),
    (v_cust, 'Cliente', 'noc-probe-cust', false),
    (v_other, 'Outro', 'noc-probe-other', false);
  INSERT INTO auth.users (id, email) VALUES (v_staff, 'staff@probe.test'), (v_plain, 'plain@probe.test');
  INSERT INTO public.noctus_users (id, email, nome, org_id, org_role, role) VALUES
    (v_staff, 'staff@probe.test', 'Staff', v_plat, 'owner', 'admin'),
    (v_plain, 'plain@probe.test', 'Plain', v_cust, 'owner', 'user');
  SELECT id INTO v_pid FROM public.products WHERE db_schema IS NOT NULL ORDER BY slug LIMIT 1;
  IF v_pid IS NULL THEN
    RAISE EXCEPTION 'fixture: no product with a db_schema in the replayed core chain';
  END IF;
  INSERT INTO public.licenses (org_id, product_id, status) VALUES (v_cust, v_pid, 'active');
END $$;
SET session_replication_role = origin;
"""

#: The probes whose expectation IS core 078 (NULL instead of home for staff without a valid selection).
_ENTRY_PROBES = {
    "current_org_id_for.null_on_session_mismatch",
    "current_org_id_for.null_when_target_unlicensed",
    "current_org_id_for.null_when_auth_session_gone",
    "current_org_id_for.null_for_staff_without_selection_on_ready_product",
    "current_org_id_for.null_for_aal1_staff_without_selection_when_mfa_optional",
}


def _helper_probes() -> list[vdg.GuardProbe]:
    return [p for p in vdg.DEFAULT_REGISTRY if p.id.startswith("current_org_id_for.")]


def _outcomes(overrides: dict[str, str]) -> dict[str, str]:
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", overrides)
    steps.append({"product": "core", "file": _FIXTURE, "sql": _FIXTURE_SQL, "mode": "file", "twice": False})
    for probe in _helper_probes():
        steps.append({"product": "core", "file": probe.id, "sql": vdg.wrap_rollback_only(probe.sql),
                      "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] == _FIXTURE:
            assert not st["failures"], st["failures"]
        elif st["file"].startswith("current_org_id_for."):
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    return out


def test_entry_probes_are_registered_and_declare_078():
    by_id = {p.id: p for p in _helper_probes()}
    assert _ENTRY_PROBES <= set(by_id)
    for pid in _ENTRY_PROBES | {"current_org_id_for.home_for_aal1_staff_without_selection_when_mfa_required"}:
        assert "078_org_picker_postgrest_entry.sql" in by_id[pid].migrations, pid


def test_every_helper_probe_is_clean_with_078(pglite):
    out = _outcomes({})
    assert len(out) == len(_helper_probes())
    assert {k: v for k, v in out.items() if v != "clean"} == {}


def test_without_078_exactly_the_entry_probes_fail(pglite):
    out = _outcomes({_M078: "SELECT 1;\n"})
    assert {k for k, v in out.items() if v != "clean"} == _ENTRY_PROBES
    assert all(out[k] == "violation" for k in _ENTRY_PROBES), out
