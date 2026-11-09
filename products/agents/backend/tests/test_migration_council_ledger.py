"""Council ledger migration (073): four append-only, service-role-only record tables whose closed sets match contract §2."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1], "council_ledger")
TABELAS = ("council_sessions", "council_objections", "council_verdicts", "council_events")
CONTRACT = Path(__file__).resolve().parents[4] / "project-history/assistant-chatbot/contracts/council-ledger.md"
ENUM_COLUNAS = (
    "stage", "subject_kind", "trigger", "mode", "severity", "chair_kind", "event_kind", "outcome", "evidence_kind",
)


def _contract_enum(nome: str) -> set[str]:
    linha = next(l for l in CONTRACT.read_text().splitlines() if l.startswith(f"- `{nome}`:"))
    return set(re.findall(r"`([a-z_0-9]+)`", linha.split(":", 1)[1]))


def _sql_enum(coluna: str) -> set[str]:
    m = re.search(rf"\b{coluna} TEXT (?:NOT NULL|NULL) CHECK \((?:{coluna} IS NULL OR )?{coluna} IN \(([^)]*)\)", SQL)
    assert m, coluna
    return set(re.findall(r"'([a-z_0-9]+)'", m.group(1)))


def test_closed_sets_equal_the_contract_enums():
    for coluna in ENUM_COLUNAS:
        assert _sql_enum(coluna) == _contract_enum(coluna), coluna


def test_ids_are_writer_supplied_never_generated():
    assert "gen_random_uuid" not in SQL
    assert "DEFAULT" not in SQL


def test_tables_are_service_role_only_select_insert_and_platform_tier():
    for t in TABELAS:
        assert f"CREATE TABLE IF NOT EXISTS agents.{t}" in SQL
        assert f"ALTER TABLE agents.{t} ENABLE ROW LEVEL SECURITY" in SQL
        assert f"REVOKE ALL ON agents.{t} FROM PUBLIC, anon, authenticated" in SQL
        assert f"GRANT SELECT, INSERT ON agents.{t} TO service_role" in SQL
        assert f"COMMENT ON TABLE agents.{t} IS 'tier:platform'" in SQL
        assert f"BEFORE UPDATE OR DELETE ON agents.{t}" in SQL
    assert not re.search(r"GRANT[^;]*(UPDATE|DELETE|ALL)[^;]*TO service_role", SQL)
    assert not re.search(r"TO (anon|authenticated)\b", SQL)


def test_outcome_fields_required_exactly_for_outcome_events():
    assert "event_kind = 'outcome' AND objection_id IS NOT NULL AND outcome IS NOT NULL AND evidence_kind IS NOT NULL" in SQL
    assert "event_kind <> 'outcome' AND objection_id IS NULL" in SQL


def test_one_verdict_per_session_and_foreign_keys():
    assert "session_id UUID PRIMARY KEY REFERENCES agents.council_sessions(session_id)" in SQL
    assert "objection_id UUID NULL REFERENCES agents.council_objections(objection_id)" in SQL
