"""Structural pins for migration 032 (Julia v2 A-QUAL): ONE platform standard (no org
fork), immutable published versions, the pin on agent_versions, the append-only
per-lead tables (LGPD) and the erasure functions. The chain is replayed on a real
Postgres by ``noctus.dev.migration_replay``; these keep intent honest."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[2], "julia_v2_qualificacao")


def _table(name: str) -> str:
    start = SQL.index(f"CREATE TABLE IF NOT EXISTS agents.{name} (")
    return SQL[start: SQL.index("\n);", start)]


def test_the_standard_is_platform_wide_no_org_no_fork():
    for t in ("qualificacao_padroes", "qualificacao_versoes", "qualificacao_criterios",
              "qualificacao_estagios", "qualificacao_parametros"):
        assert "org_id" not in _table(t), t
        assert "origem_padrao_id" not in _table(t), t
    assert "CONSTRAINT uq_qualificacao_padroes_chave UNIQUE (chave)" in SQL


def test_one_draft_per_standard_and_unique_keys():
    assert re.search(r"uq_qualificacao_versoes_um_rascunho\s+ON agents\.qualificacao_versoes \(padrao_id\) WHERE status = 'rascunho'", SQL)
    assert "UNIQUE (versao_id, chave)" in SQL and "UNIQUE (padrao_id, versao)" in SQL


def test_criterion_enums_match_the_contract():
    crit = _table("qualificacao_criterios")
    for g in ("prontidao", "bloqueios", "interesse", "perfil_imovel", "perfil_vida", "contato"):
        assert f"'{g}'" in crit
    for t in ("enum", "multi", "bool", "numero", "faixa", "texto", "imovel_ref"):
        assert f"'{t}'" in crit
    assert "sensivel IS NULL OR sensivel IN ('faixa', 'nao_coletar')" in crit
    assert "chave ~ '^[a-z][a-z0-9_]{1,63}$'" in crit
    assert "lote_ofertas INT NOT NULL DEFAULT 3 CHECK (lote_ofertas BETWEEN 1 AND 5)" in _table("qualificacao_parametros")
    assert "score_max INT NOT NULL DEFAULT 100" in _table("qualificacao_parametros")


def test_published_versions_and_children_are_immutable_by_trigger():
    assert "FUNCTION agents.guard_qualificacao_versao_immutable()" in SQL
    assert "FUNCTION agents.guard_qualificacao_filho_immutable()" in SQL
    for t in ("criterios", "estagios", "parametros"):
        assert re.search(
            rf"guard_qualificacao_{t}_immutable\s+BEFORE INSERT OR UPDATE OR DELETE ON agents\.qualificacao_{t}", SQL), t
    body = SQL[SQL.index("FUNCTION agents.guard_qualificacao_versao_immutable()"):]
    body = body[: body.index("$$;", body.index("AS $$"))]
    assert "NOT (OLD.status = 'publicada' AND NEW.status = 'arquivada')" in body
    assert "RAISE EXCEPTION 'version_immutable'" in body


def test_agent_version_pin_is_nullable_fk_to_a_published_version_and_frozen():
    assert "ADD COLUMN IF NOT EXISTS qualificacao_versao_id UUID NULL REFERENCES agents.qualificacao_versoes(id)" in SQL
    body = SQL[SQL.index("FUNCTION agents.guard_agent_version_qualificacao_pin()"):]
    body = body[: body.index("$$;", body.index("AS $$"))]
    assert "OLD.status <> 'rascunho'" in body and "'version_immutable'" in body
    assert "v_status IS DISTINCT FROM 'publicada'" in body
    assert "NEW.compiled_hash := NULL" in body  # the pin is part of the judged hash


def test_library_rls_reads_for_authenticated_writes_service_role_only():
    for t in ("qualificacao_padroes", "qualificacao_versoes", "qualificacao_criterios",
              "qualificacao_estagios", "qualificacao_parametros"):
        assert f"ON agents.{t} FOR SELECT TO authenticated USING (true)" in SQL, t
        assert f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.{t} FROM authenticated" in SQL, t
        assert f"REVOKE ALL ON agents.{t} FROM anon" in SQL, t
        assert f'"service_role_bypass" ON agents.{t} FOR ALL TO service_role' in SQL, t
    assert "DO $$" not in SQL


def test_per_lead_tables_have_no_fk_yet_but_carry_the_remediation_marker():
    for t in ("lead_qualificacao_registros", "lead_imovel_eventos"):
        assert re.search(r"lead_ref_id UUID NOT NULL,\s+-- NOC-REMEDIATE\[qual-lead-ref-fk\]", _table(t)), t
    assert "lead_ref_id UUID PRIMARY KEY,  -- NOC-REMEDIATE[qual-lead-ref-fk]" in _table("lead_qualificacao_estado")
    for t in ("lead_qualificacao_registros", "lead_imovel_eventos", "lead_qualificacao_estado"):
        assert "REFERENCES agents.lead_refs" not in _table(t)
    assert SQL.count("NOC-REMEDIATE[qual-lead-ref-fk]") >= 4
    assert re.search(r"NOC-REMEDIATE\[qual-lead-ref-fk\].*— ?2026-10-19|2026-10-19\.", SQL)


def test_records_require_the_lead_own_words_and_cap_the_quote():
    reg = _table("lead_qualificacao_registros")
    assert "char_length(trecho) <= 160" in reg
    assert "fonte <> 'lead_informou' OR trecho IS NOT NULL" in reg
    assert "fonte IN ('lead_informou', 'migracao', 'humano')" in reg


def test_registros_are_append_only_with_a_scoped_erasure_exception():
    assert re.search(
        r"guard_lead_qualificacao_registros_append_only\s+BEFORE UPDATE OR DELETE ON agents\.lead_qualificacao_registros", SQL)
    body = SQL[SQL.index("FUNCTION agents.guard_lead_qualificacao_append_only()"):]
    body = body[: body.index("$$;", body.index("AS $$"))]
    assert "agents.erasing_lead_qualificacao" in body and "RAISE EXCEPTION 'append_only'" in body


def test_lead_data_is_service_role_only():
    for t in ("lead_qualificacao_registros", "lead_imovel_eventos", "lead_qualificacao_estado"):
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated" in SQL
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in SQL


def test_event_enum_includes_quer_ver_mais_for_the_reaction_tool():
    ev = _table("lead_imovel_eventos")
    for e in ("oferecido", "gostou", "nao_gostou", "quer_visitar", "descartado", "quer_ver_mais"):
        assert f"'{e}'" in ev
    assert "origem IN ('campanha', 'similar', 'pedido_lead')" in ev


def test_erasure_functions_are_secdef_service_role_only():
    for fn, sig in (("apagar_qualificacao_lead", "UUID, UUID"), ("purgar_qualificacao_inativos", "TIMESTAMPTZ"),
                    ("criar_rascunho_qualificacao", "UUID, TEXT, UUID"), ("publicar_qualificacao_versao", "UUID, UUID")):
        assert f"FUNCTION agents.{fn}(" in SQL
        assert f"REVOKE ALL ON FUNCTION agents.{fn}({sig}) FROM PUBLIC, anon, authenticated" in SQL
        assert f"GRANT EXECUTE ON FUNCTION agents.{fn}({sig}) TO service_role" in SQL


def test_erasure_takes_all_three_per_lead_tables_and_purge_is_by_whole_lead():
    for fn in ("apagar_qualificacao_lead", "purgar_qualificacao_inativos"):
        body = SQL[SQL.index(f"FUNCTION agents.{fn}("):]
        body = body[: body.index("$$;", body.index("AS $$"))]
        for t in ("lead_qualificacao_registros", "lead_imovel_eventos", "lead_qualificacao_estado"):
            assert f"DELETE FROM agents.{t}" in body, (fn, t)
    purge = SQL[SQL.index("FUNCTION agents.purgar_qualificacao_inativos("):]
    assert "HAVING MAX(ts) < p_cutoff" in purge  # whole leads by last activity, never row by row


def test_publish_function_archives_the_previous_and_locks_the_row():
    body = SQL[SQL.index("FUNCTION agents.publicar_qualificacao_versao("):]
    body = body[: body.index("$$;", body.index("AS $$"))]
    assert "FOR UPDATE" in body and "SET status = 'arquivada'" in body and "SET status = 'publicada'" in body


def test_axis_validity_and_scores_columns_exist():
    crit = _table("qualificacao_criterios")
    assert "eixo TEXT NULL CHECK" in crit and "validade_dias INT NULL CHECK" in crit
    assert "scores JSONB NOT NULL DEFAULT '{}'::jsonb" in _table("lead_qualificacao_estado")
    copy = SQL[SQL.index("INSERT INTO agents.qualificacao_criterios"):]
    assert "eixo, validade_dias" in copy[: copy.index("FROM agents.qualificacao_criterios")]
