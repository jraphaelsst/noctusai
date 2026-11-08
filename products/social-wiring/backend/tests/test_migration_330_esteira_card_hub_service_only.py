"""Structural tests for ``*_esteira_card_hub_service_only.sql`` (security triage 2026-11-07): the Esteira card hub
(cs_post_* + cs_posts/cs_equipe) and the ``sw-esteira`` bucket are service-only. Behaviour on real Postgres: pre-commit PGlite replay."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = migration_path(ROOT, "esteira_card_hub_service_only")
ESTEIRA_241 = migration_path(ROOT, "cs_esteira")
EXTRA = {"cs_equipe", "cs_posts"}


def _strip(text: str) -> str:
    return " ".join(re.sub(r"--[^\n]*", "", text).split())


@pytest.fixture(scope="module")
def sql():
    return _strip(MIGRATION.read_text(encoding="utf-8"))


def _hub_tables() -> set[str]:
    text = ESTEIRA_241.read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS social_wiring\.(cs_post_\w+)", text)) | EXTRA


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_covers_every_esteira_hub_table(sql):
    tables = _hub_tables()
    assert len(tables) == 13
    for t in tables:
        assert f"REVOKE ALL ON TABLE social_wiring.{t} FROM PUBLIC, anon, authenticated;" in sql
        assert f"GRANT ALL ON TABLE social_wiring.{t} TO service_role;" in sql
        assert f"COMMENT ON TABLE social_wiring.{t} IS 'tier:org';" in sql


def test_drops_every_authenticated_policy_of_241(sql):
    text = _strip(ESTEIRA_241.read_text(encoding="utf-8"))
    found = re.findall(
        r'CREATE POLICY "?([\w-]+)"? ON social_wiring\.(\w+) FOR \w+ TO authenticated', text
    )
    assert len(found) >= 12
    for name, table in found:
        assert f'DROP POLICY IF EXISTS "{name}" ON social_wiring.{table};' in sql


def test_bucket_authenticated_policies_dropped_service_kept(sql):
    for cmd in ("select", "insert", "update", "delete"):
        assert f'DROP POLICY IF EXISTS "sw-esteira_storage_{cmd}" ON storage.objects;' in sql
    assert "sw-esteira_storage_service" not in sql


def test_forward_only(sql):
    up = sql.upper()
    for bad in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "SECURITY DEFINER", "DISABLE ROW LEVEL SECURITY"):
        assert bad not in up
