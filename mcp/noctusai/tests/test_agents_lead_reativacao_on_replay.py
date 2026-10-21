"""Agents 043 (an operator lifts a lead's opt-out, on the record) on the REAL core + agents chain on PGlite:
the new GuardProbe is refused, `reativar_lead` lifts the opt-out and records the `reativacao` event in one
transaction (no active opt-out = nothing written), and a later opt-out is a NEW event, never the reactivation."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = tuple(p for p in vdg._AGENTS_JULIA_V2_PROBES if p.migrations == (vdg._m("043"),))
_MIGS = {"products/agents/backend/migrations/043_julia_v2_lead_reativacao.sql",
         *{f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}}

_BEHAVIOUR = """
DO $t$
DECLARE
  v_org uuid := gen_random_uuid(); v_agent uuid; v_lead uuid; v_thread uuid; v_r jsonb; v_r2 jsonb; v_op uuid := gen_random_uuid();
BEGIN
  INSERT INTO agents.agents (org_id, key, nome, runtime, definition_mode)
    VALUES (v_org, 'noc-reativar', 'NOC', 'claude_sdk', 'studio') RETURNING id INTO v_agent;
  INSERT INTO agents.lead_refs (org_id, produto, ref_externa) VALUES (v_org, 'social-wiring', 'l-1') RETURNING id INTO v_lead;
  INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, tipo, channel, channel_ref, lead_ref_id)
    VALUES (v_org, v_agent, v_org, 'thread_lead', 'whatsapp', jsonb_build_object('chat_id', 'c1'), v_lead) RETURNING id INTO v_thread;
  INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado) VALUES (v_thread, v_agent, v_org, 'ativo');

  -- no opt-out yet: nothing to lift, nothing written
  v_r := agents.reativar_lead(v_org, 'social-wiring', 'l-1', v_op, 'voltou');
  IF NOT (v_r->>'encontrado')::boolean OR (v_r->>'reativado')::boolean THEN RAISE EXCEPTION 'no opt-out: %', v_r; END IF;
  IF EXISTS (SELECT 1 FROM agents.lead_opt_out_eventos WHERE lead_ref_id = v_lead) THEN RAISE EXCEPTION 'event written'; END IF;

  -- unknown lead
  IF (agents.reativar_lead(v_org, 'social-wiring', 'ninguem', v_op, 'x')->>'encontrado')::boolean THEN
    RAISE EXCEPTION 'unknown lead found';
  END IF;

  PERFORM agents.registrar_opt_out(v_org, 'social-wiring', 'l-1', now());
  v_r := agents.reativar_lead(v_org, 'social-wiring', 'l-1', v_op, '  Cliente pediu para voltar  ');
  IF NOT (v_r->>'reativado')::boolean THEN RAISE EXCEPTION 'not reactivated: %', v_r; END IF;
  IF NOT EXISTS (
      SELECT 1 FROM agents.lead_refs WHERE id = v_lead AND opt_in_origem = 'reativacao_manual' AND opt_in_em >= opt_out_em
  ) THEN RAISE EXCEPTION 'opt-out not lifted'; END IF;
  IF NOT EXISTS (
      SELECT 1 FROM agents.lead_opt_out_eventos WHERE id = (v_r->>'evento_id')::uuid AND tipo = 'reativacao'
         AND origem = 'operador' AND ator_user_id = v_op AND motivo = 'Cliente pediu para voltar'
  ) THEN RAISE EXCEPTION 'reactivation event wrong'; END IF;
  -- the participation stays ended: the lead's next message reopens it (controles), the RPC moves nobody
  IF (SELECT estado FROM agents.thread_participantes WHERE thread_id = v_thread) <> 'encerrado' THEN
    RAISE EXCEPTION 'participant moved';
  END IF;

  -- lifted already: a second call writes nothing
  v_r2 := agents.reativar_lead(v_org, 'social-wiring', 'l-1', v_op, 'de novo');
  IF (v_r2->>'reativado')::boolean THEN RAISE EXCEPTION 'second reactivation'; END IF;

  -- a later opt-out is a NEW opt_out event, not the reactivation mistaken for "already in force"
  v_r2 := agents.registrar_opt_out(v_org, 'social-wiring', 'l-1', now() + interval '2 seconds', 'agente', 'pediu', NULL, v_agent, v_thread, NULL);
  IF NOT (v_r2->>'evento_novo')::boolean OR
     (SELECT tipo FROM agents.lead_opt_out_eventos WHERE id = (v_r2->>'evento_id')::uuid) <> 'opt_out' THEN
    RAISE EXCEPTION 'new opt-out event expected: %', v_r2;
  END IF;
  RAISE EXCEPTION 'NOC_BEHAVIOUR_OK';
END
$t$;
"""


def test_the_043_probes_are_registered():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert len(_PROBES) == 2
    for p in _PROBES:
        assert by_id[p.id] is p and p.product == "agents"


def test_043_probes_are_refused_and_the_rpc_behaves_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    for p in _PROBES:
        steps.append({"product": "agents", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    steps.append({"product": "agents", "file": "behaviour", "sql": _BEHAVIOUR, "mode": "file",
                  "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] in {p.id for p in _PROBES}:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    bad = {k: v for k, v in out.items() if v != "refused"}
    assert not bad and len(out) == len(_PROBES), bad
    beh = next(st for st in res["steps"] if st["file"] == "behaviour")
    assert beh["failures"] and "NOC_BEHAVIOUR_OK" in beh["failures"][0]["error"], beh["failures"]
