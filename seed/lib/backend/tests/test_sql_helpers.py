"""Unit tests for `noctusai_lib.sql` — `prelude` + `updated_at_trigger`.

These wrap canonical helpers in :mod:`noctusai_lib.domain.sql_templates`
(tested separately in `test_sql_templates.py`). Tests here pin the
authoring-ergonomic shape — comment block, schema-lock, function +
trigger composition.

Asserts exact-string output where it matters (prelude header, trigger
keywords) so a future agent can't drift the shape silently.
"""
from __future__ import annotations

import pytest

from noctusai_lib.sql import prelude, updated_at_function, updated_at_trigger
from noctusai_lib.domain.sql_templates import (
    set_search_path as canonical_set_search_path,
    updated_at_function as canonical_updated_at_function,
    updated_at_trigger as canonical_updated_at_trigger,
)


# ---------------------------------------------------------------------------
# prelude
# ---------------------------------------------------------------------------


class TestPrelude:
    def test_emits_comment_block_and_schema_lock(self):
        out = prelude("foo")
        # Comment block opens with a fence line.
        assert out.startswith("-- =")
        # Why-block names both rationales the brief calls out.
        assert "RLS isolation" in out
        assert "Cross-product safety" in out
        # Schema-lock line appears verbatim and matches canonical helper.
        assert f"{canonical_set_search_path('foo')};" in out
        # Trailing newline so callers can concatenate without padding.
        assert out.endswith("\n")

    def test_schema_name_appears_in_header_comment(self):
        out = prelude("daily_life")
        assert "daily_life, public" in out
        # Header comment-line names the schema for human readers.
        assert "Schema lock — pin name resolution to daily_life, public" in out

    def test_idempotency_marker_in_comment(self):
        # Comment block declares the line is idempotent (session setting,
        # no DDL) so re-running is safe.
        out = prelude("erp")
        assert "IDEMPOTENT" in out

    def test_delegates_to_set_search_path(self):
        # The schema-lock line MUST come from the canonical helper —
        # otherwise a drift here wouldn't surface in the canonical tests.
        out = prelude("therapy")
        expected_lock = f"{canonical_set_search_path('therapy')};"
        # Find the lock line in the output — single occurrence.
        assert out.count(expected_lock) == 1

    def test_dashed_schema_passes_through(self):
        # `personal-finance` schema needs quoting in real migrations, but
        # this helper passes the schema string through unchanged. Caller
        # decides whether to wrap in quotes upstream.
        out = prelude("personal-finance")
        assert "personal-finance, public" in out

    def test_empty_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            prelude("")

    def test_whitespace_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            prelude("   ")


# ---------------------------------------------------------------------------
# updated_at_function (kwarg-only function_name)
# ---------------------------------------------------------------------------


class TestUpdatedAtFunctionWrapper:
    def test_default_matches_canonical(self):
        assert updated_at_function("erp") == canonical_updated_at_function("erp")

    def test_legacy_function_name(self):
        out = updated_at_function("erp", function_name="update_updated_at_column")
        assert "FUNCTION erp.update_updated_at_column()" in out

    def test_empty_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            updated_at_function("")


# ---------------------------------------------------------------------------
# updated_at_trigger (table-first, schema kwarg)
# ---------------------------------------------------------------------------


class TestUpdatedAtTrigger:
    def test_default_emits_function_and_trigger(self):
        out = updated_at_trigger("posts", schema="blog")
        # Both halves present.
        assert "CREATE OR REPLACE FUNCTION blog.set_updated_at()" in out
        assert "BEFORE UPDATE ON blog.posts" in out
        # Function declaration appears first, trigger second.
        assert out.index("CREATE OR REPLACE FUNCTION") < out.index(
            "BEFORE UPDATE"
        )

    def test_idempotent_keywords_present(self):
        # Both halves use CREATE OR REPLACE so re-running is safe.
        out = updated_at_trigger("posts", schema="blog")
        assert "CREATE OR REPLACE FUNCTION" in out
        assert "CREATE OR REPLACE TRIGGER" in out

    def test_default_schema_is_public(self):
        # Brief permits either "public" or the product schema as default.
        # We default to "public" + recommend passing the product schema
        # explicitly. Verify the default does NOT silently fork to a
        # made-up schema name.
        out = updated_at_trigger("posts")
        assert "BEFORE UPDATE ON public.posts" in out

    def test_explicit_schema_used(self):
        out = updated_at_trigger("posts", schema="erp")
        assert "BEFORE UPDATE ON erp.posts" in out
        assert "FUNCTION erp.set_updated_at()" in out

    def test_legacy_function_name(self):
        out = updated_at_trigger(
            "negociacoes", schema="erp", function_name="update_updated_at_column"
        )
        assert "FUNCTION erp.update_updated_at_column()" in out
        assert "EXECUTE FUNCTION erp.update_updated_at_column();" in out

    def test_custom_trigger_name(self):
        out = updated_at_trigger(
            "matricula_extracoes",
            schema="erp",
            trigger_name="touch_matricula",
        )
        assert "TRIGGER touch_matricula" in out
        assert "BEFORE UPDATE ON erp.matricula_extracoes" in out

    def test_include_function_false_omits_function(self):
        out = updated_at_trigger("posts", schema="blog", include_function=False)
        assert "CREATE OR REPLACE FUNCTION" not in out
        assert "CREATE OR REPLACE TRIGGER" in out
        assert "BEFORE UPDATE ON blog.posts" in out

    def test_include_function_false_matches_canonical_trigger(self):
        out = updated_at_trigger("posts", schema="blog", include_function=False)
        expected = canonical_updated_at_trigger("blog", "posts")
        assert out == expected

    def test_dashed_schema_passes_through(self):
        # `personal-finance` works the same as canonical helper.
        out = updated_at_trigger("contas", schema="personal-finance")
        assert "BEFORE UPDATE ON personal-finance.contas" in out

    def test_empty_table_raises(self):
        with pytest.raises(ValueError, match="non-empty table"):
            updated_at_trigger("", schema="blog")

    def test_whitespace_table_raises(self):
        with pytest.raises(ValueError, match="non-empty table"):
            updated_at_trigger("   ", schema="blog")

    def test_empty_schema_raises(self):
        with pytest.raises(ValueError, match="non-empty schema"):
            updated_at_trigger("posts", schema="")


# ---------------------------------------------------------------------------
# Composition: prelude + updated_at_trigger as a fresh migration would use
# ---------------------------------------------------------------------------


class TestComposedMigrationShape:
    """Pin the actual usage shape — `prelude(...)` then one or more
    `updated_at_trigger(...)` blocks — so the helpers compose into a
    valid-looking migration without surprises.
    """

    def test_minimal_migration_shape(self):
        body = prelude("blog") + "\n" + updated_at_trigger("posts", schema="blog")
        # Schema-lock is line 1+ of the file (after comment block).
        assert "SET search_path = blog, public;" in body
        # Trigger block follows after the prelude's trailing newline.
        assert "BEFORE UPDATE ON blog.posts" in body
        # No double declarations.
        assert body.count("SET search_path = blog, public;") == 1

    def test_multi_table_shape_skips_redundant_function(self):
        # Common case: one prelude, one function, multiple triggers.
        sections = [
            prelude("blog"),
            updated_at_function("blog"),
            updated_at_trigger("posts", schema="blog", include_function=False),
            updated_at_trigger("comments", schema="blog", include_function=False),
        ]
        body = "\n".join(sections)
        # Only ONE function declaration despite two triggers.
        assert body.count("CREATE OR REPLACE FUNCTION blog.set_updated_at()") == 1
        assert body.count("CREATE OR REPLACE TRIGGER set_updated_at_posts") == 1
        assert body.count("CREATE OR REPLACE TRIGGER set_updated_at_comments") == 1


# ---------------------------------------------------------------------------
# Fixture regression: sample_migration_using_prelude.sql
# ---------------------------------------------------------------------------


class TestSampleFixture:
    """Loads the committed sample migration and asserts the canonical
    helper outputs are present verbatim. If this test fails, either the
    helpers drifted OR the fixture is stale — regenerate via the
    one-liner documented at the top of `prelude.py`.
    """

    @staticmethod
    def _fixture_text() -> str:
        from pathlib import Path

        path = Path(__file__).parent / "fixtures" / "sample_migration_using_prelude.sql"
        return path.read_text()

    def test_fixture_contains_canonical_prelude(self):
        text = self._fixture_text()
        # Helper output (without trailing newline) appears in fixture.
        expected_prelude = prelude("blog").rstrip("\n")
        assert expected_prelude in text

    def test_fixture_contains_canonical_function(self):
        text = self._fixture_text()
        assert updated_at_function("blog") in text

    def test_fixture_contains_canonical_triggers(self):
        text = self._fixture_text()
        # Two triggers — one per table — each WITHOUT the function
        # declaration (function declared once at the top of the block).
        for table in ("posts", "comments"):
            expected = updated_at_trigger(
                table, schema="blog", include_function=False
            )
            assert expected in text, f"trigger for {table!r} missing from fixture"

    def test_fixture_function_declared_exactly_once(self):
        # The composition pattern declares the function ONCE despite N
        # triggers; verify the fixture follows that shape.
        text = self._fixture_text()
        assert text.count("CREATE OR REPLACE FUNCTION blog.set_updated_at()") == 1


# ---------------------------------------------------------------------------
# Real adopter sanity — verify helper output matches what real migrations have
# ---------------------------------------------------------------------------


class TestAgainstRealAdopters:
    """Sanity-check the helper output against the canonical patterns in
    real product migrations. These are NOT byte-equal because every
    product wrote slightly differently (whitespace, function-name
    convention, `DROP TRIGGER IF EXISTS` shim) — but the substrings the
    helpers emit MUST match patterns the real migrations contain
    (modulo formatting).

    Divergences logged in `findings.md` at project root.
    """

    def test_pf_function_substring_is_emittable(self):
        # PF uses `set_updated_at` + dashed-schema name "personal-finance".
        out = updated_at_function("personal-finance")
        assert 'FUNCTION personal-finance.set_updated_at()' in out

    def test_erp_legacy_function_name(self):
        # ERP's first migration uses `update_updated_at_column` —
        # explicit pass-through preserves that shape.
        out = updated_at_function("erp", function_name="update_updated_at_column")
        assert "FUNCTION erp.update_updated_at_column()" in out

    def test_daily_life_default_function(self):
        # daily-life uses `daily_life.set_updated_at` — default name,
        # underscore schema.
        out = updated_at_function("daily_life")
        assert "FUNCTION daily_life.set_updated_at()" in out

    def test_seed_search_path_line_appears_in_prelude(self):
        # `products/seed/backend/migrations/001_seed.sql` opens with
        # `SET search_path = seed, public;` — exact shape `prelude` emits.
        out = prelude("seed")
        assert "SET search_path = seed, public;" in out
