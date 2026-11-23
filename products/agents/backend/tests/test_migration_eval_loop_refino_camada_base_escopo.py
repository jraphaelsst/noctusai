"""Migration 094: platform scope alone is no longer a base layer for the refine; a parent of another agent still is."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "eval_loop_refino_camada_base_escopo")


def test_only_the_parent_of_another_agent_is_a_base_layer():
    assert "v_scope = 'plataforma'" not in SQL.split("RAISE EXCEPTION 'camada_base'")[0].split("CREATE OR REPLACE")[1]
    assert "EXISTS (SELECT 1 FROM agents.agents a WHERE a.pai_agent_id = v_loop_agent)" in SQL
    assert "RAISE EXCEPTION 'camada_base'" in SQL


def test_every_other_093_guard_and_the_grants_are_kept():
    for codigo in ("versao_de_outro_agente", "linha_protegida", "limite_de_refinos", "linha_ja_refinada"):
        assert f"RAISE EXCEPTION '{codigo}'" in SQL, codigo
    assert SQL.count("\nSECURITY DEFINER") == 1 and "SET search_path = agents, public" in SQL
    assert "FROM PUBLIC, anon, authenticated" in SQL and "TO service_role" in SQL and "TO authenticated" not in SQL
