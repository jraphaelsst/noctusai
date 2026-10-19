"""Regression tests for ``check_no_authenticated_grant_on_content_tables`` (security finding C2, 2026-10-19).

The agents schema is PostgREST-exposed; a ``GRANT SELECT`` / ``CREATE POLICY`` TO authenticated on an agents
table makes it readable from the browser by any logged-in member of any org. Migrations numbered >= 036 may
not do that outside ``AGENTS_BROWSER_READABLE_TABLES``. KB § PATTERNS/backend/database-rls.md.
"""
import tempfile
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev.compliance import (
    AGENTS_BROWSER_READABLE_TABLES,
    check_no_authenticated_grant_on_content_tables,
)


def _repo(sql: str, name: str = "037_x.sql") -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="agents_grant_gate_"))
    f = tmp / "products" / "agents" / "backend" / "migrations" / name
    f.parent.mkdir(parents=True)
    f.write_text(sql)
    return tmp


class TestCheckNoAuthenticatedGrantOnContentTables:
    def test_grant_select_to_authenticated_flags(self):
        issues = check_no_authenticated_grant_on_content_tables(_repo("GRANT SELECT ON agents.secrets TO authenticated;"))
        assert len(issues) == 1 and "secrets" in issues[0]["issue"]
        assert issues[0]["severity"] == "critical"

    def test_grant_all_and_multi_role_flags(self):
        assert check_no_authenticated_grant_on_content_tables(_repo("GRANT ALL ON TABLE agents.t TO service_role, authenticated;"))

    def test_grant_all_tables_in_schema_flags(self):
        assert check_no_authenticated_grant_on_content_tables(_repo("GRANT SELECT ON ALL TABLES IN SCHEMA agents TO authenticated;"))

    def test_default_privileges_grant_flags(self):
        assert check_no_authenticated_grant_on_content_tables(
            _repo("ALTER DEFAULT PRIVILEGES IN SCHEMA agents GRANT ALL ON TABLES TO authenticated;"))

    def test_policy_to_authenticated_flags(self):
        sql = 'CREATE POLICY "t_select_own_org" ON agents.t\n    FOR SELECT TO authenticated\n    USING (org_id = x());'
        assert len(check_no_authenticated_grant_on_content_tables(_repo(sql))) == 1

    def test_policy_to_anon_flags(self):
        assert check_no_authenticated_grant_on_content_tables(_repo("CREATE POLICY p ON agents.t FOR SELECT TO anon USING (true);"))

    def test_service_role_only_is_clean(self):
        sql = (
            "GRANT SELECT ON agents.t TO service_role;\n"
            "CREATE POLICY p ON agents.t FOR ALL TO service_role USING (true);\n"
            "REVOKE ALL ON agents.t FROM anon, authenticated;\n"
            "GRANT EXECUTE ON FUNCTION agents.f() TO service_role;\n"
        )
        assert check_no_authenticated_grant_on_content_tables(_repo(sql)) == []

    def test_function_and_sequence_grants_are_not_table_reads(self):
        sql = "GRANT EXECUTE ON FUNCTION agents.f() TO authenticated;\nGRANT USAGE ON SEQUENCE agents.s TO authenticated;"
        assert check_no_authenticated_grant_on_content_tables(_repo(sql)) == []

    def test_allowlisted_table_is_clean(self):
        assert "status_pagina" in AGENTS_BROWSER_READABLE_TABLES
        sql = "GRANT SELECT ON agents.status_pagina TO anon, authenticated;"
        assert check_no_authenticated_grant_on_content_tables(_repo(sql)) == []

    def test_commented_and_dollar_quoted_text_is_ignored(self):
        sql = "-- GRANT SELECT ON agents.t TO authenticated;\nDO $x$ BEGIN RAISE NOTICE 'GRANT SELECT ON agents.t TO authenticated'; END $x$;"
        assert check_no_authenticated_grant_on_content_tables(_repo(sql)) == []

    def test_legacy_migrations_before_036_are_not_scanned(self):
        repo = _repo("GRANT SELECT ON agents.t TO authenticated;", name="035_legacy.sql")
        assert check_no_authenticated_grant_on_content_tables(repo) == []

    def test_paths_scopes_to_the_staged_delta(self):
        repo = _repo("GRANT SELECT ON agents.t TO authenticated;", name="038_bad.sql")
        assert check_no_authenticated_grant_on_content_tables(repo, paths=["products/agents/backend/migrations/039_other.sql"]) == []
        assert check_no_authenticated_grant_on_content_tables(repo, paths=["products/agents/backend/migrations/038_bad.sql"])

    def test_the_real_agents_chain_is_clean(self):
        assert check_no_authenticated_grant_on_content_tables(Path(REPO_ROOT)) == []
