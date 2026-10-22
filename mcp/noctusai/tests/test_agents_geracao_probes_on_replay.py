"""Agents 049 (AI draft generation + data-driven platform definitions): every GuardProbe of the migration runs on the REAL
core + agents chain on PGlite and reports `refused`, and the migration itself applies twice (idempotency) and keeps the
tables service-role only."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = vdg._AGENTS_GERACAO_PROBES
_MIGS = {f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def test_the_probes_are_registered():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert {p.guard_name for p in _PROBES} == {
        "geracoes_limite_check", "geracoes_one_active_idx", "agents_definicao_atributos_check"}
    for p in _PROBES:
        assert by_id[p.id] is p and p.product == "agents" and p.migrations == ("049_agent_geracao.sql",)


def test_every_geracao_probe_is_refused_and_the_tables_stay_private_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    steps.append(_step("privileges", """
DO $t$ BEGIN
  IF has_table_privilege('authenticated', 'agents.geracoes', 'SELECT') OR has_table_privilege('anon', 'agents.geracao_areas', 'SELECT') THEN
    RAISE EXCEPTION 'ASSERT geracoes tables must be service-role only';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'agents.geracoes'::regclass) THEN
    RAISE EXCEPTION 'ASSERT RLS must be on';
  END IF;
  IF EXISTS (SELECT 1 FROM agents.agents WHERE padrao_qualificacao IS NOT NULL OR escopo_qualificacao IS NOT NULL OR papel IS NOT NULL) THEN
    RAISE EXCEPTION 'ASSERT no key-specific backfill: existing rows keep NULL';
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
