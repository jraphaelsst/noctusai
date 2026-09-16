"""Structural tests for `010_credentials_and_runtime_settings.sql` — parse-based."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "010_credentials_and_runtime_settings.sql"
)
TABLES = ("app_integration_config", "runtime_settings")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("table", TABLES)
def test_service_role_only(sql, table):
    assert f"ALTER TABLE agents.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert re.search(
        rf'CREATE POLICY "service_role_bypass" ON agents\.{table}\s+'
        r"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\)",
        sql,
    )
    assert f"REVOKE ALL ON agents.{table} FROM anon, authenticated" in sql
    assert not re.search(rf"ON agents\.{table}\s+FOR \w+ TO authenticated", sql)


def test_config_value_is_stored_encrypted_only(sql):
    body = re.search(r"CREATE TABLE IF NOT EXISTS agents\.app_integration_config \((.*?)\);", sql, re.S)
    assert body
    columns = {line.split()[0] for line in body.group(1).splitlines() if line.strip() and not line.strip().startswith("--")}
    assert columns == {"key", "encrypted_value", "updated_at"}


def test_runtime_setting_keys_match_the_service(sql):
    from app.services.runtime_settings import EDITABLE_KEYS

    check = re.search(r"CHECK \(key IN \(([^)]*)\)\)", sql)
    assert check
    assert tuple(k.strip().strip("'") for k in check.group(1).split(",")) == EDITABLE_KEYS


def test_new_nav_pages_have_status_rows(sql):
    assert "('credenciais', 'desenvolvimento')" in sql
    assert "('configuracoes-agente', 'desenvolvimento')" in sql
