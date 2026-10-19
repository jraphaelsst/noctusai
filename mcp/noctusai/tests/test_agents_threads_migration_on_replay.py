"""Agents 033/034 (shared Julia thread + controls) on the REAL core + agents chain on PGlite, over prod-shaped rows.

`products/agents/backend/migration-replay.json` inserts two Julia channel conversations and one Bia user conversation
just before 033. The replay applies 033 / 034 / 035 each TWICE (idempotency: the M2 backfill must not duplicate a
participant nor rewrite a row), then every assertion below runs as a SQL step that RAISES on a mismatch -- so a red here
names the property that broke:

* the M2 backfill: channel conversations become threads, the agent is the ACTIVE participant, assistant messages carry
  their author, a user conversation is untouched, the last-lead-message clock is derived from the messages;
* one ACTIVE participant per thread (the partial unique index), the participant state function (compare-and-set +
  event + audit), the role CHECK;
* the controls: an active agent stays on (ligado), a new one is off, ativo mirrors modo both ways, the audit trigger
  fires, the audit CHECK accepts the new actions;
* LGPD: apagar_lead erases every thread of the lead across agents and is idempotent; the retention purge drops an
  orphaned lead_ref.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_A = "a0000000-0000-4000-8000-00000000000a"
_JULIA = "a1000000-0000-4000-8000-000000000001"
_BIA = "a2000000-0000-4000-8000-000000000002"
_C1 = "c1000000-0000-4000-8000-000000000001"
_C2 = "c2000000-0000-4000-8000-000000000002"
_C3 = "c3000000-0000-4000-8000-000000000003"
_TARGETS = {
    f"products/agents/backend/migrations/{n}"
    for n in ("033_julia_v2_threads.sql", "034_julia_v2_controles.sql", "035_julia_v2_threads_constraints.sql")
}
_PREFIXES = ("assert:", "step:")


def _check(name: str, condition: str) -> dict:
    sql = f"DO $chk$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'ASSERT {name}'; END IF; END $chk$;"
    return {"product": "agents", "file": f"assert:{name}", "sql": sql, "mode": "file", "twice": False}


def _step(name: str, sql: str) -> dict:
    return {"product": "agents", "file": f"step:{name}", "sql": sql, "mode": "file", "twice": False}


def _expect_refused(sql: str, what: str) -> str:
    """A DO block that RAISES when `sql` is NOT refused (any error from `sql` counts as the refusal)."""
    return f"""
DO $t$ BEGIN
  BEGIN
    {sql}
    RAISE EXCEPTION 'ASSERT not refused: {what}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'ASSERT not refused%' THEN RAISE; END IF;
  END;
END $t$;"""


ASSERTIONS = [
    # --- M2 backfill ---------------------------------------------------------------------------------------------
    _check("channel_conversations_are_threads", "(SELECT count(*) FROM agents.conversations WHERE tipo = 'thread_lead') = 2"),
    _check("user_conversation_stays_chat", f"(SELECT tipo FROM agents.conversations WHERE id = '{_C3}') = 'chat'"),
    _check("each_thread_has_exactly_its_agent_as_active_participant",
           f"(SELECT count(*) FROM agents.thread_participantes WHERE estado = 'ativo' AND agent_id = '{_JULIA}') = 2 "
           "AND (SELECT count(*) FROM agents.thread_participantes) = 2"),
    _check("backfill_is_idempotent_no_duplicate_participant",
           "(SELECT count(*) FROM (SELECT thread_id, agent_id FROM agents.thread_participantes GROUP BY 1, 2 HAVING count(*) > 1) d) = 0"),
    _check("assistant_messages_carry_their_author",
           f"(SELECT agent_id FROM agents.messages WHERE id = 'd2000000-0000-4000-8000-000000000002') = '{_JULIA}' "
           f"AND (SELECT agent_id FROM agents.messages WHERE id = 'd4000000-0000-4000-8000-000000000004') IS NULL "
           "AND (SELECT count(*) FROM agents.messages WHERE role = 'user' AND agent_id IS NOT NULL) = 0"),
    _check("last_lead_message_clock_is_derived_from_the_messages",
           f"(SELECT ultima_mensagem_lead_em FROM agents.conversations WHERE id = '{_C1}') = '2026-10-10T12:00:00Z' "
           f"AND (SELECT ultima_mensagem_lead_em FROM agents.conversations WHERE id = '{_C2}') IS NULL"),
    _check("no_message_lost", "(SELECT count(*) FROM agents.messages) = 4"),
    # --- constraints -----------------------------------------------------------------------------------------------
    _step("a_second_active_participant_is_refused", _expect_refused(
        f"INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado) VALUES ('{_C1}', '{_BIA}', '{_A}', 'ativo');",
        "second ACTIVE participant on a thread")),
    _step("a_paused_second_participant_is_allowed", f"""
DO $t$ BEGIN
  INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado) VALUES ('{_C1}', '{_BIA}', '{_A}', 'concluido');
  DELETE FROM agents.thread_participantes WHERE thread_id = '{_C1}' AND agent_id = '{_BIA}';
END $t$;"""),
    _step("message_role_check_accepts_humano_and_evento_and_refuses_the_rest", f"""
DO $t$ BEGIN
  INSERT INTO agents.messages (org_id, conversation_id, role, texto, autor_user_id) VALUES ('{_A}', '{_C1}', 'humano', 'atendente', '{_A}');
  INSERT INTO agents.messages (org_id, conversation_id, role, texto) VALUES ('{_A}', '{_C1}', 'evento', 'handoff');
  DELETE FROM agents.messages WHERE role IN ('humano', 'evento');
END $t$;"""
          + _expect_refused(
              f"INSERT INTO agents.messages (org_id, conversation_id, role, texto) VALUES ('{_A}', '{_C1}', 'robo', 'x');", "an unknown role")),
    _step("tipo_thread_requires_a_channel", _expect_refused(
        f"UPDATE agents.conversations SET tipo = 'thread_lead' WHERE id = '{_C3}';", "a user conversation turned thread_lead")),
    # --- 035 (M4) ---
    _step("m4_a_thread_without_a_lead_is_refused", _expect_refused(
        f"INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, channel, channel_ref, tipo) "
        f"VALUES ('{_A}', '{_JULIA}', NULL, 'whatsapp', '{{\"chat_id\": \"sem-lead\"}}', 'thread_lead');",
        "a thread_lead with no lead_ref")),
    _step("m4_the_thread_identity_no_longer_includes_the_agent", _expect_refused(
        f"INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, channel, channel_ref, tipo, lead_ref_id) "
        f"SELECT org_id, '{_BIA}', NULL, channel, channel_ref, tipo, lead_ref_id FROM agents.conversations WHERE id = '{_C1}';",
        "a second thread for the same (org, channel, channel_ref) under another agent")),
    _check("m4_dropped_the_per_agent_identity_index", "to_regclass('agents.uq_agents_conversations_channel_ref') IS NULL"),
    # --- participant state function -------------------------------------------------------------------------------
    _step("pause_resume_is_compare_and_set_and_audited", f"""
DO $t$ DECLARE r boolean; BEGIN
  r := agents.set_participante_estado('{_A}', '{_C1}', '{_JULIA}', ARRAY['ativo'], 'pausado', 'usuario', '{_A}', 'atendente assumiu');
  IF NOT r THEN RAISE EXCEPTION 'ASSERT pause should move an ativo participant'; END IF;
  r := agents.set_participante_estado('{_A}', '{_C1}', '{_JULIA}', ARRAY['ativo'], 'pausado', 'usuario', '{_A}', 'again');
  IF r THEN RAISE EXCEPTION 'ASSERT a stale compare-and-set must not move the participant'; END IF;
  r := agents.set_participante_estado('{_A}', '{_C1}', '{_JULIA}', ARRAY['pausado'], 'ativo', 'usuario', '{_A}', 'voltou');
  IF NOT r THEN RAISE EXCEPTION 'ASSERT resume should move a pausado participant'; END IF;
  IF (SELECT count(*) FROM agents.thread_participante_eventos WHERE thread_id = '{_C1}') <> 2 THEN
    RAISE EXCEPTION 'ASSERT one event row per real transition';
  END IF;
  IF (SELECT count(*) FROM agents.agent_audit_log WHERE acao = 'conversa_pausada') <> 1
     OR (SELECT count(*) FROM agents.agent_audit_log WHERE acao = 'conversa_retomada') <> 1 THEN
    RAISE EXCEPTION 'ASSERT pause and resume must each land in agent_audit_log';
  END IF;
END $t$;"""),
    _step("encerrado_stamps_saiu_em_and_ativo_clears_it", f"""
DO $t$ BEGIN
  PERFORM agents.set_participante_estado('{_A}', '{_C2}', '{_JULIA}', ARRAY['ativo'], 'encerrado', 'sistema', NULL, 'dreno_inativo');
  IF (SELECT saiu_em IS NULL FROM agents.thread_participantes WHERE thread_id = '{_C2}') THEN
    RAISE EXCEPTION 'ASSERT encerrado must stamp saiu_em';
  END IF;
  PERFORM agents.set_participante_estado('{_A}', '{_C2}', '{_JULIA}', ARRAY['encerrado'], 'ativo', 'sistema', NULL, 'reaberta');
  IF (SELECT saiu_em IS NOT NULL FROM agents.thread_participantes WHERE thread_id = '{_C2}') THEN
    RAISE EXCEPTION 'ASSERT reopening must clear saiu_em';
  END IF;
END $t$;"""),
    # --- controls (034) --------------------------------------------------------------------------------------------
    _check("an_agent_active_today_stays_on", f"(SELECT modo_operacao FROM agents.agents WHERE id = '{_JULIA}') = 'ligado'"),
    _check("an_inactive_agent_stays_off", f"(SELECT modo_operacao FROM agents.agents WHERE id = '{_BIA}') = 'desligado'"),
    _check("dreno_default_is_seven_days", f"(SELECT dreno_inatividade_dias FROM agents.agents WHERE id = '{_JULIA}') = 7"),
    _step("ativo_mirrors_modo_both_ways_and_modo_changes_are_audited", f"""
DO $t$ BEGIN
  PERFORM agents.set_agent_modo('{_A}', '{_JULIA}', 'drenando', 3, '{_A}');
  IF NOT (SELECT ativo AND modo_operacao = 'drenando' AND dreno_inatividade_dias = 3 FROM agents.agents WHERE id = '{_JULIA}') THEN
    RAISE EXCEPTION 'ASSERT drenando keeps ativo true and stores the idle days';
  END IF;
  PERFORM agents.set_agent_modo('{_A}', '{_JULIA}', 'desligado', NULL, '{_A}');
  IF (SELECT ativo FROM agents.agents WHERE id = '{_JULIA}') OR (SELECT dreno_inatividade_dias FROM agents.agents WHERE id = '{_JULIA}') <> 3 THEN
    RAISE EXCEPTION 'ASSERT desligado sets ativo false and a NULL idle days keeps the value';
  END IF;
  UPDATE agents.agents SET ativo = true WHERE id = '{_JULIA}';
  IF (SELECT modo_operacao FROM agents.agents WHERE id = '{_JULIA}') <> 'ligado' THEN
    RAISE EXCEPTION 'ASSERT a legacy ativo=true writer turns an off agent ligado';
  END IF;
  UPDATE agents.agents SET ativo = false WHERE id = '{_JULIA}';
  IF (SELECT modo_operacao FROM agents.agents WHERE id = '{_JULIA}') <> 'desligado' THEN
    RAISE EXCEPTION 'ASSERT a legacy ativo=false writer turns the agent desligado';
  END IF;
  IF (SELECT count(*) FROM agents.agent_audit_log WHERE acao = 'modo_alterado' AND agent_id = '{_JULIA}') < 4 THEN
    RAISE EXCEPTION 'ASSERT every modo change is audited whatever the write path';
  END IF;
  IF (SELECT actor FROM agents.agent_audit_log WHERE acao = 'modo_alterado' AND agent_id = '{_JULIA}' ORDER BY created_at LIMIT 1) <> '{_A}' THEN
    RAISE EXCEPTION 'ASSERT set_agent_modo attributes the actor';
  END IF;
  PERFORM agents.set_agent_modo('{_A}', '{_JULIA}', 'ligado', NULL, '{_A}');
END $t$;"""),
    _step("set_agent_modo_refuses_a_bad_mode_and_a_bad_days_and_an_unknown_agent", _expect_refused(
        f"PERFORM agents.set_agent_modo('{_A}', '{_JULIA}', 'pausado', NULL, NULL);", "unknown mode")
          + _expect_refused(f"PERFORM agents.set_agent_modo('{_A}', '{_JULIA}', 'ligado', 0, NULL);", "0 idle days")
          + _expect_refused(f"PERFORM agents.set_agent_modo('{_A}', gen_random_uuid(), 'ligado', NULL, NULL);", "unknown agent")),
    # --- LGPD: delete-by-lead across agents ------------------------------------------------------------------------
    _step("apagar_lead_erases_every_thread_of_the_lead_across_agents_and_is_idempotent", f"""
DO $t$ DECLARE lead uuid; r jsonb; BEGIN
  SELECT id INTO lead FROM agents.lead_refs WHERE ref_externa = 'contato-1';
  INSERT INTO agents.messages (org_id, conversation_id, role, texto, agent_id, lead_ref_id) VALUES ('{_A}', '{_C1}', 'assistant', 'do outro agente', '{_BIA}', lead);
  INSERT INTO agents.thread_participantes (thread_id, agent_id, org_id, estado) VALUES ('{_C1}', '{_BIA}', '{_A}', 'concluido');
  INSERT INTO agents.thread_skill_aberturas (thread_id, org_id, skill, compiled_hash) VALUES ('{_C1}', '{_A}', 'qualificar', 'sha256:x');
  INSERT INTO agents.agent_message_feedback (org_id, message_id, nota, origem)
    SELECT '{_A}', id, 'like', 'sw' FROM agents.messages WHERE conversation_id = '{_C1}' AND role = 'assistant' LIMIT 1;
  r := agents.apagar_lead('{_A}', 'social-wiring', 'contato-1');
  IF NOT (r->>'encontrado')::boolean OR (r->>'threads')::int <> 2 THEN RAISE EXCEPTION 'ASSERT apagar_lead must report both threads, got %', r; END IF;
  IF EXISTS (SELECT 1 FROM agents.conversations WHERE id IN ('{_C1}', '{_C2}'))
     OR EXISTS (SELECT 1 FROM agents.messages WHERE conversation_id IN ('{_C1}', '{_C2}'))
     OR EXISTS (SELECT 1 FROM agents.thread_participantes WHERE thread_id IN ('{_C1}', '{_C2}'))
     OR EXISTS (SELECT 1 FROM agents.thread_participante_eventos WHERE thread_id IN ('{_C1}', '{_C2}'))
     OR EXISTS (SELECT 1 FROM agents.thread_skill_aberturas)
     OR EXISTS (SELECT 1 FROM agents.agent_message_feedback)
     OR EXISTS (SELECT 1 FROM agents.lead_refs WHERE id = lead) THEN
    RAISE EXCEPTION 'ASSERT apagar_lead left lead data behind';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agents.conversations WHERE id = '{_C3}') OR (SELECT count(*) FROM agents.messages WHERE conversation_id = '{_C3}') <> 1 THEN
    RAISE EXCEPTION 'ASSERT apagar_lead must not touch another conversation';
  END IF;
  r := agents.apagar_lead('{_A}', 'social-wiring', 'contato-1');
  IF (r->>'encontrado')::boolean THEN RAISE EXCEPTION 'ASSERT a second erase must be a no-op'; END IF;
END $t$;"""),
    _step("purge_drops_the_lead_ref_with_its_last_thread", f"""
DO $t$ DECLARE lead uuid; c uuid; BEGIN
  INSERT INTO agents.lead_refs (org_id, produto, ref_externa) VALUES ('{_A}', 'social-wiring', 'contato-2') RETURNING id INTO lead;
  INSERT INTO agents.conversations (org_id, agent_id, owner_user_id, channel, channel_ref, tipo, lead_ref_id, created_at)
    VALUES ('{_A}', '{_JULIA}', NULL, 'whatsapp', '{{"chat_id": "velho"}}', 'thread_lead', lead, '2020-01-01') RETURNING id INTO c;
  IF agents.purge_channel_conversations('2021-01-01') <> 1 THEN RAISE EXCEPTION 'ASSERT purge should remove exactly the old thread'; END IF;
  IF EXISTS (SELECT 1 FROM agents.lead_refs WHERE id = lead) THEN RAISE EXCEPTION 'ASSERT the orphaned lead_ref must go with its last thread'; END IF;
END $t$;"""),
]


def test_threads_and_controls_migrations_keep_every_row_and_hold_their_invariants_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "agents", set(_TARGETS), "worktree", {})
    assert any(s["file"] == "fixture:033_julia_v2_threads.sql" for s in steps), "the prod-shaped fixture must be replayed"
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    for target in ("033_julia_v2_threads.sql", "034_julia_v2_controles.sql", "035_julia_v2_threads_constraints.sql"):
        assert not by_file[("agents", target)]["failures"], (target, by_file[("agents", target)]["failures"])
    assert not by_file[("agents", "fixture:033_julia_v2_threads.sql")]["failures"], by_file[("agents", "fixture:033_julia_v2_threads.sql")]["failures"]
    failed = {name: s["failures"][0]["error"] for (prod, name), s in by_file.items() if prod == "agents" and name.startswith(_PREFIXES) and s["failures"]}
    assert not failed, failed
    ran = [name for (prod, name) in by_file if prod == "agents" and name.startswith(_PREFIXES)]
    assert len(ran) == len(ASSERTIONS), "every assertion step must have run"
