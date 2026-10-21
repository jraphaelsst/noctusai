"""Regression tests for the migration-SQL security keepers (2026-10-06 sweep).

KB § PATTERNS/backend/migration-sql-security-gates.md.
"""
import tempfile
from pathlib import Path

from tools.noctus.dev.compliance import (
    check_migration_untyped_empty_array,
    check_secdef_migration_revokes_execute,
    secdef_migration_violations,
)


def _repo(sql: str, name: str = "050_x.sql") -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="migsql_gate_"))
    f = tmp / "products" / "demo" / "backend" / "migrations" / name
    f.parent.mkdir(parents=True)
    f.write_text(sql)
    return tmp


SECDEF = """CREATE OR REPLACE FUNCTION demo.do_thing(x int) RETURNS int
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$ SELECT x $$;
"""


class TestCheckSecdefMigrationRevokesExecute:
    def test_unrevoked_secdef_flags(self):
        issues = check_secdef_migration_revokes_execute(_repo(SECDEF))
        assert len(issues) == 1 and issues[0]["severity"] == "high"
        assert "do_thing" in issues[0]["issue"]

    def test_revoke_naming_function_passes(self):
        sql = SECDEF + "REVOKE EXECUTE ON FUNCTION demo.do_thing(int) FROM PUBLIC, anon, authenticated;\n"
        assert check_secdef_migration_revokes_execute(_repo(sql)) == []

    def test_revoke_of_other_function_does_not_cover(self):
        sql = SECDEF + "REVOKE EXECUTE ON FUNCTION demo.other(int) FROM PUBLIC, anon, authenticated;\n"
        assert len(check_secdef_migration_revokes_execute(_repo(sql))) == 1

    def test_commented_revoke_does_not_count(self):
        sql = SECDEF + "-- REVOKE EXECUTE ON FUNCTION demo.do_thing(int) FROM PUBLIC;\n"
        assert len(check_secdef_migration_revokes_execute(_repo(sql))) == 1

    def test_dynamic_revoke_loop_passes(self):
        sql = SECDEF + "DO $$ BEGIN EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, anon, authenticated', 'x'); END $$;\n"
        assert check_secdef_migration_revokes_execute(_repo(sql)) == []

    def test_rls_helper_escape_passes_when_policy_references_fn(self):
        sql = (
            "-- secdef-execute-ok: rls-helper referenced by pg_policy\n" + SECDEF
            + "CREATE POLICY p ON demo.t USING (x = demo.do_thing(1));\n"
        )
        assert check_secdef_migration_revokes_execute(_repo(sql)) == []

    def test_rls_helper_escape_refused_without_policy_reference(self):
        sql = "-- secdef-execute-ok: rls-helper referenced by pg_policy\n" + SECDEF
        issues = check_secdef_migration_revokes_execute(_repo(sql))
        assert len(issues) == 1 and "CREATE POLICY" in issues[0]["issue"]

    def test_commented_policy_reference_does_not_verify(self):
        sql = (
            "-- secdef-execute-ok: rls-helper x\n" + SECDEF
            + "-- CREATE POLICY p ON demo.t USING (demo.do_thing(1));\n"
        )
        assert len(check_secdef_migration_revokes_execute(_repo(sql))) == 1

    def test_freeform_escape_reason_refused(self):
        sql = "-- secdef-execute-ok: trust me\n" + SECDEF
        assert len(check_secdef_migration_revokes_execute(_repo(sql))) == 1

    def test_security_invoker_function_ignored(self):
        sql = "CREATE FUNCTION demo.f() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$;\n"
        assert check_secdef_migration_revokes_execute(_repo(sql)) == []

    def test_only_the_definer_function_flags(self):
        sql = (
            "CREATE FUNCTION demo.plain() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$;\n"
            + SECDEF
        )
        assert [n for _, _, n in secdef_migration_violations(_repo(sql))] == ["do_thing"]

    def test_real_repo_is_clean_beyond_baseline(self):
        from tools.noctus.dev.compliance import REPO_ROOT
        issues = check_secdef_migration_revokes_execute(REPO_ROOT)
        assert issues == [], [i["file"] for i in issues]


class TestCheckMigrationUntypedEmptyArray:
    def test_untyped_flags(self):
        issues = check_migration_untyped_empty_array(_repo("SELECT coalesce(a, ARRAY[]) FROM t;\n"))
        assert len(issues) == 1 and issues[0]["severity"] == "high"

    def test_spaced_untyped_flags(self):
        assert len(check_migration_untyped_empty_array(_repo("SELECT ARRAY[ ];\n"))) == 1

    def test_typed_passes(self):
        assert check_migration_untyped_empty_array(_repo("SELECT ARRAY[]::text[], ARRAY[]::UUID[];\n")) == []

    def test_commented_untyped_passes(self):
        assert check_migration_untyped_empty_array(_repo("-- ARRAY[] note\nSELECT 1;\n")) == []

    def test_real_repo_is_clean(self):
        from tools.noctus.dev.compliance import REPO_ROOT
        assert check_migration_untyped_empty_array(REPO_ROOT) == []


class TestCheckGucCarveoutGuardHandWritten:
    HAND = """CREATE OR REPLACE FUNCTION demo.guard_t() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('demo.purge', true) = 'on' THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END; $$;
"""

    def test_hand_written_guard_flags(self):
        from tools.noctus.dev.compliance import check_guc_carveout_guard_hand_written

        issues = check_guc_carveout_guard_hand_written(_repo(self.HAND))
        assert len(issues) == 1 and "guc_carveout_guard_sql" in issues[0]["issue"]

    def test_helper_rendered_guard_passes(self):
        from noctusai_lib.domain.sql_templates import guc_carveout_guard_sql
        from tools.noctus.dev.compliance import check_guc_carveout_guard_hand_written

        sql = guc_carveout_guard_sql(schema="demo", table="t", guc="demo.purge")
        assert check_guc_carveout_guard_hand_written(_repo(sql)) == []

    def test_non_carveout_current_setting_not_flagged(self):
        from tools.noctus.dev.compliance import check_guc_carveout_guard_hand_written

        sql = (
            "CREATE OR REPLACE FUNCTION demo.audit() RETURNS TRIGGER LANGUAGE plpgsql AS $$\n"
            "BEGIN NEW.actor := current_setting('demo.actor', true); RETURN NEW; END; $$;\n"
        )
        assert check_guc_carveout_guard_hand_written(_repo(sql)) == []
