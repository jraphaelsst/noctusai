"""077: the testing-phase switch is gone -- its writer and its column are dropped (idempotently), the audit CHECK keeps
the historical action, and no live code path names the flag any more."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

BACKEND = Path(__file__).resolve().parents[1]
SQL = migration_sql(BACKEND, "remove_fase_testes")


def test_the_writer_and_the_column_are_dropped_idempotently():
    assert "DROP FUNCTION IF EXISTS agents.set_agent_fase_testes(UUID, UUID, BOOLEAN, UUID)" in SQL
    assert "ALTER TABLE agents.agents DROP COLUMN IF EXISTS fase_testes" in SQL


def test_the_audit_check_is_not_narrowed_so_old_audit_rows_stay_valid():
    assert "agent_audit_log" not in SQL.replace("--", "#").split("SET search_path")[1]


def test_no_application_code_names_the_flag():
    offenders = [
        str(f.relative_to(BACKEND)) for f in (BACKEND / "app").rglob("*.py")
        if "fase_testes" in f.read_text(encoding="utf-8")
        and f.name != "studio_definitions.py"  # the legacy audit action 'fase_testes_alterada' stays in AUDIT_ACOES
    ]
    assert offenders == []
