"""Structural pins for migrations 033/034/035 (Julia v2 A-THREAD). The behaviour is proven on a real Postgres by the
chain replay (mcp/noctusai/tests/test_agents_threads_migration_on_replay.py); these keep the intent honest against
the Python side and the security posture (lead data is service-role only)."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[1]
M33 = migration_sql(ROOT, "julia_v2_threads")
M34 = migration_sql(ROOT, "julia_v2_controles")
M35 = migration_sql(ROOT, "julia_v2_threads_constraints")

NEW_TABLES = (
    "lead_refs", "thread_participantes", "thread_participante_eventos", "thread_handoffs",
    "thread_skill_aberturas", "agent_message_feedback",
)
NEW_FUNCTIONS = (
    ("set_participante_estado", "UUID, UUID, UUID, TEXT[], TEXT, TEXT, UUID, TEXT, TIMESTAMPTZ"),
    ("apagar_lead", "UUID, TEXT, TEXT"),
    ("registrar_opt_out", "UUID, TEXT, TEXT, TIMESTAMPTZ"),
    ("transferir_thread", "UUID, UUID, UUID, TEXT[], TEXT, TEXT, UUID, UUID, TEXT, TEXT, TEXT, JSONB, JSONB, TEXT, UUID, JSONB, BOOLEAN, JSONB"),
)


def test_every_new_table_is_service_role_only_and_hidden_from_authenticated():
    for t in NEW_TABLES:
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in M33, t
        assert re.search(rf'ON agents\.{t}\s+FOR ALL TO service_role', M33), t
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated" in M33, t


def test_every_new_function_is_secdef_with_execute_revoked_from_public_and_granted_to_service_role_only():
    flat = " ".join(M33.split())
    for fn, sig in NEW_FUNCTIONS:
        assert f"FUNCTION agents.{fn}(" in M33, fn
        assert f"REVOKE ALL ON FUNCTION agents.{fn}({sig}) FROM PUBLIC, anon, authenticated" in flat, fn
        assert f"GRANT EXECUTE ON FUNCTION agents.{fn}({sig}) TO service_role" in flat, fn
    for fn in ("set_agent_modo", "sync_agent_modo_ativo", "audit_agent_modo_change"):
        assert re.search(rf"REVOKE ALL ON FUNCTION agents\.{fn}\([^)]*\) FROM PUBLIC, anon, authenticated", M34), fn


def test_one_active_participant_per_thread_is_a_partial_unique_index():
    assert re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_thread_participantes_one_active\s+"
        r"ON agents\.thread_participantes \(thread_id\)\s+WHERE estado = 'ativo'", M33)


def test_message_roles_and_the_version_stamp():
    assert "CHECK (role IN ('user', 'assistant', 'system', 'humano', 'evento'))" in M33
    for col in ("agent_id", "lead_ref_id", "autor_user_id", "definition_version_id", "org_specs_hash", "skill_version_ids"):
        assert f"ADD COLUMN IF NOT EXISTS {col} " in M33, col


def test_a_handoff_never_carries_a_raw_document_number():
    block = M33[M33.index("CREATE TABLE IF NOT EXISTS agents.thread_handoffs"):]
    block = block[: block.index(");\n\nALTER TABLE")]
    assert "identificacao_mascarada" in block and "identificacao_completa" in block
    assert not re.search(r"\b(cpf|rg)\b\s+TEXT", block, re.I)


def test_delete_by_lead_and_the_purge_cascade_to_the_lead_ref():
    apagar = M33[M33.index("FUNCTION agents.apagar_lead("):]
    apagar = apagar[: apagar.index("$$;", apagar.index("AS $$"))]
    for table in ("agents.messages", "agents.approvals", "agents.channel_inbound", "agents.conversations", "agents.lead_refs"):
        assert f"DELETE FROM {table}" in apagar, table
    purge = M33[M33.index("FUNCTION agents.purge_channel_conversations("):]
    assert "DELETE FROM agents.lead_refs" in purge and "NOT EXISTS" in purge


def test_the_audit_check_lists_every_action_both_slices_need():
    block = M34[M34.index("ADD CONSTRAINT agent_audit_log_acao_check"):]
    for acao in ("limiar_alterado", "publicado", "publicado_override", "rascunho_descartado", "modo_alterado",
                 "conversa_pausada", "conversa_retomada", "conteudo_editado_mcp", "padrao_publicado"):
        assert f"'{acao}'" in block, acao


def test_an_agent_that_is_active_today_stays_on_and_a_new_one_is_off():
    assert "modo_operacao TEXT NOT NULL DEFAULT 'desligado'" in M34
    assert re.search(r"UPDATE agents\.agents\s+SET modo_operacao = 'ligado'\s+WHERE ativo", M34)
    assert M34.index("SET modo_operacao = 'ligado'") < M34.index("CREATE TRIGGER sync_agent_modo_ativo")


def test_the_audit_trigger_has_no_column_list_so_a_legacy_ativo_write_is_audited_too():
    trig = M34[M34.index("CREATE TRIGGER audit_agent_modo_change"):]
    assert trig.startswith("CREATE TRIGGER audit_agent_modo_change\n    AFTER UPDATE ON agents.agents")


def test_035_refuses_loudly_when_applied_before_the_backfill_and_is_marked_so():
    assert M35.lstrip().splitlines()[2].startswith("-- 035") or "APPLY ONLY AFTER" in M35
    assert "APPLY ONLY AFTER THE M2 BACKFILL IS VERIFIED" in M35
    assert "RAISE EXCEPTION 'threads_nao_vinculadas" in M35 and "RAISE EXCEPTION 'threads_duplicadas" in M35
    assert M35.index("RAISE EXCEPTION 'threads_nao_vinculadas") < M35.index("CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_threads_channel")
    assert M35.index("CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_threads_channel") < M35.index("DROP INDEX IF EXISTS agents.uq_agents_conversations_channel_ref")
    assert "tipo <> 'thread_lead' OR (channel IS NOT NULL AND lead_ref_id IS NOT NULL)" in M35
