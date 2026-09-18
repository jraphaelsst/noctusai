"""Structural (parse-based) tests for `048_storage_no_public_buckets.sql`.

Pins the forward fix for the 2026-09-17 erp-certidoes public-bucket leak:
both `erp-certidoes` / `erp-geral` flip to `public = false` (idempotent —
the historical `public = true` declarations in 001/011 are IMMUTABLE and
are NOT edited here), `certidao_resultados` gains `arquivo_path`, and the
existing public-URL rows are backfilled path-only, idempotently.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "048_storage_no_public_buckets.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DELETE FROM" not in code
    assert "DROP COLUMN" not in code


def test_does_not_edit_historical_migrations():
    """001/011 stay untouched (immutable history) — this migration is the
    forward record instead. Both still carry their ORIGINAL `true` bucket
    declaration, unedited."""
    hist_001 = MIGRATION.parent / "001_erp_imobiliario.sql"
    hist_011 = MIGRATION.parent / "011_storage_buckets.sql"
    assert "('erp-certidoes', 'erp-certidoes', true)" in hist_001.read_text(encoding="utf-8")
    assert "('erp-certidoes', 'erp-certidoes', true)" in hist_011.read_text(encoding="utf-8")


def test_buckets_flip_to_private_idempotently(flat: str):
    assert (
        "UPDATE storage.buckets SET public = false WHERE id IN "
        "('erp-certidoes', 'erp-geral') AND public = true;" in flat
    )


def test_arquivo_path_column_added_if_not_exists(flat: str):
    assert (
        "ALTER TABLE erp.certidao_resultados "
        "ADD COLUMN IF NOT EXISTS arquivo_path text;" in flat
    )


def test_backfill_moves_path_and_clears_url(flat: str):
    """The backfill UPDATE must set BOTH `arquivo_path` (extracted) and
    `arquivo_url = NULL` in the SAME statement — a stale public-route URL
    must never survive alongside the new path."""
    assert "arquivo_path = split_part(" in flat
    assert "arquivo_url = NULL" in flat
    assert "/object/public/erp-certidoes/" in flat


def test_backfill_where_clause_is_re_run_safe(flat: str):
    """The WHERE clause matches only rows whose `arquivo_url` still has the
    old public-URL shape — once a row is migrated (`arquivo_url` is NULL),
    `arquivo_url LIKE '%...%'` no longer matches it. A second run of this
    migration therefore finds zero matching rows — idempotent by
    construction, not merely by an `IF NOT EXISTS` guard."""
    backfill_stmt = flat.split("UPDATE erp.certidao_resultados", 1)[1].split(";", 1)[0]
    assert "arquivo_url LIKE" in backfill_stmt
    assert "/object/public/erp-certidoes/" in backfill_stmt


def test_query_string_suffix_is_stripped(flat: str):
    """`get_public_url` historically appended `?...` to the URL (the same
    shape `_delete_storage_files` used to strip) — the backfill must strip
    it too, or `arquivo_path` would carry a bogus `?` suffix."""
    assert "split_part(" in flat
    assert "'?', 1" in flat


def test_ends_with_schema_reload(code: str):
    assert code.strip().endswith("NOTIFY pgrst, 'reload schema';")
