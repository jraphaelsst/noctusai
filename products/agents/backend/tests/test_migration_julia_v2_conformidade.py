"""Structural pins for migration 037 (Julia v2 A-RT). The behaviour is proven on a real Postgres by the chain replay
(`noctus.dev.migration_replay`); these keep the intent honest: the new tables are service-role only, the erasure
functions raise the flag the append-only guard needs before the lead_ref FK cascades, and no content ships."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[1]
M37 = migration_sql(ROOT, "julia_v2_conformidade")
M32 = migration_sql(ROOT, "julia_v2_qualificacao")

TABLES = ("conformidade_regras", "conformidade_violacoes", "conformidade_impressoes", "canal_limites")
PER_LEAD = (
    "lead_qualificacao_registros", "lead_imovel_eventos", "lead_qualificacao_estado",
    "lead_qualificacao_confirmacoes", "lead_identificacao",
)


def test_every_new_table_is_service_role_only_and_hidden_from_authenticated():
    for t in TABLES:
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in M37, t
        assert re.search(rf'ON agents\.{t}\s+FOR ALL TO service_role', M37), t
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated" in M37, t


def test_the_per_lead_tables_get_the_lead_ref_foreign_key_with_cascade_and_it_is_validated():
    assert "FOREIGN KEY (lead_ref_id)" in M37 and "REFERENCES agents.lead_refs(id) ON DELETE CASCADE NOT VALID" in M37
    assert "VALIDATE CONSTRAINT" in M37
    for t in PER_LEAD:
        assert f"'{t}'" in M37, t
    # the access audit keeps NO FK / NO erasure exception (accountability outlives the lead; it holds no PII)
    assert "lead_identificacao_acessos'" not in M37


def test_the_functions_that_delete_a_lead_ref_raise_the_append_only_erasure_flag_around_it():
    assert "agents.erasing_lead_qualificacao" in M32  # the guard's flag (032)
    for fn in ("apagar_lead", "delete_channel_conversation", "purge_channel_conversations"):
        block = M37[M37.index(f"CREATE OR REPLACE FUNCTION agents.{fn}("):]
        block = block[: block.index("$$;\n", block.index("AS $$")) ]
        assert "set_config('agents.erasing_lead_qualificacao', 'on', true)" in block, fn
        assert block.index("'on'") < block.index("DELETE FROM agents.lead_refs"), fn
        assert "'off'" in block, fn


def test_a_handoff_may_end_the_giver_concluido():
    assert "p_para_estado NOT IN ('transferido', 'pausado', 'concluido')" in M37


def test_no_content_is_seeded_and_the_correction_text_is_a_registry_key_not_a_string():
    # D3: content is data written through the API / MCP tool, never a migration. The only INSERTs are the
    # hand-off function's own (the note and the receiving participant), not seed rows.
    inserts = re.findall(r"INSERT INTO (agents\.\w+)", M37)
    assert set(inserts) <= {"agents.thread_handoffs", "agents.thread_participantes", "agents.thread_participante_eventos"}
    assert "mensagem_correcao_texto_chave" in M37 and "~ '^[a-z0-9]+(\\.[a-z0-9_]+)+$'" in M37


def test_the_violation_row_holds_codes_and_counts_only():
    block = M37[M37.index("CREATE TABLE IF NOT EXISTS agents.conformidade_violacoes"):]
    block = block[: block.index(");")]
    assert "detalhe JSONB" in block and "texto" not in block.replace("detalhe", "")
