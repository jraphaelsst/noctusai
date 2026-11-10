"""Agents 080 (the follow-up cap) on the REAL core + agents chain on PGlite: a new draft of a standard copies
`max_retomadas_seguidas` (the clone RPC was re-declared with the column), a fresh row defaults to 2, the event table is
append-only and a deleted thread takes its events with it."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_MIGS = {"products/agents/backend/migrations/080_retomada_limite.sql"}

_BEHAVIOUR = """
DO $t$
DECLARE
  v_org uuid := gen_random_uuid(); v_agent uuid; v_lead uuid; v_thread uuid; v_padrao uuid; v_pv uuid; v_novo uuid; v_n int;
BEGIN
  INSERT INTO agents.agents (org_id, key, nome, runtime, definition_mode)
    VALUES (v_org, 'noc-retomada', 'NOC', 'claude_sdk', 'studio') RETURNING id INTO v_agent;
  INSERT INTO agents.lead_refs (org_id, produto, ref_externa) VALUES (v_org, 'social-wiring', 'l-1') RETURNING id INTO v_lead;
  INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, tipo, channel, channel_ref, lead_ref_id)
    VALUES (v_org, v_agent, v_org, 'thread_lead', 'whatsapp', jsonb_build_object('chat_id', 'c1'), v_lead) RETURNING id INTO v_thread;

  INSERT INTO agents.qualificacao_padroes (chave, nome) VALUES ('noc-ret-' || substr(v_org::text, 1, 8), 'NOC') RETURNING id INTO v_padrao;
  INSERT INTO agents.qualificacao_versoes (padrao_id, versao) VALUES (v_padrao, 1) RETURNING id INTO v_pv;
  INSERT INTO agents.qualificacao_parametros (versao_id, minimo_para_ofertar) VALUES (v_pv, '{"todos": []}'::jsonb);
  IF (SELECT max_retomadas_seguidas FROM agents.qualificacao_parametros WHERE versao_id = v_pv) <> 2 THEN
    RAISE EXCEPTION 'default is not 2';
  END IF;
  UPDATE agents.qualificacao_parametros SET max_retomadas_seguidas = 4 WHERE versao_id = v_pv;
  UPDATE agents.qualificacao_versoes SET status = 'publicada', publicada_em = now(), publicada_por = v_org WHERE id = v_pv;

  v_novo := agents.criar_rascunho_qualificacao(v_padrao, 'copia', v_pv);
  IF (SELECT max_retomadas_seguidas FROM agents.qualificacao_parametros WHERE versao_id = v_novo) <> 4 THEN
    RAISE EXCEPTION 'the new draft did not copy max_retomadas_seguidas';
  END IF;

  INSERT INTO agents.thread_retomada_eventos (org_id, thread_id, agent_id, tier, resultado) VALUES (v_org, v_thread, v_agent, 'horas', 'enviada');
  DELETE FROM agents.conversations WHERE id = v_thread;
  SELECT count(*) INTO v_n FROM agents.thread_retomada_eventos WHERE org_id = v_org;
  IF v_n <> 0 THEN RAISE EXCEPTION 'events survived the thread: %', v_n; END IF;
  RAISE EXCEPTION 'NOC_BEHAVIOUR_OK';
END
$t$;
"""


def test_080_clone_copies_the_cap_default_is_two_and_events_follow_their_thread(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    steps.append({"product": "agents", "file": "behaviour", "sql": _BEHAVIOUR, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    beh = next(st for st in res["steps"] if st["file"] == "behaviour")
    assert beh["failures"] and "NOC_BEHAVIOUR_OK" in beh["failures"][0]["error"], beh["failures"]
