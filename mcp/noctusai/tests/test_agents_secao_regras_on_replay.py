"""Agents secao_regras (agent_prompt_sections.regras) on the REAL core + agents chain on PGlite.

The regras migration is applied twice by the harness (idempotency). The assertion steps then prove, on the real chain:

* the column exists, ``text[] NOT NULL DEFAULT '{}'``;
* the backfill statement tags a ``discordar-com-respeito`` section on a DRAFT and on a PUBLISHED version, and running it
  again adds nothing (the rule is never duplicated);
* the immutability guard is back ON after the migration (a published section still refuses an UPDATE);
* ``replace_draft_sections`` and ``replace_draft_bundle`` write the rules they are given, and a section sent without
  them ends with none.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_ORG = "a0000000-0000-4000-8000-00000000000a"
_USER = "b0000000-0000-4000-8000-00000000000b"
_AG = "f1000000-0000-4000-8000-000000000001"
_DRAFT = "d1000000-0000-4000-8000-000000000001"
_PUB = "d2000000-0000-4000-8000-000000000002"
_TARGET = next(Path(REPO_ROOT).glob("products/agents/backend/migrations/*_secao_regras.sql")).relative_to(REPO_ROOT).as_posix()
_PREFIXES = ("assert:", "step:")
_HASH = "sha256:" + "a" * 64

_BACKFILL = """
ALTER TABLE agents.agent_prompt_sections DISABLE TRIGGER guard_agent_prompt_sections_immutable;
UPDATE agents.agent_prompt_sections SET regras = array_append(regras, 'discordar-com-respeito')
 WHERE chave = 'discordar-com-respeito' AND NOT ('discordar-com-respeito' = ANY(regras));
ALTER TABLE agents.agent_prompt_sections ENABLE TRIGGER guard_agent_prompt_sections_immutable;
"""


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


ASSERTIONS = [
    _step("seed", f"""
SET search_path = agents, public;
INSERT INTO agents.agents (id, org_id, key, nome, runtime, ativo) VALUES ('{_AG}', '{_ORG}', 'a', 'A', 'claude_sdk', false);
INSERT INTO agents.agent_versions (id, org_id, agent_id, versao, status, model, effort, created_by)
  VALUES ('{_DRAFT}', '{_ORG}', '{_AG}', 2, 'rascunho', 'claude-sonnet-5', 'low', '{_USER}');
INSERT INTO agents.agent_versions (id, org_id, agent_id, versao, status, model, effort, created_by, published_by, published_at, compiled_hash, publish_override_reason)
  VALUES ('{_PUB}', '{_ORG}', '{_AG}', 1, 'ativa', 'claude-sonnet-5', 'low', '{_USER}', '{_USER}', now(), '{_HASH}', 'publicação de teste para o guard');
INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo) VALUES
  ('{_ORG}', '{_DRAFT}', 'discordar-com-respeito', 'D', 1, 'x'), ('{_ORG}', '{_DRAFT}', 'persona', 'P', 2, 'y');
ALTER TABLE agents.agent_prompt_sections DISABLE TRIGGER guard_agent_prompt_sections_immutable;
INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo)
  VALUES ('{_ORG}', '{_PUB}', 'discordar-com-respeito', 'D', 1, 'x');
ALTER TABLE agents.agent_prompt_sections ENABLE TRIGGER guard_agent_prompt_sections_immutable;
"""),
    _step("column_is_text_array_not_null_default_empty", """
DO $t$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'agents' AND table_name = 'agent_prompt_sections'
      AND column_name = 'regras' AND is_nullable = 'NO' AND data_type = 'ARRAY') THEN
    RAISE EXCEPTION 'ASSERT regras must be text[] NOT NULL';
  END IF;
  IF (SELECT count(*) FROM agents.agent_prompt_sections WHERE regras <> '{}') <> 0 THEN
    RAISE EXCEPTION 'ASSERT fresh rows start with no rules';
  END IF;
END $t$;"""),
    _step("backfill_tags_draft_and_published_once_even_run_twice", _BACKFILL + _BACKFILL + """
DO $t$ BEGIN
  IF (SELECT count(*) FROM agents.agent_prompt_sections WHERE chave = 'discordar-com-respeito' AND regras = ARRAY['discordar-com-respeito']) <> 2 THEN
    RAISE EXCEPTION 'ASSERT both discordar sections tagged exactly once';
  END IF;
  IF (SELECT count(*) FROM agents.agent_prompt_sections WHERE chave = 'persona' AND regras = '{}') <> 1 THEN
    RAISE EXCEPTION 'ASSERT other sections untouched';
  END IF;
END $t$;"""),
    _step("the_immutability_guard_is_back_on", """
DO $t$ BEGIN
  BEGIN
    UPDATE agents.agent_prompt_sections SET conteudo = 'z' WHERE version_id = 'd2000000-0000-4000-8000-000000000002';
    RAISE EXCEPTION 'ASSERT published section edit not refused';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'version_immutable' THEN RAISE EXCEPTION 'ASSERT wanted version_immutable, got %', SQLERRM; END IF;
  END;
END $t$;"""),
    _step("replace_draft_sections_writes_the_rules", f"""
DO $t$ BEGIN
  PERFORM agents.replace_draft_sections('{_ORG}', '{_DRAFT}', jsonb_build_array(
    jsonb_build_object('chave', 'honestidade', 'titulo', 'H', 'ordem', 1, 'conteudo', 'c', 'ativo', true, 'regras', jsonb_build_array('discordar-com-respeito')),
    jsonb_build_object('chave', 'persona', 'titulo', 'P', 'ordem', 2, 'conteudo', 'c', 'ativo', true)));
  IF (SELECT regras FROM agents.agent_prompt_sections WHERE version_id = '{_DRAFT}' AND chave = 'honestidade') <> ARRAY['discordar-com-respeito'] THEN
    RAISE EXCEPTION 'ASSERT the rule must be written';
  END IF;
  IF (SELECT regras FROM agents.agent_prompt_sections WHERE version_id = '{_DRAFT}' AND chave = 'persona') <> '{{}}' THEN
    RAISE EXCEPTION 'ASSERT a section sent without rules has none';
  END IF;
END $t$;"""),
    _step("replace_draft_bundle_writes_the_rules", f"""
DO $t$ BEGIN
  PERFORM agents.replace_draft_bundle('{_ORG}', '{_DRAFT}', jsonb_build_array(
    jsonb_build_object('chave', 'honestidade', 'titulo', 'H', 'ordem', 1, 'conteudo', 'c', 'ativo', true, 'regras', jsonb_build_array('discordar-com-respeito'))), '[]'::jsonb);
  IF (SELECT regras FROM agents.agent_prompt_sections WHERE version_id = '{_DRAFT}' AND chave = 'honestidade') <> ARRAY['discordar-com-respeito'] THEN
    RAISE EXCEPTION 'ASSERT the bundle must carry the rule';
  END IF;
END $t$;"""),
    _step("a_new_draft_copied_from_a_version_keeps_the_rules", f"""
DO $t$
DECLARE v_new UUID;
BEGIN
  DELETE FROM agents.agent_versions WHERE id = '{_DRAFT}';  -- one draft per agent: free the slot
  v_new := agents.create_agent_draft('{_ORG}', '{_AG}', '{_PUB}', '{_USER}');
  IF (SELECT regras FROM agents.agent_prompt_sections WHERE version_id = v_new AND chave = 'discordar-com-respeito') <> ARRAY['discordar-com-respeito'] THEN
    RAISE EXCEPTION 'ASSERT the copied draft must keep the rules';
  END IF;
END $t$;"""),
]


def test_secao_regras_migration_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "agents", {_TARGET}, "worktree", {})
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    target = by_file[("agents", Path(_TARGET).name)]
    assert not target["failures"], target["failures"]
    failed = {name: s["failures"][0]["error"] for (prod, name), s in by_file.items() if prod == "agents" and name.startswith(_PREFIXES) and s["failures"]}
    assert not failed, "\n".join(f"{k}: {v}" for k, v in failed.items())
    ran = [name for (prod, name) in by_file if prod == "agents" and name.startswith(_PREFIXES)]
    assert len(ran) == len(ASSERTIONS), "every assertion step must have run"
