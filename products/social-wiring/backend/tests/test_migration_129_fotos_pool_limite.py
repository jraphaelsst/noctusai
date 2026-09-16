"""Structural (parse-based) tests for `129_fotos_pool_limite.sql`.

Pins the pool-limit setting (pairs; NULL/0 = unlimited), the write-time
trigger that refuses a pair past the limit, and the `pool_cheio` marker the
seed repository maps to `PoolFullError`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.domain.photo_editing.repository import POOL_FULL_DB_MARKER

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "129_fotos_pool_limite.sql"


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


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


def test_limit_column_is_nullable_non_negative(flat: str):
    assert (
        "ALTER TABLE social_wiring.fotos_platform_settings "
        "ADD COLUMN IF NOT EXISTS limite_pares_referencia INTEGER "
        "CHECK (limite_pares_referencia IS NULL OR limite_pares_referencia >= 0);"
    ) in flat
    assert "NOT NULL" not in flat.split("limite_pares_referencia INTEGER")[1].split(";")[0]


def test_trigger_guards_insert_and_unarchive(flat: str):
    assert (
        "BEFORE INSERT OR UPDATE OF arquivado_em ON social_wiring.fotos_referencias"
    ) in flat
    assert "EXECUTE FUNCTION social_wiring.fotos_referencias_limite()" in flat


def test_trigger_counts_only_active_pairs_and_treats_zero_as_unlimited(flat: str):
    body = flat.split("CREATE OR REPLACE FUNCTION social_wiring.fotos_referencias_limite()")[1]
    assert "IF COALESCE(v_limite, 0) = 0 THEN RETURN NEW;" in body
    assert "FROM social_wiring.fotos_referencias WHERE arquivado_em IS NULL;" in body
    assert "IF NEW.arquivado_em IS NOT NULL THEN RETURN NEW;" in body


def test_trigger_serializes_on_the_settings_row(flat: str):
    assert "FROM social_wiring.fotos_platform_settings WHERE id = 1 FOR UPDATE;" in flat


def test_error_carries_the_marker_the_repository_maps(flat: str):
    assert f"RAISE EXCEPTION '{POOL_FULL_DB_MARKER}:" in flat


def test_function_pins_an_empty_search_path(flat: str):
    assert "LANGUAGE plpgsql SET search_path = '' AS $$" in flat
