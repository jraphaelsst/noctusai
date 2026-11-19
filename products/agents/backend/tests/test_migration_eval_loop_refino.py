"""Migration 092: the refine events, the one-decision-per-round index and the atomic ``aplicar_refinamento_loop`` (edit + spend + event)."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.studio_eval_refino import SupabaseRefinoStore  # noqa: F401  (the RPC the store calls is the one declared below)

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_loop_refino")


def _lista(trecho: str) -> set[str]:
    return {t.strip().strip("'") for t in trecho.split("IN (")[1].split(")")[0].replace("\n", "").split(",")}


def test_the_events_check_keeps_the_088_events_and_adds_exactly_the_three_refine_events():
    corpo = SQL[SQL.index("ADD CONSTRAINT eval_loop_eventos_evento_check"):SQL.index("-- 2 .")]
    eventos = _lista(corpo)
    assert {"refinamento_proposto", "refinamento_recusado", "refinamento_avaliado"} <= eventos
    assert {"loop_iniciado", "rodada_aberta", "rodada_fechada", "rodada_com_erro", "run_com_erro", "preflight_recusado",
            "driver_aguardando", "driver_retomado", "loop_parado", "modo_alterado"} <= eventos
    assert len(eventos) == 13


def test_one_refine_decision_per_loop_and_round_is_a_unique_index():
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_eval_loop_eventos_refino_por_rodada" in SQL
    assert "(loop_id, rodada_seq)" in SQL and "WHERE evento IN ('refinamento_proposto', 'refinamento_recusado')" in SQL


def test_the_function_is_service_role_only_security_definer_with_a_pinned_search_path():
    assert "CREATE OR REPLACE FUNCTION agents.aplicar_refinamento_loop(" in SQL
    assert "SECURITY DEFINER" in SQL and "SET search_path = agents, public" in SQL
    assert "FROM PUBLIC, anon, authenticated" in SQL and "TO service_role" in SQL and "TO authenticated" not in SQL


def test_the_edit_is_a_targeted_update_guarded_by_the_draft_hash_and_the_rows_old_text_never_a_replace_set():
    assert "v_status <> 'rascunho'" in SQL and "v_hash IS DISTINCT FROM p_expected_hash" in SQL
    assert "conteudo = p_antes" in SQL and "descricao = p_antes" in SQL and "linha_alterada" in SQL
    assert "DELETE" not in SQL[SQL.index("CREATE OR REPLACE FUNCTION"):]  # the one-row UPDATE, not agents.replace_draft_*


def test_edit_spend_and_event_are_one_function_so_one_transaction():
    corpo = SQL[SQL.index("CREATE OR REPLACE FUNCTION"):]
    assert corpo.index("UPDATE agents.agent_prompt_sections") < corpo.index("UPDATE agents.eval_loops SET gasto_usd") < corpo.index(
        "INSERT INTO agents.eval_loop_eventos")
    assert "gasto_usd + p_custo_usd" in corpo
