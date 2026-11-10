"""Agents 079 (an emergency stays open and closes by inactivity) on the REAL core + agents chain on PGlite: the file
applies twice (idempotent), the window column is CHECKed, the partial index exists, and `emergencia` is a valid
alert tipo while an unknown tipo is still refused."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_MIGS = {"products/agents/backend/migrations/079_emergencia_inatividade.sql"}

_BEHAVIOUR = """
DO $t$
DECLARE
  v_org uuid := gen_random_uuid(); v_agent uuid; v_lead uuid; v_thread uuid; v_ok boolean;
BEGIN
  INSERT INTO agents.agents (org_id, key, nome, runtime, definition_mode)
    VALUES (v_org, 'noc-emerg', 'NOC', 'claude_sdk', 'studio') RETURNING id INTO v_agent;
  INSERT INTO agents.lead_refs (org_id, produto, ref_externa) VALUES (v_org, 'social-wiring', 'l-1') RETURNING id INTO v_lead;
  INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, tipo, channel, channel_ref, lead_ref_id)
    VALUES (v_org, v_agent, v_org, 'thread_lead', 'whatsapp', jsonb_build_object('chat_id', 'c1'), v_lead) RETURNING id INTO v_thread;
  INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado, fecha_inativo_min)
    VALUES (v_thread, v_agent, v_org, 'ativo', 10);

  v_ok := false;
  BEGIN
    UPDATE agents.thread_participantes SET fecha_inativo_min = 0 WHERE thread_id = v_thread;
  EXCEPTION WHEN check_violation THEN v_ok := true; END;
  IF NOT v_ok THEN RAISE EXCEPTION 'window 0 accepted'; END IF;

  INSERT INTO agents.thread_alertas (org_id, thread_id, agent_id, tipo, descricao)
    VALUES (v_org, v_thread, v_agent, 'emergencia', 'gas');
  v_ok := false;
  BEGIN
    INSERT INTO agents.thread_alertas (org_id, thread_id, agent_id, tipo, descricao)
      VALUES (v_org, v_thread, v_agent, 'inventado', 'x');
  EXCEPTION WHEN check_violation THEN v_ok := true; END;
  IF NOT v_ok THEN RAISE EXCEPTION 'unknown tipo accepted'; END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'agents'
                 AND indexname = 'idx_agents_thread_participantes_inatividade') THEN
    RAISE EXCEPTION 'index missing';
  END IF;
  RAISE EXCEPTION 'NOC_BEHAVIOUR_OK';
END
$t$;
"""


def test_079_applies_twice_and_behaves_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    steps.append({"product": "agents", "file": "behaviour", "sql": _BEHAVIOUR, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    beh = next(st for st in res["steps"] if st["file"] == "behaviour")
    assert beh["failures"] and "NOC_BEHAVIOUR_OK" in beh["failures"][0]["error"], beh["failures"]
