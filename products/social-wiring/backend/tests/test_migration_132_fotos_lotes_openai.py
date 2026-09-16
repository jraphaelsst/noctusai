"""Structural (parse-based) tests for `132_fotos_lotes_openai.sql`.

Pins: the Econômico provider-batch table carries org_id + RLS +
service_role_bypass + the batch-visibility read rule, its engine status
vocabulary matches `OpenAIBatchStatus`, and `fotos_fotos.openai_batch_id`
gets the FK the 123 header promised.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.domain.photo_editing.types import OpenAIBatchRecord, OpenAIBatchStatus

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "132_fotos_lotes_openai.sql"


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


def test_sets_search_path_and_is_forward_only(flat: str, code: str):
    assert "SET search_path = social_wiring, public;" in flat
    assert "DROP TABLE" not in code and "DROP COLUMN" not in code


def test_table_is_org_scoped_with_rls_and_bypass(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.fotos_lotes_openai" in flat
    assert "org_id UUID NOT NULL" in flat
    assert "ALTER TABLE social_wiring.fotos_lotes_openai ENABLE ROW LEVEL SECURITY" in flat
    assert (
        'CREATE POLICY "service_role_bypass" ON social_wiring.fotos_lotes_openai '
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    ) in flat
    assert (
        "USING (org_id = public.current_org_id() AND social_wiring.fotos_lote_visivel(lote_id))"
        in flat
    )


def test_status_vocabulary_matches_the_engine(flat: str):
    values = ", ".join(f"'{s.value}'" for s in OpenAIBatchStatus)
    assert f"CHECK (status IN ({values}))" in flat


def test_every_engine_field_is_a_column(code: str):
    block = code.split("CREATE TABLE IF NOT EXISTS social_wiring.fotos_lotes_openai", 1)[1]
    block = block.split(");", 1)[0]
    columns = {line.split()[0] for line in block.splitlines() if line.strip() and line.startswith("    ")}
    fields = set(OpenAIBatchRecord.__dataclass_fields__)
    assert fields <= columns, fields - columns


def test_photo_pointer_gets_its_fk(flat: str):
    assert (
        "ALTER TABLE social_wiring.fotos_fotos ADD CONSTRAINT fotos_fotos_openai_batch_id_fkey "
        "FOREIGN KEY (openai_batch_id) REFERENCES social_wiring.fotos_lotes_openai (openai_batch_id) "
        "ON DELETE SET NULL"
    ) in flat
    assert "openai_batch_id TEXT UNIQUE" in flat
