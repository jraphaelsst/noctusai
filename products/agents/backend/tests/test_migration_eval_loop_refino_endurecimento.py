"""Migration 093: the refine hardening -- the checks the database makes by itself, the two new events and the atomic human review."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.studio_eval_refino import MAX_REFINOS_POR_LOOP as MAX_STORE
from app.studio.eval_loop_refino import EVENTOS_REFINO, MAX_REFINOS_POR_LOOP
from app.studio.eval_loop_refino_protegido import PADRAO_FERRAMENTA_SQL, PADRAO_SECAO_SQL

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_loop_refino_endurecimento")
APLICAR = SQL[SQL.index("CREATE OR REPLACE FUNCTION agents.aplicar_refinamento_loop("):SQL.index("-- 4 . the human review")]
REVISAR = SQL[SQL.index("CREATE OR REPLACE FUNCTION agents.revisar_refinamento_loop("):]


def test_the_events_check_is_the_full_vocabulary_of_the_app():
    corpo = SQL[SQL.index("ADD CONSTRAINT eval_loop_eventos_evento_check"):SQL.index("-- 2 .")]
    eventos = {t.strip().strip("'") for t in corpo.split("IN (")[1].split(")")[0].replace("\n", "").split(",")}
    assert set(EVENTOS_REFINO) <= eventos and len(eventos) == 15


def test_one_decision_per_round_counts_no_edit_and_one_review_per_round():
    assert "WHERE evento IN ('refinamento_proposto', 'refinamento_recusado', 'refinamento_sem_edicao')" in SQL
    assert "uq_agents_eval_loop_eventos_revisao_por_rodada" in SQL and "WHERE evento = 'refinamento_revisado'" in SQL


def test_the_old_unguarded_signature_is_dropped_and_the_new_one_is_service_role_only():
    assert "DROP FUNCTION IF EXISTS agents.aplicar_refinamento_loop(UUID, UUID, INT, TEXT, JSONB, NUMERIC, UUID, TEXT, TEXT, TEXT, TEXT, TEXT);" in SQL
    for fn in ("aplicar_refinamento_loop", "revisar_refinamento_loop"):
        assert f"REVOKE ALL ON FUNCTION agents.{fn}(" in SQL and "FROM PUBLIC, anon, authenticated" in SQL
        assert f"GRANT EXECUTE ON FUNCTION agents.{fn}(" in SQL
    assert "TO authenticated" not in SQL and SQL.count("SECURITY DEFINER") == 2 and SQL.count("SET search_path = agents, public") >= 3


def test_the_database_refuses_by_itself_a_foreign_version_a_base_layer_a_protective_row_and_the_caps():
    for codigo in ("versao_de_outro_agente", "camada_base", "linha_protegida", "limite_de_refinos", "linha_ja_refinada"):
        assert f"RAISE EXCEPTION '{codigo}'" in APLICAR, codigo
    assert "v_ver_agent IS DISTINCT FROM v_loop_agent" in APLICAR
    assert "v_scope = 'plataforma'" in APLICAR and "a.pai_agent_id = v_loop_agent" in APLICAR
    assert "cardinality(v_regras) > 0" in APLICAR and "cardinality(regras) = 0" in APLICAR  # regras <> '{}' never edited
    assert "= ANY (COALESCE(p_protegidas" in APLICAR
    assert "IF v_n >= 3 THEN" in APLICAR and MAX_REFINOS_POR_LOOP == MAX_STORE == 3
    # every protective refusal runs BEFORE the compare-and-set and before any write
    assert APLICAR.index("'linha_protegida'") < APLICAR.index("p_expected_hash THEN") < APLICAR.index("UPDATE agents.agent_prompt_sections")


def test_the_sql_key_patterns_are_the_ones_the_app_validator_reads():
    assert f"lower(p_chave) ~ '{PADRAO_SECAO_SQL}'" in APLICAR
    assert f"lower(p_chave) ~ '{PADRAO_FERRAMENTA_SQL}'" in APLICAR
    for chave in ("opt-out", "seguranca", "transferencia", "identidade-e-privacidade", "honestidade"):
        assert re.search(PADRAO_SECAO_SQL, chave), chave
    for nome in ("handoff", "encerrar", "registrar_solicitacao_titular", "consentimento_credito"):
        assert re.search(PADRAO_FERRAMENTA_SQL, nome), nome


def test_the_review_is_one_transaction_with_the_same_compare_and_set_and_an_actor():
    assert "'aceito', 'revertido'" in REVISAR and "p_ator IS NULL" in REVISAR
    for codigo in ("refino_nao_encontrado", "refino_ja_revisado", "versao_de_outro_agente", "conflito_de_versao", "linha_alterada", "version_immutable"):
        assert f"RAISE EXCEPTION '{codigo}'" in REVISAR, codigo
    assert REVISAR.index("v_hash IS DISTINCT FROM p_expected_hash") < REVISAR.index("UPDATE agents.agent_prompt_sections") < REVISAR.index(
        "INSERT INTO agents.eval_loop_eventos")
    assert "conteudo = p_antes" in REVISAR and "descricao = p_antes" in REVISAR  # the row must still hold the edit
    assert "'refinamento_revisado'" in REVISAR and "ator)" in REVISAR and "jsonb_build_object('decisao', p_decisao)" in REVISAR
    assert "DELETE" not in SQL[SQL.index("CREATE OR REPLACE FUNCTION"):]
