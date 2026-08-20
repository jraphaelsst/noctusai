"""Structural tests for `062_codigo_imovel_canonical.sql`.

The migration is a FILE, not an applied change — it needs tech-lead consent
to run against any database. So these assert its *structure* by parsing it,
which is the only honest verification available before it is applied. Same
convention as `test_migration_040_imoveis.py`.

The load-bearing assertion is the last class: the SQL trigger and the
Python parser must produce the SAME canonical form. The trigger is BEFORE
INSERT, so a disagreement means the API echoes one value while the DB
holds another — the exact failure `parse_contato` documents against
`canonicalize_lead_contato()` (migration 037). Here it is executable
rather than a comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.leads.importer.parsers import parse_codigo

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "062_codigo_imovel_canonical.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped, so prose never satisfies a check."""
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


class TestMirrorSide:
    def test_codigo_norm_is_a_stored_generated_column(self, code: str):
        """Generated, not trigger-maintained: Postgres then guarantees it
        can never drift from `codigo`, and there is no write path to
        forget."""
        assert "GENERATED ALWAYS AS (upper(btrim(codigo))) STORED" in code

    def test_codigo_norm_index_is_unique(self, code: str):
        """Two rows differing ONLY by case would mean Vista is serving the
        same imóvel twice. That must fail loudly, not silently upsert one
        over the other."""
        assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_imoveis_org_codigo_norm" in code

    def test_index_is_org_scoped(self, code: str):
        """`codigo` is unique per TENANT, not globally — an unscoped unique
        index would reject a second org's identical code."""
        assert "uq_sw_imoveis_org_codigo_norm\n    ON social_wiring.imoveis (org_id, codigo_norm)" in code


class TestLeadsSide:
    def test_raw_column_is_never_updated(self, code: str):
        """The original spelling must survive — that is what makes the
        backfill reversible with no extra column."""
        assert "SET codigo_imovel =" not in code
        assert "NEW.codigo_imovel :=" not in code

    def test_trigger_fires_before_insert_and_targeted_update(self, code: str):
        assert "BEFORE INSERT OR UPDATE OF codigo_imovel ON social_wiring.leads" in code

    def test_trigger_is_dropped_before_create(self, code: str):
        """Idempotency: a re-run must not fail on an existing trigger."""
        assert "DROP TRIGGER IF EXISTS canonicalize_lead_codigo_imovel_trigger" in code

    def test_function_pins_search_path(self, code: str):
        """An unpinned search_path in a SECURITY-sensitive function is the
        standard Postgres hijack surface; 037's functions all pin it."""
        assert code.count("SET search_path TO 'social_wiring', 'public'") >= 2

    def test_backfill_is_guarded_against_a_rewrite_on_rerun(self, code: str):
        assert "IS DISTINCT FROM upper(btrim(codigo_imovel))" in code

    def test_join_index_is_partial(self, code: str):
        """2030 of 13405 leads carry no código and can never satisfy the
        join."""
        assert "WHERE codigo_imovel_norm IS NOT NULL" in code


class TestLeadVendasGetsTheSameTreatment:
    def test_vendas_column_exists(self, code: str):
        assert "ALTER TABLE social_wiring.lead_vendas" in code

    def test_vendas_trigger_exists(self, code: str):
        assert "BEFORE INSERT OR UPDATE OF codigo_imovel ON social_wiring.lead_vendas" in code


class TestNoShapeFilter:
    def test_norm_is_not_null_gated_on_the_product_code_pattern(self, code: str):
        """Case-folding guesses nothing, so there is no unsafe value to
        withhold. A shape filter would hide a one-letter-prefix code like
        `P0601` from the query a human would use to find it."""
        assert "[A-Z]{2,4}" not in code


class TestSqlAndPythonAgree:
    """The executable half of the migration-037 contract."""

    @pytest.mark.parametrize(
        "raw",
        ["one10107", "One10107", "ONE10107", "oNe10107", "ca0190", "CA4350", "a3282"],
    )
    def test_parser_matches_the_trigger_expression(self, raw: str):
        # The trigger body is `upper(btrim(...))`.
        sql_result = raw.strip().upper()
        codigo, _, _ = parse_codigo(raw)
        assert codigo == sql_result

    def test_trigger_body_is_still_upper_btrim(self, code: str):
        """If this expression changes, the parity test above is measuring
        the wrong thing — so pin the expression itself."""
        assert "NEW.codigo_imovel_norm := upper(v_value);" in code
        assert "v_value := btrim(COALESCE(NEW.codigo_imovel, ''));" in code

    def test_empty_becomes_null_not_empty_string(self, code: str):
        """NULL means 'no código'. An empty string would join nothing and
        also fail to read as absent."""
        assert "NEW.codigo_imovel_norm := NULL;" in code
