"""Agents 036 (browser-read lockdown, security finding C2) on the REAL core + agents chain on PGlite.

1. With 036 applied (twice -- idempotency) every lockdown probe is ``clean``: no agents table outside the allowlist
   grants anything to anon/authenticated, no policy names them, ``status_pagina`` is read-only for the browser.
2. With 036 replaced by a no-op the same probes report ``violation`` -- the probes are not vacuous (001's
   ``GRANT ALL`` + the ``*_select_own_org`` policies really do expose the schema without it).
3. Behaviour, not just catalog: as ``authenticated`` AND ``anon`` a SELECT on every definition / eval / knowledge
   table (Julia's prompt, security finding P1-A) is refused (insufficient_privilege) after the WHOLE agents chain,
   and on ``status_pagina`` it succeeds.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_M036 = "products/agents/backend/migrations/036_revoke_authenticated_content.sql"
_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = vdg._AGENTS_BROWSER_LOCKDOWN_PROBES

_BEHAVIOUR = "step:authenticated-cannot-select-content-but-can-read-status_pagina"
_BEHAVIOUR_SQL = """
DO $t$
DECLARE
  t text;
  -- Julia's definition (prompt, skills, versions, textos/ferramentas/decisoes/specs, the shared skill library),
  -- eval and knowledge tables, and the audit log: service-role only, for ANY org member.
  v_tables text[] := ARRAY[
    'compiled_prompts', 'agent_prompt_sections', 'agent_skills', 'agent_skill_files', 'agent_versions',
    'agent_version_textos', 'agent_version_ferramentas', 'agent_version_decisoes', 'agent_version_specs',
    'agent_version_skill_refs', 'agent_version_marcadores', 'skills_biblioteca', 'skill_versoes',
    'skill_versao_arquivos', 'textos_plataforma', 'eval_cases', 'eval_runs', 'eval_results',
    'eval_mecanismo_runs', 'eval_mecanismo_execucoes', 'knowledge_collections', 'knowledge_documents',
    'knowledge_revisions', 'agent_audit_log', 'conformidade_regras', 'definition_org_grants'
  ];
BEGIN
  FOREACH t IN ARRAY v_tables LOOP
    IF to_regclass(format('agents.%I', t)) IS NULL THEN
      RAISE EXCEPTION 'ASSERT agents.% is not in the replayed chain (list drifted)', t;
    END IF;
    SET LOCAL ROLE authenticated;
    BEGIN
      EXECUTE format('SELECT 1 FROM agents.%I LIMIT 1', t);
      RESET ROLE;
      RAISE EXCEPTION 'ASSERT authenticated could SELECT agents.%', t;
    EXCEPTION WHEN insufficient_privilege THEN
      RESET ROLE;
    END;
    SET LOCAL ROLE anon;
    BEGIN
      EXECUTE format('SELECT 1 FROM agents.%I LIMIT 1', t);
      RESET ROLE;
      RAISE EXCEPTION 'ASSERT anon could SELECT agents.%', t;
    EXCEPTION WHEN insufficient_privilege THEN
      RESET ROLE;
    END;
  END LOOP;
  SET LOCAL ROLE authenticated;
  PERFORM 1 FROM agents.status_pagina LIMIT 1;
  RESET ROLE;
END $t$;
"""


def _run(overrides: dict[str, str], with_behaviour: bool = False) -> tuple[dict[str, str], list[dict]]:
    steps = mr._steps_for(Path(REPO_ROOT), "agents", {_M036}, "worktree", overrides)
    for p in _PROBES:
        steps.append({"product": "agents", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    if with_behaviour:
        steps.append({"product": "agents", "file": _BEHAVIOUR, "sql": _BEHAVIOUR_SQL, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in _PROBES}
    out: dict[str, str] = {}
    other: list[dict] = []
    for st in res["steps"]:
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
        elif st["failures"] and st["product"] == "agents":  # core history carries its own known residue
            other.append(st)
    return out, other


def test_lockdown_probes_are_registered_and_declare_036():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert len(_PROBES) == 3
    for p in _PROBES:
        assert by_id[p.id] is p
        assert "036_revoke_authenticated_content.sql" in p.migrations


def test_every_lockdown_probe_is_clean_with_036(pglite):
    out, other = _run({}, with_behaviour=True)
    assert other == [], other
    assert out == {p.id: "clean" for p in _PROBES}


def test_without_036_the_lockdown_probes_report_violation(pglite):
    out, other = _run({_M036: "SELECT 1;\n"})
    assert other == [], other
    assert out == {p.id: "violation" for p in _PROBES}, out
