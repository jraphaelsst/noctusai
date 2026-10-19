"""Migration 039 (shared skill library) BEHAVIOUR on a real Postgres (PGlite): the guards are proven by
watching them refuse, not by reading the DDL. Replays the agents chain (core first) with 039 applied as a whole
file, then runs one probe script whose every step raises PROBE_FAIL if a forbidden operation is PERMITTED.

Skipped (not green) when the node harness cannot be measured -- noctus.dev.migration_replay reports that as
inconclusive and so does this."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.dev import migration_replay as mr  # noqa: E402

REPO = MCP_ROOT.parents[1]
TARGET = "products/agents/backend/migrations/039_julia_v2_skills_compartilhadas.sql"

PROBE = r"""
DO $p$
DECLARE s uuid; v1 uuid; v2 uuid; org uuid := gen_random_uuid(); ag uuid; av uuid; av2 uuid; usr uuid := gen_random_uuid(); n int; st text; ph text;
BEGIN
  INSERT INTO agents.skills_biblioteca(chave, nome) VALUES ('probe-skill', 'P') RETURNING id INTO s;
  v1 := agents.criar_rascunho_skill(s, NULL, NULL);

  -- 1. a skill without real text cannot be published
  BEGIN PERFORM agents.publicar_skill_versao(v1, usr); RAISE EXCEPTION 'PROBE_FAIL publish-empty permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'invalid_payload' THEN RAISE EXCEPTION 'PROBE_FAIL publish-empty got %', SQLERRM; END IF; END;

  -- 2. only one draft per skill
  BEGIN PERFORM agents.criar_rascunho_skill(s, NULL, NULL); RAISE EXCEPTION 'PROBE_FAIL second-draft permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'draft_exists' THEN RAISE EXCEPTION 'PROBE_FAIL second-draft got %', SQLERRM; END IF; END;

  UPDATE agents.skill_versoes SET descricao_modelo = 'quando abrir', corpo = 'corpo 1' WHERE id = v1;
  INSERT INTO agents.skill_versao_arquivos(skill_versao_id, caminho, conteudo) VALUES (v1, 'ref/a.md', 'x');

  -- a draft cannot be pinned
  INSERT INTO agents.agents(org_id, key, nome, runtime) VALUES (org, 'probe', 'P', 'claude_sdk') RETURNING id INTO ag;
  av := agents.create_agent_draft(org, ag, NULL, usr);
  BEGIN INSERT INTO agents.agent_version_skill_refs(org_id, version_id, skill_versao_id) VALUES (org, av, v1);
    RAISE EXCEPTION 'PROBE_FAIL pin-draft-skill permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'invalid_payload' THEN RAISE EXCEPTION 'PROBE_FAIL pin-draft-skill got %', SQLERRM; END IF; END;

  PERFORM agents.publicar_skill_versao(v1, usr);

  -- 3. a published skill version (and its files) is immutable
  BEGIN UPDATE agents.skill_versoes SET corpo = 'mudou' WHERE id = v1; RAISE EXCEPTION 'PROBE_FAIL update-published permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL update-published got %', SQLERRM; END IF; END;
  BEGIN DELETE FROM agents.skill_versoes WHERE id = v1; RAISE EXCEPTION 'PROBE_FAIL delete-published permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL delete-published got %', SQLERRM; END IF; END;
  BEGIN UPDATE agents.skill_versao_arquivos SET conteudo = 'y' WHERE skill_versao_id = v1; RAISE EXCEPTION 'PROBE_FAIL update-file permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL update-file got %', SQLERRM; END IF; END;
  BEGIN INSERT INTO agents.skill_versao_arquivos(skill_versao_id, caminho, conteudo) VALUES (v1, 'novo.md', 'x'); RAISE EXCEPTION 'PROBE_FAIL insert-file permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL insert-file got %', SQLERRM; END IF; END;
  BEGIN UPDATE agents.skill_versoes SET status = 'rascunho' WHERE id = v1; RAISE EXCEPTION 'PROBE_FAIL unpublish permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL unpublish got %', SQLERRM; END IF; END;

  -- 4. pin it on the agent draft; the pin NULLs the draft's hash; one version per skill; org must match
  UPDATE agents.agent_versions SET compiled_hash = 'sha256:before' WHERE id = av;
  INSERT INTO agents.agent_version_skill_refs(org_id, version_id, skill_versao_id, obrigatoria_para, ordem)
    VALUES (org, av, v1, ARRAY['registrar_perfil', 'handoff'], 5);
  SELECT compiled_hash INTO ph FROM agents.agent_versions WHERE id = av;
  IF ph IS NOT NULL THEN RAISE EXCEPTION 'PROBE_FAIL pin did not invalidate the hash (%)', ph; END IF;
  IF (SELECT skill_id FROM agents.agent_version_skill_refs WHERE version_id = av) IS DISTINCT FROM s THEN RAISE EXCEPTION 'PROBE_FAIL skill_id not derived'; END IF;
  BEGIN INSERT INTO agents.agent_version_skill_refs(org_id, version_id, skill_versao_id) VALUES (org, av, v1);
    RAISE EXCEPTION 'PROBE_FAIL double-pin permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM NOT LIKE '%duplicate key%' THEN RAISE EXCEPTION 'PROBE_FAIL double-pin got %', SQLERRM; END IF; END;
  BEGIN UPDATE agents.agent_version_skill_refs SET obrigatoria_para = ARRAY['Bad Name'] WHERE version_id = av;
    RAISE EXCEPTION 'PROBE_FAIL bad-tool-name permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM NOT LIKE '%violates check constraint%' THEN RAISE EXCEPTION 'PROBE_FAIL bad-tool-name got %', SQLERRM; END IF; END;
  BEGIN UPDATE agents.agent_version_skill_refs SET org_id = gen_random_uuid() WHERE version_id = av;
    RAISE EXCEPTION 'PROBE_FAIL foreign-org permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'invalid_payload' THEN RAISE EXCEPTION 'PROBE_FAIL foreign-org got %', SQLERRM; END IF; END;

  -- 5. a v2 of the skill: publishing archives v1; the old pin stays on v1 (immutable)
  v2 := agents.criar_rascunho_skill(s, 'v2', v1);
  IF (SELECT corpo FROM agents.skill_versoes WHERE id = v2) <> 'corpo 1' THEN RAISE EXCEPTION 'PROBE_FAIL draft copy lost the body'; END IF;
  IF (SELECT count(*) FROM agents.skill_versao_arquivos WHERE skill_versao_id = v2) <> 1 THEN RAISE EXCEPTION 'PROBE_FAIL draft copy lost the files'; END IF;
  UPDATE agents.skill_versoes SET corpo = 'corpo 2' WHERE id = v2;
  PERFORM agents.publicar_skill_versao(v2, usr);
  SELECT status INTO st FROM agents.skill_versoes WHERE id = v1;
  IF st <> 'arquivada' THEN RAISE EXCEPTION 'PROBE_FAIL v1 not archived (%)', st; END IF;
  IF (SELECT skill_versao_id FROM agents.agent_version_skill_refs WHERE version_id = av) <> v1 THEN RAISE EXCEPTION 'PROBE_FAIL pin moved'; END IF;

  -- 6. a NEW draft of the agent inherits the pin (AFTER INSERT trigger), published one stays frozen
  UPDATE agents.agent_versions SET compiled_hash = 'sha256:' || repeat('a',64) WHERE id = av;
  PERFORM agents.publish_agent_version(org, av, usr, NULL, 'override reason with more than twenty chars', 'sha256:' || repeat('a',64), 'texto', '[]'::jsonb);
  av2 := agents.create_agent_draft(org, ag, av, usr);
  SELECT count(*) INTO n FROM agents.agent_version_skill_refs WHERE version_id = av2 AND skill_versao_id = v1 AND ordem = 5
     AND obrigatoria_para = ARRAY['registrar_perfil', 'handoff'];
  IF n <> 1 THEN RAISE EXCEPTION 'PROBE_FAIL the new draft did not inherit the pin (%)', n; END IF;
  BEGIN DELETE FROM agents.agent_version_skill_refs WHERE version_id = av; RAISE EXCEPTION 'PROBE_FAIL unpin-published permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL unpin-published got %', SQLERRM; END IF; END;
  BEGIN UPDATE agents.agent_version_skill_refs SET skill_versao_id = v2 WHERE version_id = av; RAISE EXCEPTION 'PROBE_FAIL repin-published permitted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'PROBE_FAIL repin-published got %', SQLERRM; END IF; END;
  -- the draft can be re-pinned to the newer version and unpinned
  UPDATE agents.agent_version_skill_refs SET skill_versao_id = v2 WHERE version_id = av2;
  DELETE FROM agents.agent_version_skill_refs WHERE version_id = av2;

  -- 7. the tables are not readable by tenants
  IF has_table_privilege('authenticated', 'agents.skill_versoes', 'SELECT')
     OR has_table_privilege('authenticated', 'agents.skills_biblioteca', 'SELECT')
     OR has_table_privilege('authenticated', 'agents.skill_versao_arquivos', 'SELECT')
     OR has_table_privilege('authenticated', 'agents.agent_version_skill_refs', 'SELECT')
     OR has_table_privilege('anon', 'agents.skill_versoes', 'SELECT') THEN
    RAISE EXCEPTION 'PROBE_FAIL a tenant role can read the skill library';
  END IF;
END $p$;
"""


def test_the_skill_library_guards_refuse_what_they_claim_to_refuse():
    if not (REPO / TARGET).exists():
        pytest.skip("migration 039 not in this tree")
    steps = mr._steps_for(REPO, "agents", {TARGET}, "worktree", {})
    steps.append({"product": "agents", "file": "skills_probe", "sql": PROBE, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 600, None)
    if not res.get("ok"):
        pytest.skip(f"PGlite harness could not measure: {res.get('error')}")
    (probe,) = [s for s in res["steps"] if s["file"] == "skills_probe"]
    assert probe["failures"] == [], probe["failures"]
    target = next(s for s in res["steps"] if s["file"] == TARGET.rsplit("/", 1)[1])
    assert target["failures"] == [], target["failures"]  # applied whole, and applied twice (idempotent)
