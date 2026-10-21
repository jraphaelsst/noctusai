"""Agents 048 (agent deletion + surviving audit log) on the REAL core + agents chain on PGlite.

048 is applied twice (idempotency), then every assertion runs as a SQL step that RAISES on a mismatch:

* each guard of ``agents.excluir_agente`` refuses with its own code and deletes NOTHING
  (publicado / tem_instancias / tem_conversas / tem_canal / ativo / agent_not_found);
* an empty shell with a draft, a section, a persona, a client, a stored compiled prompt and an empty conversation is
  deleted with every dependent; the OTHER agent is untouched;
* its audit rows survive with ``agent_id`` NULL, keep the ``agent_key``/``agent_nome`` snapshot and gain exactly one
  ``agente_excluido`` tombstone;
* the append-only guard still refuses what it always did: an UPDATE / DELETE of an audit row outside the RPC, even the
  one mutation the RPC is allowed (agent_id -> NULL) while the flag is off.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_ORG = "a0000000-0000-4000-8000-00000000000a"
_USER = "b0000000-0000-4000-8000-00000000000b"
_CASCA = "f1000000-0000-4000-8000-000000000001"
_PUB = "f2000000-0000-4000-8000-000000000002"
_CONV = "f3000000-0000-4000-8000-000000000003"
_CANAL = "f4000000-0000-4000-8000-000000000004"
_ATIVO = "f5000000-0000-4000-8000-000000000005"
_TARGET = "products/agents/backend/migrations/048_agent_lifecycle_delete.sql"
_PREFIXES = ("assert:", "step:")
_HASH = "sha256:" + "a" * 64


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def _refused_with(code: str, call: str, agent: str) -> dict:
    """The RPC call must RAISE exactly `code`, and the agent must still exist afterwards."""
    return _step(f"refuses_{code}_{agent[:2]}", f"""
DO $t$ BEGIN
  BEGIN
    PERFORM {call};
    RAISE EXCEPTION 'ASSERT not refused: {code}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> '{code}' THEN RAISE EXCEPTION 'ASSERT wanted {code}, got %', SQLERRM; END IF;
  END;
  IF NOT EXISTS (SELECT 1 FROM agents.agents WHERE id = '{agent}') THEN
    RAISE EXCEPTION 'ASSERT a refused delete must delete nothing ({code})';
  END IF;
END $t$;""")


def _rpc(agent: str) -> str:
    return f"agents.excluir_agente('{_ORG}', '{agent}', '{_USER}')"


def _expect_refused(sql: str, what: str) -> str:
    return f"""
DO $t$ BEGIN
  BEGIN
    {sql}
    RAISE EXCEPTION 'ASSERT not refused: {what}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'ASSERT not refused%' THEN RAISE; END IF;
    IF SQLSTATE LIKE '42%' THEN RAISE; END IF;
  END;
END $t$;"""


ASSERTIONS = [
    _step("seed", f"""
SET search_path = agents, public;
INSERT INTO agents.agents (id, org_id, key, nome, runtime, ativo) VALUES
  ('{_CASCA}', '{_ORG}', 'casca', 'Casca', 'claude_sdk', false),
  ('{_PUB}', '{_ORG}', 'publicado', 'Publicado', 'claude_sdk', false),
  ('{_CONV}', '{_ORG}', 'conversa', 'Conversa', 'claude_sdk', false),
  ('{_CANAL}', '{_ORG}', 'canal', 'Canal', 'claude_sdk', false),
  ('{_ATIVO}', '{_ORG}', 'ativo', 'Ativo', 'claude_sdk', true);
-- the shell: a draft + section, a persona, a client, a stored compiled prompt, an empty conversation, audit rows
INSERT INTO agents.agent_versions (id, org_id, agent_id, versao, status, model, effort, created_by) VALUES
  ('d1000000-0000-4000-8000-000000000001', '{_ORG}', '{_CASCA}', 1, 'rascunho', 'claude-sonnet-5', 'low', '{_USER}');
INSERT INTO agents.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo)
  VALUES ('{_ORG}', 'd1000000-0000-4000-8000-000000000001', 'persona', 'Persona', 1, 'x');
INSERT INTO agents.agent_personas (org_id, agent_id, versao, nome, papel, model, effort, created_by)
  VALUES ('{_ORG}', '{_CASCA}', 1, 'P', 'papel', 'claude-sonnet-5', 'low', '{_USER}');
INSERT INTO agents.agent_clients (id, org_id, agent_id, slug, nome) VALUES
  ('c1000000-0000-4000-8000-000000000001', '{_ORG}', '{_CASCA}', 'cli', 'Cliente');
INSERT INTO agents.compiled_prompts (org_id, hash, version_id, client_id, texto, manifest) VALUES
  ('{_ORG}', '{_HASH}', 'd1000000-0000-4000-8000-000000000001', 'c1000000-0000-4000-8000-000000000001', 't', '[]'::jsonb);
INSERT INTO agents.conversations (org_id, agent_id, owner_user_id) VALUES ('{_ORG}', '{_CASCA}', '{_USER}');
UPDATE agents.agents SET publicacao_limiar = 0.9 WHERE id = '{_CASCA}';
-- guard fixtures: a PUBLISHED version, a conversation with a message, an active channel token
INSERT INTO agents.agent_versions (id, org_id, agent_id, versao, status, model, effort, created_by, published_by, published_at, compiled_hash, publish_override_reason)
  VALUES ('d2000000-0000-4000-8000-000000000002', '{_ORG}', '{_PUB}', 1, 'ativa', 'claude-sonnet-5', 'low', '{_USER}', '{_USER}', now(), '{_HASH}', 'publicação de teste para o guard de exclusão');
INSERT INTO agents.conversations (id, org_id, agent_id, owner_user_id) VALUES ('99000000-0000-4000-8000-000000000002', '{_ORG}', '{_CONV}', '{_USER}');
INSERT INTO agents.messages (org_id, conversation_id, role, texto) VALUES ('{_ORG}', '99000000-0000-4000-8000-000000000002', 'user', 'oi');
INSERT INTO agents.api_tokens (org_id, label, token_hash, token_prefix, scopes, principal_agent_id)
  VALUES ('{_ORG}', 'canal', 'h-canal', 'pk_x', '{{channel}}', '{_CANAL}');
"""),
    _refused_with("excluir_agente_publicado", _rpc(_PUB), _PUB),
    _refused_with("excluir_agente_tem_conversas", _rpc(_CONV), _CONV),
    _refused_with("excluir_agente_tem_canal", _rpc(_CANAL), _CANAL),
    _refused_with("excluir_agente_ativo", _rpc(_ATIVO), _ATIVO),
    _step("a_revoked_or_expired_channel_token_does_not_block", f"""
DO $t$ BEGIN
  UPDATE agents.api_tokens SET revoked_at = now() WHERE principal_agent_id = '{_CANAL}';
  PERFORM {_rpc(_CANAL)};
  IF EXISTS (SELECT 1 FROM agents.agents WHERE id = '{_CANAL}') THEN RAISE EXCEPTION 'ASSERT a revoked token must not block'; END IF;
END $t$;"""),
    _step("unknown_agent_and_foreign_org", f"""
DO $t$ BEGIN
  BEGIN PERFORM agents.excluir_agente('{_ORG}', gen_random_uuid(), '{_USER}'); RAISE EXCEPTION 'ASSERT no raise';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'agent_not_found' THEN RAISE EXCEPTION 'ASSERT wanted agent_not_found, got %', SQLERRM; END IF; END;
  BEGIN PERFORM agents.excluir_agente(gen_random_uuid(), '{_CASCA}', '{_USER}'); RAISE EXCEPTION 'ASSERT no raise';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM <> 'agent_not_found' THEN RAISE EXCEPTION 'ASSERT wanted agent_not_found, got %', SQLERRM; END IF; END;
END $t$;"""),
    _step("audit_rows_carry_the_agent_snapshot_before_the_delete", f"""
DO $t$ BEGIN
  IF (SELECT count(*) FROM agents.agent_audit_log WHERE agent_id = '{_CASCA}' AND agent_key = 'casca' AND agent_nome = 'Casca') < 1 THEN
    RAISE EXCEPTION 'ASSERT the limiar audit row must carry key+nome (snapshot trigger)';
  END IF;
END $t$;"""),
    _step("outside_the_rpc_the_audit_log_stays_append_only", _expect_refused(
        f"UPDATE agents.agent_audit_log SET agent_id = NULL WHERE agent_id = '{_CASCA}';", "agent_id -> NULL without the flag")
        + _expect_refused(f"UPDATE agents.agent_audit_log SET acao = 'publicado' WHERE agent_id = '{_CASCA}';", "update acao")
        + _expect_refused(f"DELETE FROM agents.agent_audit_log WHERE agent_id = '{_CASCA}';", "delete a row")
        + _expect_refused(f"DELETE FROM agents.agents WHERE id = '{_CASCA}';", "agent delete is blocked by its dependents")),
    _step("the_flag_alone_allows_nothing_but_agent_id_to_null", _expect_refused(
        f"PERFORM set_config('agents.agent_delete', 'on', true); UPDATE agents.agent_audit_log SET acao = 'publicado', agent_id = NULL WHERE agent_id = '{_CASCA}';",
        "flag on, another column moved")),
    _step("excluir_agente_deletes_the_shell_and_every_dependent", f"""
DO $t$ BEGIN
  PERFORM {_rpc(_CASCA)};
  IF EXISTS (SELECT 1 FROM agents.agents WHERE id = '{_CASCA}')
     OR EXISTS (SELECT 1 FROM agents.agent_versions WHERE agent_id = '{_CASCA}')
     OR EXISTS (SELECT 1 FROM agents.agent_prompt_sections WHERE version_id = 'd1000000-0000-4000-8000-000000000001')
     OR EXISTS (SELECT 1 FROM agents.agent_personas WHERE agent_id = '{_CASCA}')
     OR EXISTS (SELECT 1 FROM agents.agent_clients WHERE agent_id = '{_CASCA}')
     OR EXISTS (SELECT 1 FROM agents.compiled_prompts WHERE hash = '{_HASH}' AND version_id = 'd1000000-0000-4000-8000-000000000001')
     OR EXISTS (SELECT 1 FROM agents.conversations WHERE agent_id = '{_CASCA}') THEN
    RAISE EXCEPTION 'ASSERT dependents left behind';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agents.agents WHERE id = '{_PUB}') OR NOT EXISTS (SELECT 1 FROM agents.agent_versions WHERE agent_id = '{_PUB}') THEN
    RAISE EXCEPTION 'ASSERT another agent must be untouched';
  END IF;
END $t$;"""),
    _step("the_audit_survived_with_a_tombstone", f"""
DO $t$ BEGIN
  IF EXISTS (SELECT 1 FROM agents.agent_audit_log WHERE agent_key = 'casca' AND agent_id IS NOT NULL) THEN
    RAISE EXCEPTION 'ASSERT every audit row of the deleted agent must have agent_id NULL';
  END IF;
  IF (SELECT count(*) FROM agents.agent_audit_log WHERE agent_key = 'casca' AND acao = 'limiar_alterado') <> 1 THEN
    RAISE EXCEPTION 'ASSERT the older audit row must survive';
  END IF;
  IF (SELECT count(*) FROM agents.agent_audit_log WHERE agent_key = 'casca' AND acao = 'agente_excluido' AND agent_nome = 'Casca'
        AND actor = '{_USER}' AND antes->>'id' = '{_CASCA}') <> 1 THEN
    RAISE EXCEPTION 'ASSERT exactly one tombstone naming the agent';
  END IF;
END $t$;"""),
    _step("the_flag_is_off_again_after_the_rpc", _expect_refused(
        "UPDATE agents.agent_audit_log SET agent_id = NULL WHERE agent_key = 'casca';", "update after the rpc")),
    _step("the_acao_check_admits_the_lifecycle_actions", f"""
INSERT INTO agents.agent_audit_log (org_id, agent_id, acao) VALUES ('{_ORG}', '{_PUB}', 'agente_criado');
{_expect_refused(f"INSERT INTO agents.agent_audit_log (org_id, agent_id, acao) VALUES ('{_ORG}', '{_PUB}', 'inventada');", "unknown acao")}
{_expect_refused(f"INSERT INTO agents.agent_audit_log (org_id, agent_id, acao) VALUES ('{_ORG}', NULL, 'agente_criado');", "no agent id and no key")}"""),
]


def test_agent_deletion_keeps_the_audit_log_and_every_guard_holds_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "agents", {_TARGET}, "worktree", {})
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    assert not by_file[("agents", "048_agent_lifecycle_delete.sql")]["failures"], by_file[("agents", "048_agent_lifecycle_delete.sql")]["failures"]
    failed = {name: s["failures"][0]["error"] for (prod, name), s in by_file.items() if prod == "agents" and name.startswith(_PREFIXES) and s["failures"]}
    assert not failed, "\n".join(f"{k}: {v}" for k, v in failed.items())
    ran = [name for (prod, name) in by_file if prod == "agents" and name.startswith(_PREFIXES)]
    assert len(ran) == len(ASSERTIONS), "every assertion step must have run"
