"""Migration-declared CROSS-COLUMN CHECKs, enforced by `MockSupabaseClient`
with no manifest (2026-10-10).

Three layers, tested where they live:
  * `sql_check.compile_check` — the SQL subset, three-valued logic, and the
    "unknown passes" rule that keeps the mock from failing a test on a guess;
  * `migration_parser.parse_check_sql` — CHECKs as they stand after the
    migrations apply in order (drop / re-add / rename / drop column);
  * the mock — a violating INSERT / UPDATE / UPSERT raises
    `MockRowCheckViolation`; a row that doesn't carry every column a CHECK
    reads is not judged.
"""
from __future__ import annotations

import pytest

from noctusai_lib.testing import (
    MockRowCheckViolation,
    MockSupabaseClient,
    reset_cache,
    set_cache_for_tests,
    set_checks_for_tests,
)
from noctusai_lib.testing.migration_parser import parse_check_sql
from noctusai_lib.testing.sql_check import UnsupportedCheck, compile_check


def _v(body: str, **row):
    return compile_check(body).verdict(row)


class TestSqlCheck:
    @pytest.mark.parametrize("body,row,expected", [
        ("ends_at > starts_at", {"starts_at": "2026-01-01T10:00:00+00:00", "ends_at": "2026-01-01T09:00:00+00:00"}, False),
        ("ends_at > starts_at", {"starts_at": "2026-01-01T10:00:00Z", "ends_at": "2026-01-01 11:00:00+00:00"}, True),
        ("pct_a + pct_b + pct_c = 100", {"pct_a": 50, "pct_b": 30, "pct_c": 20}, True),
        ("pct_a + pct_b + pct_c = 100", {"pct_a": "50.5", "pct_b": 30, "pct_c": 20}, False),
        ("num_nonnulls(lead_id, meta_id) = 1", {"lead_id": "x", "meta_id": "y"}, False),
        ("num_nonnulls(lead_id, meta_id) = 1", {"lead_id": None, "meta_id": "y"}, True),
        ("(ended_at IS NULL) = (ended_by IS NULL)", {"ended_at": "2026-01-01", "ended_by": None}, False),
        ("status <> 'perdido' OR (motivo IS NOT NULL AND perdido_em IS NOT NULL)",
         {"status": "perdido", "motivo": None, "perdido_em": None}, False),
        ("NOT recorrente OR (dias > 0 AND qtd > 0)", {"recorrente": True, "dias": 0, "qtd": 1}, False),
        ("action NOT IN ('archive', 'send_back') OR length(btrim(coalesce(motivo, ''))) > 0",
         {"action": "archive", "motivo": "  "}, False),
        ("reason IS NULL OR length(btrim(reason, E' \\t\\r\\n')) >= 3", {"reason": "\t ab \n"}, False),
        ("jsonb_typeof(criterios) = 'array' AND cardinality(tags) BETWEEN 1 AND 2",
         {"criterios": [1], "tags": ["a"]}, True),
        ("tipos <@ ARRAY['a', 'b']::text[] AND n > 0", {"tipos": ["a", "c"], "n": 1}, False),
        ("(origem = 'gerado' AND sha ~ '^[0-9a-f]{4}$') OR (origem = 'upload' AND sha IS NULL)",
         {"origem": "gerado", "sha": "ABCD"}, False),
        ("vinculado_a IS NULL OR vinculado_a <> id", {"vinculado_a": "u1", "id": "u1"}, False),
        # pg_get_constraintdef renders IN as `= ANY (ARRAY[...])` — catalog-generated DDL (pg_dump / prod catalog)
        ("(status = ANY (ARRAY['ativa'::text, 'pausada'::text]))", {"status": "pausada"}, True),
        ("(status = ANY (ARRAY['ativa'::text, 'pausada'::text]))", {"status": "bogus"}, False),
        ("(rating = ANY (ARRAY['-1'::integer, 1]))", {"rating": -1}, True),
        ("(rating = ANY (ARRAY['-1'::integer, 1]))", {"rating": 5}, False),
        ("COALESCE(org_role, '') <> ALL (ARRAY['membro'])", {"org_role": "membro"}, False),
        ("COALESCE(org_role, '') <> ALL (ARRAY['membro'])", {"org_role": "owner"}, True),
        ("n > SOME (ARRAY[3, 7])", {"n": 5}, True),
    ])
    def test_verdicts(self, body, row, expected):
        assert _v(body, **row) is expected

    def test_sql_null_passes(self):
        assert _v("a + b = 100", a=None, b=1) is None  # NULL, not FALSE: the CHECK holds

    def test_a_column_the_row_lacks_is_not_judged(self):
        assert _v("ends_at > starts_at", ends_at="2026-01-01") is None

    @pytest.mark.parametrize("row", [
        {"a": {"x": 1}, "b": "text"},                                   # incomparable types
        {"a": "2026-01-01T10:00:00", "b": "2026-01-01T09:00:00+00:00"},  # naive vs aware
        {"a": "2026-01-01", "b": "2026-01-01T09:00:00+00:00"},           # date vs timestamp
    ])
    def test_what_the_mock_cannot_judge_faithfully_is_unknown(self, row):
        assert _v("a > b", **row) is None

    @pytest.mark.parametrize("body", [
        "social_wiring.matricula_ruido_valido(ruido) AND x > y",
        "a LIKE 'x%' AND b > 0",
        "a > (SELECT max(b) FROM t)",
        "CASE WHEN a THEN b ELSE c END",
        "a ~ '[[:digit:]]' AND b > 0",
    ])
    def test_sql_outside_the_modelled_subset_is_refused_at_compile(self, body):
        with pytest.raises(UnsupportedCheck):
            compile_check(body)

    def test_quantified_comparison_keeps_sql_null_semantics(self):
        assert _v("status = ANY (ARRAY['a', NULL])", status="b") is None  # no match, a NULL element
        assert _v("status = ANY (ARRAY['a', NULL])", status="a") is True
        assert _v("status <> ALL (ARRAY['a', NULL])", status="b") is None
        assert _v("status = ANY (ARRAY['a'])", status=None) is None
        assert compile_check("(rating = ANY (ARRAY['-1'::integer, 1]))").columns == {"rating"}

    def test_columns_are_what_the_check_reads(self):
        assert compile_check("t.a + coalesce(b, 0) > c::int").columns == {"a", "b", "c"}


class TestParseCheckSql:
    def test_checks_as_they_stand_after_the_migrations(self):
        sql = """
        CREATE TABLE s.t (
          id uuid PRIMARY KEY,
          a int CHECK (a > 0),
          b int CONSTRAINT b_pos CHECK (b >= 0),
          starts_at timestamptz, ends_at timestamptz,
          CONSTRAINT t_order CHECK (ends_at > starts_at),
          CHECK (a <> b)
        );
        ALTER TABLE s.t ADD CONSTRAINT t_sum CHECK (a + b = 100);
        ALTER TABLE s.t DROP CONSTRAINT IF EXISTS t_order,
                        ADD CONSTRAINT t_order CHECK (ends_at >= starts_at);
        ALTER TABLE s.t RENAME COLUMN b TO bee;
        ALTER TABLE s.t DROP COLUMN a;
        CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1; END $$ LANGUAGE plpgsql;
        """

        assert parse_check_sql(sql) == {"s.t": {"b_pos": "bee >= 0", "t_order": "ends_at >= starts_at"}}

    def test_unnamed_checks_get_postgres_default_names(self):
        sql = "CREATE TABLE t (a int CHECK (a > 0), b int, CHECK (a <> b));"

        assert parse_check_sql(sql) == {"public.t": {"t_a_check": "a > 0", "t_check": "a <> b"}}

    def test_rename_table_and_drop_table(self):
        sql = """
        CREATE TABLE x.old (a int, b int, CONSTRAINT ab CHECK (a < b));
        ALTER TABLE x.old RENAME TO fresh;
        CREATE TABLE x.gone (a int, b int, CHECK (a < b));
        DROP TABLE x.gone;
        """

        assert parse_check_sql(sql) == {"x.fresh": {"ab": "a < b"}}

    def test_rls_with_check_is_not_a_table_check(self):
        sql = "CREATE POLICY p ON t FOR INSERT WITH CHECK (org_id = auth.uid() AND a > b);"

        assert parse_check_sql(sql) == {}


@pytest.fixture
def window_table():
    set_cache_for_tests({"public.slots": {"id", "starts_at", "ends_at", "note"}})
    set_checks_for_tests({"public.slots": {"slots_order": "ends_at > starts_at"}})
    yield MockSupabaseClient()
    reset_cache()


class TestMockEnforces:
    def test_violating_insert_raises(self, window_table):
        with pytest.raises(MockRowCheckViolation, match='"slots_order"'):
            window_table.table("slots").insert(
                {"id": "1", "starts_at": "2026-01-02T10:00:00Z", "ends_at": "2026-01-02T09:00:00Z"}
            ).execute()

    def test_satisfying_insert_passes(self, window_table):
        window_table.table("slots").insert(
            {"id": "1", "starts_at": "2026-01-02T10:00:00Z", "ends_at": "2026-01-02T11:00:00Z"}
        ).execute()

    def test_batch_insert_judges_every_row(self, window_table):
        with pytest.raises(MockRowCheckViolation):
            window_table.table("slots").insert([
                {"id": "1", "starts_at": "2026-01-02T10:00:00Z", "ends_at": "2026-01-02T11:00:00Z"},
                {"id": "2", "starts_at": "2026-01-02T10:00:00Z", "ends_at": "2026-01-02T10:00:00Z"},
            ]).execute()

    def test_violating_update_and_upsert_raise(self, window_table):
        bad = {"starts_at": "2026-01-02T10:00:00Z", "ends_at": "2026-01-01T10:00:00Z"}
        with pytest.raises(MockRowCheckViolation):
            window_table.table("slots").update(bad).eq("id", "1").execute()
        with pytest.raises(MockRowCheckViolation):
            window_table.table("slots").upsert({"id": "1", **bad}).execute()

    def test_an_insert_omitting_a_required_column_is_born_null(self):
        """The original incident shape (`atendimento_contrato_versoes`,
        2026-09-22): an INSERT that simply leaves out the columns a
        `_por_origem` CHECK requires. Postgres stores NULL and refuses it."""
        set_cache_for_tests({"public.versoes": {"id", "origem", "docx_path"}})
        set_checks_for_tests({"public.versoes": {
            "versoes_por_origem": "(origem = 'gerado' AND docx_path IS NOT NULL) OR origem = 'upload'",
        }})
        try:
            with pytest.raises(MockRowCheckViolation, match="docx_path=None"):
                MockSupabaseClient().table("versoes").insert({"id": "1", "origem": "gerado"}).execute()
        finally:
            reset_cache()

    def test_an_omitted_column_with_a_default_is_not_guessed(self):
        set_cache_for_tests({"public.split": {"id", "pct_a", "pct_b"}})
        set_checks_for_tests({"public.split": {"split_100": "pct_a + pct_b = 100"}},
                             defaults={"public.split": {"pct_b"}})
        try:
            MockSupabaseClient().table("split").insert({"id": "1", "pct_a": 10}).execute()
        finally:
            reset_cache()

    def test_a_single_column_check_is_enforced_too(self):
        """The igig notifications case (2026-10-10): `type IN (...)` refused
        every product kind in production while the suite stayed green."""
        set_cache_for_tests({"public.notifications": {"id", "type"}})
        set_checks_for_tests({"public.notifications": {
            "notifications_type_check": "type IN ('team_invite', 'system')",
        }})
        try:
            with pytest.raises(MockRowCheckViolation, match="notifications_type_check"):
                MockSupabaseClient().table("notifications").insert({"id": "1", "type": "automacao"}).execute()
            MockSupabaseClient().table("notifications").insert({"id": "2", "type": "system"}).execute()
        finally:
            reset_cache()

    def test_a_patch_without_every_column_is_not_judged(self, window_table):
        window_table.table("slots").update({"ends_at": "2000-01-01T00:00:00Z"}).eq("id", "1").execute()

    def test_off_with_schema_validation(self):
        set_cache_for_tests({"public.slots": {"id", "starts_at", "ends_at"}})
        set_checks_for_tests({"public.slots": {"slots_order": "ends_at > starts_at"}})
        try:
            MockSupabaseClient(validate_schema=False).table("slots").insert(
                {"id": "1", "starts_at": "2026-01-02T10:00:00Z", "ends_at": "2026-01-01T10:00:00Z"}
            ).execute()
        finally:
            reset_cache()
