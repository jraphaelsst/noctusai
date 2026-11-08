"""Structural tests for ``*_documentos_service_only.sql`` (security triage 2026-11-07, P1): the private documents bucket and
the card-hub ``cliente_*`` tables are service-only. Behaviour on real Postgres: pre-commit PGlite replay."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
MIGRATION = migration_path(ROOT, "documentos_service_only")
FROZEN = ("card_hub_core", "card_hub_documentos", "cliente_checklist_extras")


def _strip(text: str) -> str:
    return " ".join(re.sub(r"--[^\n]*", "", text).split())


@pytest.fixture(scope="module")
def sql():
    return _strip(MIGRATION.read_text(encoding="utf-8"))


def _cliente_tables() -> set[str]:
    found: set[str] = set()
    for f in MIGRATIONS.glob("*.sql"):
        found |= set(re.findall(r"CREATE TABLE IF NOT EXISTS social_wiring\.(cliente_\w+)", f.read_text(encoding="utf-8")))
    return found


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_drops_the_four_authenticated_storage_policies_and_keeps_service(sql):
    for cmd in ("select", "insert", "update", "delete"):
        assert f'DROP POLICY IF EXISTS "sw_documentos_storage_{cmd}" ON storage.objects;' in sql
    assert "sw_documentos_storage_service" not in sql  # kept, never dropped


def test_no_authenticated_storage_policy_for_bucket_remains_after_replay():
    """Replay the chain textually: the last statement per policy name wins."""
    state: dict[str, bool] = {}
    for f in sorted(MIGRATIONS.glob("*.sql")):
        text = re.sub(r"--[^\n]*", "", f.read_text(encoding="utf-8"))
        for m in re.finditer(
            r'DROP POLICY IF EXISTS\s+"?(\w+)"?\s+ON storage\.objects|'
            r'CREATE POLICY\s+"?(\w+)"?\s+ON storage\.objects\s+FOR\s+\w+\s+TO\s+(\w+)(.*?);',
            text,
            re.S | re.I,
        ):
            if m.group(1):
                state.pop(m.group(1), None)
            elif "social-wiring-documentos" in m.group(4):
                state[m.group(2)] = m.group(3).lower() == "authenticated"
    assert not [n for n, auth in state.items() if auth], state
    assert "sw_documentos_storage_service" in state


def test_revokes_and_tiers_every_cliente_table(sql):
    tables = _cliente_tables()
    assert len(tables) >= 19
    for t in tables:
        assert f"REVOKE ALL ON TABLE social_wiring.{t} FROM anon, authenticated;" in sql
        assert f"COMMENT ON TABLE social_wiring.{t} IS 'tier:org';" in sql


def test_drops_origens_excluidas_write_policy_keeps_select(sql):
    assert (
        'DROP POLICY IF EXISTS "cliente_origens_excluidas_write_own_org" ON social_wiring.cliente_origens_excluidas;' in sql
    )
    assert "cliente_origens_excluidas_select_own_org" not in sql


def test_default_privileges_revoked(sql):
    for obj in ("TABLES", "SEQUENCES"):
        assert (
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA social_wiring REVOKE ALL ON {obj} FROM anon, authenticated;"
            in sql
        )


def test_forward_only(sql):
    up = sql.upper()
    for bad in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "SECURITY DEFINER", "DISABLE ROW LEVEL SECURITY"):
        assert bad not in up


def test_frozen_migrations_untouched():
    paths = [f"products/social-wiring/backend/migrations/{migration_path(ROOT, n).name}" for n in FROZEN]
    out = subprocess.run(["git", "diff", "--name-only", "origin/dev", "--", *paths], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("origin/dev not resolvable")
    assert out.stdout.strip() == ""
