"""Structural pins for the Julia v2 content migration (031): definition scope, the four version-scoped
content tables, platform texts, per-org spec values, the audit actions. The file is also replayed on a
real Postgres (PGlite, applied twice) by the pre-commit chain replay; these keep the invariants honest."""
from __future__ import annotations

import re
from pathlib import Path

from app.stores.studio_definitions import AUDIT_ACOES, DEFINITION_SCOPES
from app.studio.models import LIMITS, SPEC_TIPOS

SQL = next(Path(__file__).resolve().parents[1].joinpath("migrations").glob("*julia_v2_conteudo.sql")).read_text(encoding="utf-8")
CONTENT_TABLES = ("agent_version_textos", "agent_version_ferramentas", "agent_version_decisoes", "agent_version_specs")


def test_definition_scope_constraints_match_the_python_side():
    assert "CHECK (definition_scope IN ('org', 'plataforma', 'instancia'))" in SQL
    assert DEFINITION_SCOPES == ("org", "plataforma", "instancia")
    assert "(definition_scope = 'instancia') = (definition_agent_id IS NOT NULL)" in SQL
    assert "definition_scope = 'org' OR conteudo_modo = 'linhas'" in SQL
    assert "agents_one_plataforma_per_key" in SQL and "WHERE definition_scope = 'plataforma'" in SQL


def test_platform_definition_is_pinned_to_the_platform_org_and_scope_never_changes():
    assert "o.is_platform" in SQL and "definition_not_platform" in SQL
    assert "scope_immutable" in SQL and "definition_invalid" in SQL


def test_every_content_table_is_version_scoped_cascading_and_hash_guarded():
    for t in CONTENT_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS agents.{t}" in SQL
        assert f"CREATE OR REPLACE TRIGGER guard_{t}_immutable" in SQL
        assert f"set_updated_at_{t}" in SQL and f"{t}_select_own_org" in SQL
    assert SQL.count("REFERENCES agents.agent_versions(id) ON DELETE CASCADE") == 4
    assert SQL.count("UNIQUE (version_id,") == 4
    assert SQL.count("EXECUTE FUNCTION agents.guard_version_child_immutable()") == 4


def test_size_caps_match_models_limits():
    assert f"length(conteudo) <= {LIMITS['texto.conteudo']}" in SQL
    assert f"BETWEEN 1 AND {LIMITS['ferramenta.descricao']}" in SQL
    assert f"length(regra) <= {LIMITS['decisao.regra']}" in SQL
    assert f"length(valor) <= {LIMITS['org_spec.valor.texto_longo']}" in SQL
    assert SPEC_TIPOS == ("texto", "texto_longo") and "IN ('texto', 'texto_longo')" in SQL


def test_a_new_draft_copies_the_content_through_a_trigger_not_a_third_create_agent_draft():
    assert "CREATE OR REPLACE TRIGGER copy_version_conteudo" in SQL
    assert "AFTER INSERT ON agents.agent_versions" in SQL
    assert "FUNCTION agents.create_agent_draft" not in SQL


def test_decisao_sections_are_copied_before_the_immutability_triggers_exist():
    assert SQL.index("INSERT INTO agents.agent_version_decisoes") < SQL.index(
        "CREATE OR REPLACE TRIGGER guard_agent_version_decisoes_immutable")
    assert "LIKE 'decisao-%'" in SQL and "ON CONFLICT (version_id, chave) DO NOTHING" in SQL


def test_no_content_is_seeded_in_the_migration():
    """D3: structure only. The only INSERT is the move of existing decisao-* sections."""
    inserts = re.findall(r"INSERT INTO agents\.(\w+)", SQL)
    assert set(inserts) <= {"agent_version_decisoes", "agent_version_textos", "agent_version_ferramentas", "agent_version_specs"}
    assert not re.search(r"\bVALUES\s*\(", SQL)


def test_secdef_functions_revoke_execute_and_audit_actions_are_extended_once():
    for fn in ("guard_agent_definition_scope()", "copy_version_conteudo()", "replace_draft_conteudo(UUID, UUID, TEXT, JSONB)"):
        assert f"REVOKE ALL ON FUNCTION agents.{fn} FROM PUBLIC, anon, authenticated" in SQL
    later = {"agente_excluido", "agente_criado", "agente_gerado", "historico_transferido", "agente_arquivado"}
    for acao in set(AUDIT_ACOES) - later:  # lifecycle actions arrive in 048 / 049, the cutover ones in 053
        assert f"'{acao}'" in SQL
    assert "conversa_pausada" in SQL and "padrao_publicado" in SQL  # the contract §5.1 list, so siblings never redefine it


def test_platform_texts_have_no_authenticated_access():
    assert "REVOKE ALL ON agents.textos_plataforma FROM anon, authenticated" in SQL
