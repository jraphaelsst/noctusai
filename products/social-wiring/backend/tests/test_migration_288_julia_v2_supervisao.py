"""Structural tests for ``*_julia_v2_supervisao.sql`` (julia-v2 G1 + G3; parse-based -- the migration is a FILE, not an
applied change). Behaviour of every guard is proven on a real Postgres chain by
mcp/noctusai/tests/test_sw_maya_blocos_probes_on_replay.py (the maya probes now include this migration's)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "julia_v2_supervisao")


@pytest.fixture(scope="module")
def sql():
    raw = MIGRATION.read_text(encoding="utf-8")
    code = re.sub(r"--[^\n]*", "", raw)
    return " ".join(code.split())


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_forward_only_and_idempotent(sql):
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in upper
    assert "SET search_path = social_wiring, public;" in sql
    assert sql.count("ADD COLUMN") == sql.count("ADD COLUMN IF NOT EXISTS") == 2
    # every ADD CONSTRAINT is preceded by its DROP ... IF EXISTS
    assert sql.count("ADD CONSTRAINT") == sql.count("DROP CONSTRAINT IF EXISTS") == 3


def test_split_columns_target_the_renamed_table_not_the_compat_view(sql):
    assert "ALTER TABLE social_wiring.julia_interacoes ADD COLUMN IF NOT EXISTS primeira_resposta_agente_at timestamptz" in sql
    assert "ALTER TABLE social_wiring.julia_interacoes ADD COLUMN IF NOT EXISTS primeira_resposta_humana_at timestamptz" in sql
    assert "lais_" not in sql


def test_legacy_column_is_kept_and_marked_for_a_later_drop(sql):
    assert "NOC-REMEDIATE[drop-primeira-resposta-at]" in MIGRATION.read_text(encoding="utf-8")
    assert "COMMENT ON COLUMN social_wiring.julia_interacoes.primeira_resposta_at IS 'DEPRECATED" in sql


def test_backfill_is_provable_only_and_never_overwrites(sql):
    # only where an outbound message of that kind sits within +-5 s of the old stamp; fills NULLs only
    assert sql.count("interval '5 seconds'") == 4
    assert "m.structured_payload ->> 'origem' = 'julia'" in sql
    assert "COALESCE(m.structured_payload ->> 'origem', '') <> 'julia'" in sql
    assert sql.count("WHERE i.primeira_resposta_") == 2 and "primeira_resposta_agente_at IS NULL" in sql


def test_gatilho_gains_the_accept_trigger(sql):
    m = re.search(r"CONSTRAINT atendimento_handoffs_gatilho_valido CHECK \(gatilho IN \(([^)]*)\)", sql)
    assert m
    assert {v.strip().strip("'") for v in m.group(1).split(",")} == {"novo_lead", "movimento_etapa", "aceite_proposta"}


def test_no_security_definer_and_no_new_table(sql):
    assert "SECURITY DEFINER" not in sql.upper() and "CREATE TABLE" not in sql.upper()
