"""Agents 083 (EOA for the platform grant ledger): every lifecycle change of `agents.agent_product_grants` appends one
row to `agents.agent_product_grant_eventos` IN THE SAME TRANSACTION (a trigger, so no writer can forget it), the event
table is append-only and service-role only, both tables declare their access tier, and the migration applies twice.

Runs on the REAL core + agents chain on PGlite (KB § PATTERNS/backend/migration-chain-replay.md)."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_MIG = "products/agents/backend/migrations/083_agent_product_grant_eventos.sql"

_ORG = "00000000-0000-0000-0000-0000000000a1"
_AGENT = "00000000-0000-0000-0000-0000000000b1"
_ADMIN = "00000000-0000-0000-0000-0000000000c1"
_TOK1 = "00000000-0000-0000-0000-0000000000d1"
_TOK2 = "00000000-0000-0000-0000-0000000000d2"


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


_LIFECYCLE = f"""
DO $t$
DECLARE v_id uuid; v_tipos text; v_de_para text; v_actor uuid;
BEGIN
  INSERT INTO agents.agent_product_grants (org_id, agent_id, agent_key, product, created_by)
       VALUES ('{_ORG}', '{_AGENT}', 'julia', 'social-wiring', '{_ADMIN}') RETURNING id INTO v_id;
  UPDATE agents.agent_product_grants
     SET status = 'ativo', product_token_id = '{_TOK1}' WHERE id = v_id;
  -- a rotation keeps the status and swaps the product token
  UPDATE agents.agent_product_grants SET product_token_id = '{_TOK2}' WHERE id = v_id;
  -- an unrelated column change is NOT a lifecycle event
  UPDATE agents.agent_product_grants SET last_error = 'x' WHERE id = v_id;
  UPDATE agents.agent_product_grants
     SET status = 'revogado', revoked_by = '{_ADMIN}', revoked_at = now() WHERE id = v_id;

  SELECT string_agg(event_type, ',' ORDER BY seq) INTO v_tipos
    FROM agents.agent_product_grant_eventos WHERE grant_id = v_id;
  IF v_tipos IS DISTINCT FROM 'grant_criado,grant_ativado,grant_tokens_rotacionados,grant_revogado' THEN
    RAISE EXCEPTION 'ASSERT event sequence: %', v_tipos;
  END IF;
  SELECT string_agg(coalesce(de, '-') || '>' || coalesce(para, '-'), ',' ORDER BY seq) INTO v_de_para
    FROM agents.agent_product_grant_eventos WHERE grant_id = v_id;
  IF v_de_para IS DISTINCT FROM '->pendente,pendente>ativo,ativo>ativo,ativo>revogado' THEN
    RAISE EXCEPTION 'ASSERT de/para: %', v_de_para;
  END IF;
  SELECT actor_id INTO v_actor FROM agents.agent_product_grant_eventos
   WHERE grant_id = v_id AND event_type = 'grant_revogado';
  IF v_actor IS DISTINCT FROM '{_ADMIN}'::uuid THEN
    RAISE EXCEPTION 'ASSERT the revocation names who revoked: %', v_actor;
  END IF;
  IF EXISTS (SELECT 1 FROM agents.agent_product_grant_eventos
              WHERE grant_id = v_id AND (org_id <> '{_ORG}' OR product <> 'social-wiring' OR agent_key <> 'julia')) THEN
    RAISE EXCEPTION 'ASSERT every event carries the (org, agent, product) of its grant';
  END IF;
END $t$;"""

_PRIVATE_AND_TIERED = """
DO $t$ BEGIN
  IF has_table_privilege('authenticated', 'agents.agent_product_grant_eventos', 'SELECT')
     OR has_table_privilege('anon', 'agents.agent_product_grant_eventos', 'SELECT') THEN
    RAISE EXCEPTION 'ASSERT agent_product_grant_eventos must be service-role only';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'agents.agent_product_grant_eventos'::regclass) THEN
    RAISE EXCEPTION 'ASSERT RLS must be on';
  END IF;
  IF obj_description('agents.agent_product_grant_eventos'::regclass, 'pg_class') IS DISTINCT FROM 'tier:platform'
     OR obj_description('agents.agent_product_grants'::regclass, 'pg_class') IS DISTINCT FROM 'tier:platform' THEN
    RAISE EXCEPTION 'ASSERT both grant tables declare tier:platform';
  END IF;
END $t$;"""


def test_grant_lifecycle_is_recorded_append_only_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", {_MIG}, "worktree", {})
    assert any(s["file"] == Path(_MIG).name for s in steps), "083 must be on the agents chain"
    steps.append(_step("lifecycle", _LIFECYCLE))
    steps.append(_step("private", _PRIVATE_AND_TIERED))
    steps.append(_step("no_update", "UPDATE agents.agent_product_grant_eventos SET para = 'x';"))
    steps.append(_step("no_delete", "DELETE FROM agents.agent_product_grant_eventos;"))
    probe = next(p for p in vdg.DEFAULT_REGISTRY if p.id == "agents.grants.eventos_append_only")
    assert probe.migrations == (Path(_MIG).name,)
    steps.append({"product": "agents", "file": probe.id, "sql": vdg.wrap_rollback_only(probe.sql), "mode": "file",
                  "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    mig = by_file[Path(_MIG).name]
    assert not mig["failures"], mig["failures"]  # applied twice, cleanly
    for name in ("lifecycle", "private"):
        assert not by_file[f"step:{name}"]["failures"], by_file[f"step:{name}"]["failures"]
    for name in ("no_update", "no_delete"):
        fails = by_file[f"step:{name}"]["failures"]
        assert fails and "append-only" in fails[0]["error"], fails
    probe_fails = by_file["agents.grants.eventos_append_only"]["failures"]
    assert probe_fails and "NOC_PROBE:refused:" in probe_fails[0]["error"], probe_fails
