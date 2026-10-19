"""Structural tests for ``*_simec.sql`` (parse-based — the migration is a
FILE, not an applied change)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "simec")
TABLES = ("simec_configs", "simec_config_historico", "simec_readouts", "simec_leituras")


@pytest.fixture(scope="module")
def sql():
    raw = MIGRATION.read_text(encoding="utf-8")
    code = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--"))
    code = re.sub(r"--[^\n]*", "", code)
    return " ".join(code.split())


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_forward_only_and_idempotent(sql):
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in upper
    assert "SET search_path = social_wiring, public;" in sql
    for t in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS social_wiring.{t} (" in sql
    assert sql.count("CREATE INDEX") == sql.count("CREATE INDEX IF NOT EXISTS")
    assert sql.count("CREATE UNIQUE INDEX") == sql.count("CREATE UNIQUE INDEX IF NOT EXISTS")
    assert sql.count("CREATE POLICY") == sql.count("DROP POLICY IF EXISTS")
    assert "SECURITY DEFINER" not in sql.upper()


@pytest.mark.parametrize("table", TABLES)
def test_rls_org_scoped_like_siblings(sql, table):
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert (
        f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} '
        "FOR SELECT TO authenticated "
        "USING (org_id = (SELECT public.current_org_id_for('social_wiring')));"
    ) in sql
    assert (
        f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} '
        "FOR ALL TO service_role USING (true) WITH CHECK (true);"
    ) in sql


def test_one_layer_per_org_and_per_profile(sql):
    assert "ON social_wiring.simec_configs (org_id, platform) WHERE account_id IS NULL" in sql
    assert "ON social_wiring.simec_configs (org_id, platform, account_id) WHERE account_id IS NOT NULL" in sql


def test_readouts_are_traceable(sql):
    for col in ("config_version text NOT NULL", "config_fingerprint text NOT NULL",
                "config jsonb NOT NULL", "source text NOT NULL"):
        assert col in sql
    assert "CHECK (config_fingerprint ~ '^[0-9a-f]{64}$')" in sql


def test_reading_statuses_match_the_seed_enum(sql):
    from noctusai_lib.domain.content_performance import ReadingStatus

    stored = {s.value for s in ReadingStatus} - {"vazio"}  # empty readings are never stored
    m = re.search(r"simec_leituras_status_valido CHECK \(status IN \(([^)]*)\)\)", sql)
    assert m, "status CHECK missing"
    assert {v.strip().strip("'") for v in m.group(1).split(",")} == stored


def test_page_seeded_in_development(sql):
    assert "VALUES ('simec', 'desenvolvimento'," in sql
    assert "ON CONFLICT (nome_pagina) DO NOTHING" in sql
