"""Structural tests for ``012_agent_studio_definitions.sql`` (contract §B1).

Parse-based, no database — same style as ``tests/stores/test_migration_006_shape.py``.
The statement-level parse uses ``pglast`` (the real Postgres parser), so a
syntax error in the migration fails here, not at deploy.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parents[3] / "migrations" / "012_agent_studio_definitions.sql"

NEW_TABLES = (
    "agent_versions",
    "agent_prompt_sections",
    "agent_skills",
    "agent_skill_files",
    "agent_clients",
    "agent_client_entries",
    "compiled_prompts",
    "agent_audit_log",
)
VERSION_FUNCTIONS = (
    "create_agent_draft",
    "publish_agent_version",
    "discard_agent_draft",
    "set_agent_publicacao_limiar",
    "replace_draft_sections",
    "replace_draft_bundle",
    "erase_compiled_prompts",
)
TRIGGER_FUNCTIONS = (
    "guard_agent_version_immutable",
    "guard_version_child_immutable",
    "guard_skill_file_immutable",
    "guard_compiled_prompt_immutable",
    "guard_audit_log_append_only",
    "guard_client_entry_cap",
    "audit_agent_limiar_change",
)
ALL_FUNCTIONS = VERSION_FUNCTIONS + TRIGGER_FUNCTIONS


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _table_block(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE agents.{table} (")
    return sql[start : sql.index(");", start)]


def _function_block(sql: str, name: str) -> str:
    start = sql.index(f"CREATE OR REPLACE FUNCTION agents.{name}(")
    return sql[start : sql.index("$$;", start)]


class TestParses:
    def test_every_statement_parses_with_the_postgres_parser(self, sql):
        pglast = pytest.importorskip("pglast")
        assert len(pglast.parse_sql(sql)) > 50

    def test_every_plpgsql_body_parses(self, sql):
        parser = pytest.importorskip("pglast.parser")
        # pglast's PL/pgSQL parser cannot resolve a `schema.table` %ROWTYPE
        # outside pg_catalog/public; RECORD is equivalent for a syntax check.
        body = re.sub(r"(v_\w+) agents\.agent_versions;", r"\1 RECORD;", sql)
        fns = re.findall(r"CREATE OR REPLACE FUNCTION.*?\$\$;", body, re.S)
        assert len(fns) == len(ALL_FUNCTIONS)
        for fn in fns:
            parser.parse_plpgsql_json(fn)


class TestStudioColumnsOnAgents:
    def test_definition_mode_defaults_legacy(self, sql):
        assert re.search(
            r"ADD COLUMN definition_mode TEXT NOT NULL DEFAULT 'legacy'\s+"
            r"CHECK \(definition_mode IN \('legacy', 'studio'\)\)",
            sql,
        )

    def test_descricao_and_limiar(self, sql):
        assert "ADD COLUMN descricao TEXT NULL" in sql
        assert "ADD COLUMN publicacao_limiar NUMERIC(4,3) NOT NULL DEFAULT 0.800," in sql

    def test_limiar_has_a_named_floor(self, sql):
        """H2: a threshold below 0.5 makes the gate decorative."""
        assert re.search(
            r"ADD CONSTRAINT agents_publicacao_limiar_floor\s+"
            r"CHECK \(publicacao_limiar >= 0\.5 AND publicacao_limiar <= 1\)",
            sql,
        )

    def test_proof_of_use_columns(self, sql):
        assert re.search(
            r"ALTER TABLE agents\.conversations\s+ADD COLUMN version_id UUID NULL REFERENCES agents\.agent_versions\(id\),\s+"
            r"ADD COLUMN client_id UUID NULL REFERENCES agents\.agent_clients\(id\);",
            sql,
        )
        assert re.search(
            r"ALTER TABLE agents\.messages\s+ADD COLUMN version_id UUID NULL REFERENCES agents\.agent_versions\(id\),\s+"
            r"ADD COLUMN compiled_hash TEXT NULL;",
            sql,
        )


class TestConventions:
    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_common_columns(self, sql, table):
        block = _table_block(sql, table)
        assert re.search(r"id UUID PRIMARY KEY DEFAULT gen_random_uuid\(\)", block)
        assert re.search(r"org_id UUID NOT NULL", block)
        assert re.search(r"created_at TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)
        assert re.search(r"updated_at TIMESTAMPTZ NOT NULL DEFAULT now\(\)", block)

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_rls_enabled(self, sql, table):
        assert f"ALTER TABLE agents.{table} ENABLE ROW LEVEL SECURITY" in sql

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_org_scoped_select_policy(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "{table}_select_own_org" ON agents\.{table}\s+'
            rf"FOR SELECT TO authenticated\s+USING \(org_id = current_org_id\(\)\)",
            sql,
        )

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_literal_service_role_bypass(self, sql, table):
        assert re.search(
            rf'CREATE POLICY "service_role_bypass" ON agents\.{table}\s+'
            rf"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)",
            sql,
        )

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_org_index(self, sql, table):
        assert f"CREATE INDEX idx_agents_{table}_org ON agents.{table}(org_id);" in sql

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_updated_at_trigger(self, sql, table):
        assert re.search(
            rf"CREATE OR REPLACE TRIGGER set_updated_at_{table}\s+BEFORE UPDATE ON agents\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION agents\.set_updated_at\(\)",
            sql,
        )

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_anon_lockdown_restated(self, sql, table):
        """011 revoked anon from the schema default privileges; each new
        table restates it explicitly."""
        assert f"REVOKE ALL ON agents.{table} FROM anon;" in sql

    def test_no_new_grant_to_anon(self, sql):
        code = re.sub(r"--[^\n]*", "", sql)
        grants = re.findall(r"^\s*GRANT\b[^;]*;", code, re.M)
        assert grants, "expected the service_role GRANT statements"
        assert not [g for g in grants if re.search(r"\banon\b|\bauthenticated\b|\bPUBLIC\b", g)]


class TestPageVisibility:
    def test_studio_nav_page_is_seeded_in_development(self, sql):
        """Without a status_pagina row the `/studio` nav entry is hidden from
        everyone (KB § PATTERNS/frontend/status-pagina-dev-visibility.md)."""
        assert re.search(
            r"INSERT INTO agents\.status_pagina \(nome_pagina, status\) VALUES\s+"
            r"\('studio', 'desenvolvimento'\)\s+ON CONFLICT \(nome_pagina\) DO NOTHING;",
            sql,
        )


class TestVersionInvariants:
    def test_partial_uniques(self, sql):
        assert re.search(
            r"CREATE UNIQUE INDEX agent_versions_one_ativa_idx\s+ON agents\.agent_versions \(agent_id\) WHERE status = 'ativa'",
            sql,
        )
        assert re.search(
            r"CREATE UNIQUE INDEX agent_versions_one_rascunho_idx\s+ON agents\.agent_versions \(agent_id\) WHERE status = 'rascunho'",
            sql,
        )

    def test_checks(self, sql):
        block = _table_block(sql, "agent_versions")
        assert "CHECK (status IN ('rascunho', 'ativa', 'substituida'))" in block
        assert "CHECK (model IN ('claude-opus-5', 'claude-sonnet-5'))" in block
        assert "CHECK (effort IN ('low', 'medium', 'high', 'xhigh', 'max'))" in block
        assert "CHECK (max_turns BETWEEN 1 AND 200)" in block
        assert "UNIQUE (agent_id, versao)" in block
        assert "UNIQUE (org_id, hash)" in _table_block(sql, "compiled_prompts")
        assert "UNIQUE (version_id, chave)" in _table_block(sql, "agent_prompt_sections")
        assert "UNIQUE (version_id, nome)" in _table_block(sql, "agent_skills")
        assert "UNIQUE (skill_id, caminho)" in _table_block(sql, "agent_skill_files")
        assert "UNIQUE (agent_id, slug)" in _table_block(sql, "agent_clients")

    def test_children_cascade_from_their_version(self, sql):
        for table in ("agent_prompt_sections", "agent_skills"):
            assert "REFERENCES agents.agent_versions(id) ON DELETE CASCADE" in _table_block(sql, table)
        assert "REFERENCES agents.agent_skills(id) ON DELETE CASCADE" in _table_block(sql, "agent_skill_files")


class TestImmutabilityTriggers:
    @pytest.mark.parametrize(
        "trigger, table, events, fn",
        [
            ("guard_agent_version_immutable", "agent_versions", "BEFORE UPDATE OR DELETE", "guard_agent_version_immutable"),
            ("guard_agent_prompt_sections_immutable", "agent_prompt_sections", "BEFORE INSERT OR UPDATE OR DELETE", "guard_version_child_immutable"),
            ("guard_agent_skills_immutable", "agent_skills", "BEFORE INSERT OR UPDATE OR DELETE", "guard_version_child_immutable"),
            ("guard_agent_skill_files_immutable", "agent_skill_files", "BEFORE INSERT OR UPDATE OR DELETE", "guard_skill_file_immutable"),
            ("guard_compiled_prompts_immutable", "compiled_prompts", "BEFORE UPDATE OR DELETE", "guard_compiled_prompt_immutable"),
            ("guard_agent_audit_log_append_only", "agent_audit_log", "BEFORE UPDATE OR DELETE", "guard_audit_log_append_only"),
            ("guard_agent_client_entries_cap", "agent_client_entries", "BEFORE INSERT OR UPDATE", "guard_client_entry_cap"),
        ],
    )
    def test_trigger_present(self, sql, trigger, table, events, fn):
        assert re.search(
            rf"CREATE OR REPLACE TRIGGER {trigger}\s+{events} ON agents\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION agents\.{fn}\(\)",
            sql,
        ), f"missing trigger {trigger} on {table}"

    def test_version_guard_only_allows_ativa_to_substituida(self, sql):
        body = _function_block(sql, "guard_agent_version_immutable")
        assert "OLD.status = 'ativa' AND NEW.status = 'substituida'" in body
        # Every content column is compared on the published path.
        for col in (
            "notas", "model", "effort", "max_turns", "idioma", "tool_policy", "compiled_hash",
            "eval_run_id", "publish_override_reason", "published_at", "published_by",
            "limiar_aplicado", "eval_score",
        ):
            assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in body, col

    def test_guards_raise_the_machine_code(self, sql):
        for fn in ("guard_agent_version_immutable", "guard_version_child_immutable", "guard_skill_file_immutable"):
            assert "RAISE EXCEPTION 'version_immutable'" in _function_block(sql, fn)
        assert "RAISE EXCEPTION 'compiled_prompt_immutable'" in _function_block(sql, "guard_compiled_prompt_immutable")


class TestVersionFunctions:
    def test_signatures(self, sql):
        assert re.search(
            r"FUNCTION agents\.create_agent_draft\(\s*p_org_id UUID,\s*p_agent_id UUID,\s*"
            r"p_source_version_id UUID,\s*p_created_by UUID\s*\) RETURNS UUID",
            sql,
        )
        assert re.search(
            r"FUNCTION agents\.publish_agent_version\(\s*p_org_id UUID,\s*p_version_id UUID,\s*"
            r"p_published_by UUID,\s*p_eval_run_id UUID,\s*p_override_reason TEXT,\s*"
            r"p_expected_hash TEXT,\s*p_texto TEXT,\s*p_manifest JSONB\s*\) RETURNS VOID",
            sql,
        )
        assert re.search(
            r"FUNCTION agents\.discard_agent_draft\(\s*p_org_id UUID,\s*p_version_id UUID,\s*p_actor UUID\s*\) RETURNS VOID",
            sql,
        )
        assert re.search(
            r"FUNCTION agents\.replace_draft_bundle\(\s*p_org_id UUID,\s*p_version_id UUID,\s*"
            r"p_secoes JSONB,\s*p_skills JSONB\s*\) RETURNS VOID",
            sql,
        )
        assert re.search(
            r"FUNCTION agents\.erase_compiled_prompts\(\s*p_org_id UUID,\s*p_client_id UUID\s*\) RETURNS INT",
            sql,
        )

    def test_create_draft_raises_draft_exists_and_deep_copies(self, sql):
        body = _function_block(sql, "create_agent_draft")
        assert "RAISE EXCEPTION 'draft_exists'" in body
        assert "COALESCE(MAX(versao), 0) + 1" in body
        assert "'claude-opus-5', 'high', 40" in body
        for table in ("agent_prompt_sections", "agent_skills", "agent_skill_files"):
            assert f"INSERT INTO agents.{table}" in body

    def test_publish_flips_ativa_before_setting_the_new_one(self, sql):
        body = _function_block(sql, "publish_agent_version")
        assert "RAISE EXCEPTION 'version_immutable'" in body
        assert body.index("SET status = 'substituida'") < body.index("SET status = 'ativa'")

    @pytest.mark.parametrize("fn", VERSION_FUNCTIONS)
    def test_version_functions_are_security_definer_with_locked_search_path(self, sql, fn):
        body = _function_block(sql, fn)
        assert "SECURITY DEFINER" in body
        assert "SET search_path = agents, public" in body


class TestSecurityDefinerExecuteGrants:
    """Generic walk (as in 006's test): EVERY SECURITY DEFINER function in 012
    has the REVOKE (PUBLIC, anon, authenticated) + GRANT service_role pair."""

    @staticmethod
    def _definer_names(sql: str) -> list[str]:
        names = []
        for m in re.finditer(r"CREATE OR REPLACE FUNCTION\s+(agents\.\w+)\s*\(", sql):
            nxt = sql.find("CREATE OR REPLACE FUNCTION", m.end())
            if "SECURITY DEFINER" in sql[m.end() : nxt if nxt != -1 else len(sql)]:
                names.append(m.group(1))
        return names

    def test_every_function_is_covered(self, sql):
        names = self._definer_names(sql)
        assert sorted(names) == sorted(f"agents.{fn}" for fn in ALL_FUNCTIONS)

    def test_revoke_pairs(self, sql):
        for fname in self._definer_names(sql):
            m = re.search(rf"REVOKE ALL ON FUNCTION {re.escape(fname)}\b[^;]*FROM([^;]*);", sql)
            assert m, f"{fname} lacks its REVOKE"
            for role in ("PUBLIC", "ANON", "AUTHENTICATED"):
                assert role in m.group(1).upper(), f"{fname} REVOKE must name {role}"

    def test_grant_pairs_service_role_only(self, sql):
        for fname in self._definer_names(sql):
            m = re.search(rf"GRANT EXECUTE ON FUNCTION {re.escape(fname)}\b[^;]*TO([^;]*);", sql)
            assert m, f"{fname} lacks its GRANT"
            assert [r.strip() for r in m.group(1).split(",")] == ["service_role"]


# ── wave-1 security review hardening ────────────────────────────────────────


class TestAuthenticatedWriteLockdown:
    """M5 (mirrors 009/010): authenticated keeps SELECT, never writes."""

    @pytest.mark.parametrize("table", NEW_TABLES)
    def test_authenticated_writes_revoked(self, sql, table):
        assert f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON agents.{table} FROM authenticated;" in sql


class TestSizeCaps:
    """M3: the DB CHECK backstop of ``app.studio.models.LIMITS``."""

    @pytest.mark.parametrize(
        "table, check",
        [
            ("agent_prompt_sections", "CHECK (length(conteudo) <= 40000)"),
            ("agent_skills", "CHECK (length(corpo) <= 60000)"),
            ("agent_skill_files", "CHECK (length(conteudo) <= 120000)"),
            ("agent_clients", "CHECK (length(resumo) <= 8000)"),
            ("agent_client_entries", "CHECK (length(titulo) <= 200)"),
            ("agent_client_entries", "CHECK (length(conteudo) <= 4000)"),
        ],
    )
    def test_cap(self, sql, table, check):
        assert check in _table_block(sql, table)

    def test_caps_match_the_python_limits(self, sql):
        from app.studio.models import LIMITS

        for key, needle in (
            ("section.conteudo", "length(conteudo) <= {}"), ("skill.corpo", "length(corpo) <= {}"),
            ("skill_file.conteudo", "length(conteudo) <= {}"), ("client.resumo", "length(resumo) <= {}"),
            ("entry.titulo", "length(titulo) <= {}"), ("entry.conteudo", "length(conteudo) <= {}"),
        ):
            assert needle.format(LIMITS[key]) in sql, key

    def test_active_entry_cap_trigger(self, sql):
        body = _function_block(sql, "guard_client_entry_cap")
        assert "v_ativas >= 200" in body
        assert "FOR UPDATE" in body  # serialises concurrent inserts per client
        assert "RAISE EXCEPTION 'client_entries_cap'" in body


class TestOverrideReason:
    def test_named_check_on_trimmed_length(self, sql):
        """L1: DB backstop — the reason must survive btrim with >= 20 chars."""
        block = _table_block(sql, "agent_versions")
        assert "CONSTRAINT agent_versions_override_reason_len CHECK (" in block
        assert "length(btrim(publish_override_reason, E' \\t\\r\\n')) >= 20" in block


class TestPublishRace:
    """M1: content writes NULL the draft hash; publish needs the expected hash."""

    @pytest.mark.parametrize("fn", ["guard_version_child_immutable", "guard_skill_file_immutable"])
    def test_child_guards_lock_parent_and_null_its_hash(self, sql, fn):
        body = _function_block(sql, fn)
        assert "FOR UPDATE" in body
        assert "SET compiled_hash = NULL" in body

    def test_draft_setting_change_nulls_hash(self, sql):
        body = _function_block(sql, "guard_agent_version_immutable")
        assert "NEW.compiled_hash := NULL;" in body

    def test_publish_refuses_a_changed_draft(self, sql):
        body = _function_block(sql, "publish_agent_version")
        assert "v_row.compiled_hash IS DISTINCT FROM p_expected_hash" in body
        assert "RAISE EXCEPTION 'draft_changed'" in body
        # checked on the FOR UPDATE-locked row, before anything is written
        assert body.index("FOR UPDATE") < body.index("'draft_changed'") < body.index("UPDATE agents.agent_versions")


class TestPublishGateInDb:
    """H1/H2: the DB re-validates the gate and snapshots it."""

    def test_run_must_be_complete_and_match(self, sql):
        body = _function_block(sql, "publish_agent_version")
        for cond in (
            "r.version_id = p_version_id", "r.status = 'concluida'", "r.completa", "r.total >= 1",
            "r.compiled_hash = p_expected_hash", "r.score >= v_limiar",
        ):
            assert cond in body, cond
        assert "c.ativo" in body  # >= 1 active case
        assert "RAISE EXCEPTION 'eval_required'" in body

    def test_snapshots_threshold_and_score(self, sql):
        body = _function_block(sql, "publish_agent_version")
        assert "limiar_aplicado = v_limiar" in body
        assert "eval_score = v_score" in body
        assert "FOR SHARE" in body  # threshold can't move under the publish

    def test_override_needs_20_non_whitespace_chars(self, sql):
        body = _function_block(sql, "publish_agent_version")
        assert "length(regexp_replace(v_reason, '\\s', '', 'g')) < 20" in body

    def test_proof_of_use_is_in_the_same_transaction(self, sql):
        body = _function_block(sql, "publish_agent_version")
        assert "INSERT INTO agents.compiled_prompts" in body
        assert "ON CONFLICT (org_id, hash) DO NOTHING" in body
        assert body.index("INSERT INTO agents.compiled_prompts") < body.index("SET status = 'ativa'")

    def test_version_columns(self, sql):
        block = _table_block(sql, "agent_versions")
        assert "limiar_aplicado NUMERIC(4,3) NULL" in block
        assert "eval_score NUMERIC(4,3) NULL" in block


class TestAuditLog:
    def test_publish_and_discard_append(self, sql):
        assert "INSERT INTO agents.agent_audit_log" in _function_block(sql, "publish_agent_version")
        assert "'publicado_override'" in _function_block(sql, "publish_agent_version")
        body = _function_block(sql, "discard_agent_draft")
        assert "INSERT INTO agents.agent_audit_log" in body and "'rascunho_descartado'" in body

    def test_threshold_changes_are_audited_by_trigger(self, sql):
        assert re.search(
            r"CREATE OR REPLACE TRIGGER audit_agent_limiar_change\s+AFTER UPDATE OF publicacao_limiar ON agents\.agents\s+"
            r"FOR EACH ROW\s+WHEN \(OLD\.publicacao_limiar IS DISTINCT FROM NEW\.publicacao_limiar\)",
            sql,
        )
        assert "current_setting('agents.audit_actor', true)" in _function_block(sql, "audit_agent_limiar_change")
        assert "set_config('agents.audit_actor'" in _function_block(sql, "set_agent_publicacao_limiar")

    def test_acao_allowlist(self, sql):
        assert (
            "CHECK (acao IN ('limiar_alterado', 'publicado', 'publicado_override', 'rascunho_descartado'))"
            in _table_block(sql, "agent_audit_log")
        )


class TestCompiledPromptErasure:
    """L2: DELETE is refused except through the service_role erasure function."""

    def test_guard_allows_delete_only_under_the_erasure_flag(self, sql):
        body = _function_block(sql, "guard_compiled_prompt_immutable")
        assert "current_setting('agents.compiled_prompt_erasure', true) = 'on'" in body

    def test_erasure_function_sets_the_flag_and_scopes_by_org_and_client(self, sql):
        body = _function_block(sql, "erase_compiled_prompts")
        assert "set_config('agents.compiled_prompt_erasure', 'on', true)" in body
        assert "DELETE FROM agents.compiled_prompts WHERE org_id = p_org_id AND client_id = p_client_id" in body
        assert "RAISE EXCEPTION 'client_required'" in body


class TestAtomicReplace:
    def test_sections_replace_defers_the_chave_unique(self, sql):
        block = _table_block(sql, "agent_prompt_sections")
        assert "UNIQUE (version_id, chave) DEFERRABLE INITIALLY IMMEDIATE" in block
        body = _function_block(sql, "replace_draft_sections")
        assert "SET CONSTRAINTS agents.agent_prompt_sections_version_chave_key DEFERRED" in body
        assert "RAISE EXCEPTION 'chave_conflict'" in body

    def test_bundle_replaces_sections_skills_and_files(self, sql):
        body = _function_block(sql, "replace_draft_bundle")
        for stmt in (
            "DELETE FROM agents.agent_prompt_sections", "DELETE FROM agents.agent_skills",
            "INSERT INTO agents.agent_prompt_sections", "INSERT INTO agents.agent_skills",
            "INSERT INTO agents.agent_skill_files",
        ):
            assert stmt in body, stmt
        assert "RAISE EXCEPTION 'skill_exists'" in body
