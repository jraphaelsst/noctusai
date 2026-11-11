"""Orbity 034/035 on the REAL core + orbity chain on PGlite: the ON CONFLICT arbiters resolve and the browser roles hold nothing.

* `ON CONFLICT (org_id, campaign_id, date)` / `(org_id, lead_id)` are the arbiters the org-bound client's upserts name: if
  the composite unique index is missing Postgres raises 42P10 at PLAN time, so a zero-row `INSERT ... SELECT ... WHERE false`
  proves the target resolves without needing parent rows;
* after the sweep the browser roles hold NO privilege on any orbity table but SELECT on status_pagina, no sequence, and cannot
  EXECUTE `seed_default_lead_stages`; service_role keeps everything.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_TARGETS = {f"products/orbity/backend/migrations/{n}" for n in ("034_orbity_service_only_batch3.sql", "035_orbity_function_and_grant_hardening.sql")}


def _check(name: str, condition: str) -> dict:
    sql = f"DO $chk$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'ASSERT {name}'; END IF; END $chk$;"
    return {"product": "orbity", "file": f"assert:{name}", "sql": sql, "mode": "file", "twice": False}


def _step(name: str, sql: str) -> dict:
    return {"product": "orbity", "file": f"assert:{name}", "sql": sql, "mode": "file", "twice": False}


ASSERTIONS = [
    _step("campaign_metrics_arbiter_resolves", """
INSERT INTO orbity.campaign_metrics (org_id, campaign_id, date)
SELECT gen_random_uuid(), gen_random_uuid(), CURRENT_DATE WHERE false
ON CONFLICT (org_id, campaign_id, date) DO NOTHING;"""),
    _step("lead_scoring_results_arbiter_resolves", """
INSERT INTO orbity.lead_scoring_results (org_id, lead_id)
SELECT gen_random_uuid(), gen_random_uuid() WHERE false
ON CONFLICT (org_id, lead_id) DO NOTHING;"""),
    _check("no_browser_privilege_on_any_table_but_status_pagina", """
(SELECT count(*) FROM information_schema.role_table_grants
  WHERE table_schema = 'orbity' AND grantee IN ('anon', 'authenticated', 'PUBLIC')
    AND NOT (table_name = 'status_pagina' AND privilege_type = 'SELECT')) = 0"""),
    _check("status_pagina_is_select_only_for_the_browser", """
has_table_privilege('authenticated', 'orbity.status_pagina', 'SELECT') AND has_table_privilege('anon', 'orbity.status_pagina', 'SELECT')
AND NOT has_table_privilege('authenticated', 'orbity.status_pagina', 'INSERT')
AND NOT has_table_privilege('authenticated', 'orbity.status_pagina', 'UPDATE')
AND NOT has_table_privilege('authenticated', 'orbity.status_pagina', 'DELETE')"""),
    _check("tenant_tables_are_service_only", """
NOT has_table_privilege('authenticated', 'orbity.tasks', 'SELECT') AND NOT has_table_privilege('anon', 'orbity.leads', 'SELECT')
AND has_table_privilege('service_role', 'orbity.tasks', 'INSERT')"""),
    _check("seed_default_lead_stages_is_service_only", """
NOT has_function_privilege('anon', 'orbity.seed_default_lead_stages(uuid)', 'EXECUTE')
AND NOT has_function_privilege('authenticated', 'orbity.seed_default_lead_stages(uuid)', 'EXECUTE')
AND has_function_privilege('service_role', 'orbity.seed_default_lead_stages(uuid)', 'EXECUTE')"""),
    _check("seed_default_lead_stages_pins_its_search_path", """
(SELECT bool_or(c LIKE 'search_path=%') FROM pg_proc p, unnest(p.proconfig) c WHERE p.oid = 'orbity.seed_default_lead_stages(uuid)'::regprocedure)"""),
]


def test_the_composite_arbiters_resolve_and_the_browser_roles_hold_nothing_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "orbity", set(_TARGETS), "worktree", {})
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    for target in ("034_orbity_service_only_batch3.sql", "035_orbity_function_and_grant_hardening.sql"):
        assert not by_file[("orbity", target)]["failures"], (target, by_file[("orbity", target)]["failures"])
    failed = {n: s["failures"][0]["error"] for (prod, n), s in by_file.items() if prod == "orbity" and n.startswith("assert:") and s["failures"]}
    assert not failed, failed
    ran = [n for (prod, n) in by_file if prod == "orbity" and n.startswith("assert:")]
    assert len(ran) == len(ASSERTIONS), "every assertion step must have run"
