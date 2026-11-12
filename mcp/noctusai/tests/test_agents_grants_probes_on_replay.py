"""Agents 060 (platform grant ledger, Julia-line D1) + 083 (its append-only event log): the grant GuardProbes run on the REAL core + agents chain
on PGlite and reports `refused`; the table stays service-role only, and the migration applies twice."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = [p for p in vdg.DEFAULT_REGISTRY if p.id.startswith("agents.grants.")]
_MIGS = {f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def test_the_probe_is_registered():
    assert [p.id for p in _PROBES] == ["agents.grants.one_live_unique", "agents.grants.eventos_append_only"]
    assert [p.guard_name for p in _PROBES] == [
        "idx_agent_product_grants_one_live", "guard_agent_product_grant_eventos_append_only",
    ]
    assert {p.product for p in _PROBES} == {"agents"}


def test_the_one_live_probe_is_refused_and_the_table_stays_private_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    steps.append(_step("privileges", """
DO $t$ BEGIN
  IF has_table_privilege('authenticated', 'agents.agent_product_grants', 'SELECT')
     OR has_table_privilege('anon', 'agents.agent_product_grants', 'SELECT') THEN
    RAISE EXCEPTION 'ASSERT agent_product_grants must be service-role only';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'agents.agent_product_grants'::regclass) THEN
    RAISE EXCEPTION 'ASSERT RLS must be on';
  END IF;
END $t$;"""))
    for p in _PROBES:
        steps.append({"product": "agents", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in _PROBES}
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] == "step:privileges":
            assert not st["failures"], st["failures"]
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    bad = {k: v for k, v in out.items() if v != "refused"}
    assert not bad and len(out) == len(_PROBES), bad
