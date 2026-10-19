"""Structural pins for migration 039 (Julia v2 A-SKILLS): one platform-wide, versioned skill library with
immutable published versions, the hash-covered pins on an agent version (copied into new drafts by an
AFTER INSERT trigger), service-role-only access (IP), and NO seeded content. The chain is replayed on a
real Postgres (applied twice) by ``noctus.dev.migration_replay``; these keep the intent honest."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

from app.stores.skills_biblioteca import SKILL_CHAVE_RE, TOOL_NAME_RE
from app.studio.models import LIMITS

SQL = migration_sql(Path(__file__).resolve().parents[1], "julia_v2_skills_compartilhadas")
LIBRARY = ("skills_biblioteca", "skill_versoes", "skill_versao_arquivos")
ALL_TABLES = (*LIBRARY, "agent_version_skill_refs")


def _table(name: str) -> str:
    start = SQL.index(f"CREATE TABLE IF NOT EXISTS agents.{name} (")
    return SQL[start: SQL.index("\n);", start)]


def test_the_library_is_platform_wide_no_org():
    for t in LIBRARY:
        assert "org_id" not in _table(t), t
    assert "CONSTRAINT uq_skills_biblioteca_chave UNIQUE (chave)" in SQL
    assert "UNIQUE (skill_id, versao)" in SQL


def test_every_table_is_service_role_only():
    """IP rule: no authenticated/anon grant and no tenant read policy on any of the four."""
    for t in ALL_TABLES:
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in SQL, t
        assert re.search(rf'CREATE POLICY "service_role_bypass" ON agents\.{t}\s+FOR ALL TO service_role', SQL), t
        assert f"REVOKE ALL ON agents.{t} FROM anon, authenticated;" in SQL, t
    assert "TO authenticated" not in re.sub(r"--[^\n]*", "", SQL)
    assert not re.search(r"GRANT\s+(SELECT|ALL|INSERT|UPDATE)[^;]*TO\s+(authenticated|anon)", SQL, re.I)


def test_published_versions_are_immutable_in_the_database():
    assert "CREATE OR REPLACE TRIGGER guard_skill_versao_immutable" in SQL
    assert "BEFORE UPDATE OR DELETE ON agents.skill_versoes" in SQL
    assert "CREATE OR REPLACE TRIGGER guard_skill_versao_arquivos_immutable" in SQL
    assert SQL.count("RAISE EXCEPTION 'version_immutable'") >= 6
    # content columns frozen on the publicada -> arquivada step
    for col in ("descricao_modelo", "corpo", "skill_id", "versao", "notas"):
        assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in SQL, col
    assert re.search(r"uq_skill_versoes_um_rascunho\s+ON agents\.skill_versoes \(skill_id\) WHERE status = 'rascunho'", SQL)


def test_a_published_version_has_real_text():
    assert "status = 'rascunho' OR (btrim(corpo) <> '' AND btrim(descricao_modelo) <> '')" in SQL
    assert "IF btrim(v_corpo) = '' OR btrim(v_desc) = ''" in SQL


def test_the_pins_are_hash_covered_and_inherited_by_new_drafts():
    assert "EXECUTE FUNCTION agents.guard_version_child_immutable()" in SQL  # 012: NULLs compiled_hash
    assert "CREATE OR REPLACE TRIGGER guard_agent_version_skill_refs_immutable" in SQL
    assert "CREATE OR REPLACE TRIGGER copy_version_skill_refs" in SQL and "AFTER INSERT ON agents.agent_versions" in SQL
    assert "FUNCTION agents.create_agent_draft" not in SQL  # 031's pattern: a trigger, not a redefinition
    refs = _table("agent_version_skill_refs")
    assert "REFERENCES agents.agent_versions(id) ON DELETE CASCADE" in refs
    assert "REFERENCES agents.skill_versoes(id)" in refs and "ON DELETE CASCADE" not in refs.split("skill_versao_id")[1]
    assert "UNIQUE (version_id, skill_id)" in refs  # one pinned version per skill
    assert "obrigatoria_para TEXT[] NOT NULL DEFAULT '{}'" in refs


def test_a_draft_skill_version_cannot_be_pinned_and_the_org_must_match():
    guard = SQL[SQL.index("FUNCTION agents.guard_agent_version_skill_ref()"):]
    guard = guard[: guard.index("$$;", guard.index("$$;") + 3)]
    assert "v_status = 'rascunho'" in guard and "RAISE EXCEPTION 'invalid_payload'" in guard
    assert "NEW.skill_id := v_skill" in guard and "IS DISTINCT FROM NEW.org_id" in guard


def test_security_definer_functions_revoke_execute_from_public():
    names = re.findall(r"CREATE OR REPLACE FUNCTION (agents\.\w+)\(", SQL)
    assert len(names) == 6
    for name in names:
        assert re.search(rf"REVOKE ALL ON FUNCTION {re.escape(name)}\([^)]*\) FROM PUBLIC, anon, authenticated;", SQL), name
        assert re.search(rf"GRANT EXECUTE ON FUNCTION {re.escape(name)}\([^)]*\) TO service_role;", SQL), name
    assert SQL.count("SECURITY DEFINER SET search_path = agents, public") == 6


def test_size_caps_and_shapes_match_the_python_side():
    assert f"length(corpo) <= {LIMITS['skill.corpo']}" in SQL
    assert f"length(conteudo) <= {LIMITS['skill_file.conteudo']}" in SQL
    assert SKILL_CHAVE_RE.pattern in SQL
    # the DB shape for a gated tool name is the same shape the API enforces
    assert TOOL_NAME_RE.pattern.strip("^$") in SQL


def test_no_content_is_seeded_in_the_migration():
    """D3: structure only -- skill text arrives as DB data through the MCP content tool."""
    code = re.sub(r"--[^\n]*", "", SQL)
    inserts = re.findall(r"INSERT INTO agents\.(\w+)", code)
    # the only INSERTs are inside the two RPCs (new draft + file copy) and the draft-inheritance trigger
    assert sorted(inserts) == ["agent_version_skill_refs", "skill_versao_arquivos", "skill_versoes"]
    assert "VALUES" not in code
