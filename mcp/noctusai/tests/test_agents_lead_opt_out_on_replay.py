"""Agents 042 (a lead that asks to stop is never dropped silently) on the REAL core + agents chain on PGlite:
the new GuardProbes are refused, the extended `registrar_opt_out` keeps its 4-argument call shape, writes the event
in the same transaction, is idempotent (no second event while the opt-out is in force) and ends every agent."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = tuple(p for p in vdg._AGENTS_JULIA_V2_PROBES if p.migrations == (vdg._m("042"),))
_MIGS = {"products/agents/backend/migrations/042_julia_v2_lead_opt_out_eventos.sql",
         *{f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}}

_BEHAVIOUR = """
DO $t$
DECLARE
  v_org uuid := gen_random_uuid(); v_agent uuid; v_lead uuid; v_thread uuid; v_r jsonb; v_r2 jsonb; v_n int;
BEGIN
  INSERT INTO agents.agents (org_id, key, nome, runtime, definition_mode)
    VALUES (v_org, 'noc-opt-out', 'NOC', 'claude_sdk', 'studio') RETURNING id INTO v_agent;
  INSERT INTO agents.lead_refs (org_id, produto, ref_externa) VALUES (v_org, 'social-wiring', 'l-1') RETURNING id INTO v_lead;
  INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, tipo, channel, channel_ref, lead_ref_id)
    VALUES (v_org, v_agent, v_org, 'thread_lead', 'whatsapp', jsonb_build_object('chat_id', 'c1'), v_lead) RETURNING id INTO v_thread;
  INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado) VALUES (v_thread, v_agent, v_org, 'ativo');

  -- the OLD 4-argument call shape still works and writes the default event
  v_r := agents.registrar_opt_out(v_org, 'social-wiring', 'l-1', now());
  IF NOT (v_r->>'encontrado')::boolean OR (v_r->>'participantes_encerrados')::int <> 1 OR NOT (v_r->>'evento_novo')::boolean THEN
    RAISE EXCEPTION 'first opt-out: %', v_r;
  END IF;
  IF (SELECT motivo FROM agents.lead_opt_out_eventos WHERE id = (v_r->>'evento_id')::uuid) <> 'nao_informado' THEN
    RAISE EXCEPTION 'default motive';
  END IF;
  IF (SELECT estado FROM agents.thread_participantes WHERE thread_id = v_thread) <> 'encerrado' THEN
    RAISE EXCEPTION 'participant not ended';
  END IF;

  -- idempotent while in force: no second event, same id
  v_r2 := agents.registrar_opt_out(v_org, 'social-wiring', 'l-1', now(), 'agente', 'de novo', 'pare', v_agent, v_thread, NULL);
  IF (v_r2->>'evento_novo')::boolean OR v_r2->>'evento_id' <> v_r->>'evento_id' THEN
    RAISE EXCEPTION 'second opt-out recorded a new event: %', v_r2;
  END IF;
  SELECT count(*) INTO v_n FROM agents.lead_opt_out_eventos WHERE lead_ref_id = v_lead;
  IF v_n <> 1 THEN RAISE EXCEPTION 'expected 1 event, got %', v_n; END IF;

  -- an opt-in lifts it; a new opt-out is a NEW event carrying who / why / the lead's words
  UPDATE agents.lead_refs SET opt_in_em = now() + interval '1 second', opt_in_origem = 'lead_iniciou' WHERE id = v_lead;
  v_r2 := agents.registrar_opt_out(v_org, 'social-wiring', 'l-1', now() + interval '2 seconds', 'agente', 'pediu', 'pare', v_agent, v_thread, NULL);
  IF NOT (v_r2->>'evento_novo')::boolean THEN RAISE EXCEPTION 'new event after opt-in expected'; END IF;
  IF (SELECT mensagem_lead FROM agents.lead_opt_out_eventos WHERE id = (v_r2->>'evento_id')::uuid) <> 'pare' THEN
    RAISE EXCEPTION 'lead words';
  END IF;

  -- unknown lead
  IF (agents.registrar_opt_out(v_org, 'social-wiring', 'ninguem', now())->>'encontrado')::boolean THEN
    RAISE EXCEPTION 'unknown lead found';
  END IF;

  -- erasing the lead takes its events with it
  DELETE FROM agents.lead_refs WHERE id = v_lead;
  IF EXISTS (SELECT 1 FROM agents.lead_opt_out_eventos WHERE org_id = v_org) THEN RAISE EXCEPTION 'events survived the lead'; END IF;
  RAISE EXCEPTION 'NOC_BEHAVIOUR_OK';
END
$t$;
"""


def test_the_042_probes_are_registered():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert len(_PROBES) == 5
    for p in _PROBES:
        assert by_id[p.id] is p and p.product == "agents"


def test_042_probes_are_refused_and_the_rpc_behaves_on_the_real_chain(pglite):
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
