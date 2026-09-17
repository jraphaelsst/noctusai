"""Structural tests for `011_credentials_whatsapp_connections.sql`.

The migration is a FILE, not an applied change — it needs tech-lead
consent to run against any database. These assert its *structure* by
parsing it (the only honest verification available before it is
applied), pinning that:

1. Both tables carry RLS, `current_org_id()` (not `auth.jwt()`) on the
   authenticated SELECT policy, and a service_role bypass policy.
2. Neither table grants anything to `anon`.
3. The DDL matches the verbatim output of the seed helpers this
   migration is derived from (`credentials_table_ddl` /
   `whatsapp_connections_table_ddl`) for `schema="community"` — this is
   what makes it "from the seed DDL helpers" rather than a hand-copy
   that silently drifted. The bypass-policy name is normalized before
   comparing (this migration renames the helper's shared
   `"service_role_bypass"` to a per-table
   `"<table>_service_role_bypass"` — functionally identical; Postgres
   policy names are unique per-table, not per-schema).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "011_credentials_whatsapp_connections.sql"
)
_SEED_LIB = Path(__file__).resolve().parents[4] / "seed" / "lib" / "backend"
if str(_SEED_LIB) not in sys.path:
    sys.path.insert(0, str(_SEED_LIB))


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    normalized = code.replace(
        "credentials_service_role_bypass", "service_role_bypass"
    ).replace(
        "whatsapp_connections_service_role_bypass", "service_role_bypass"
    )
    return " ".join(normalized.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_search_path_locked_to_community(sql: str):
    assert "SET search_path = community, public;" in sql


@pytest.mark.parametrize("table", ["credentials", "whatsapp_connections"])
def test_rls_enabled_with_org_scoped_select(flat: str, table: str):
    assert f"ALTER TABLE community.{table} ENABLE ROW LEVEL SECURITY;" in flat
    assert (
        f'CREATE POLICY "{table}_select_own_org" ON community.{table} '
        "FOR SELECT TO authenticated USING (org_id = current_org_id());"
    ) in flat
    # The broken top-level-JWT-claim form migration 004 codified the fix
    # for must never recur here.
    assert "auth.jwt()" not in flat


@pytest.mark.parametrize("table", ["credentials", "whatsapp_connections"])
def test_service_role_bypass_present(flat: str, table: str):
    assert (
        f"CREATE POLICY \"service_role_bypass\" ON community.{table} "
        "FOR ALL TO service_role USING (true) WITH CHECK (true);"
    ) in flat


def test_no_anon_grants(code: str):
    assert "anon" not in code.lower()


def test_credentials_matches_seed_ddl_helper(flat: str):
    from noctusai_lib.security.api_keys import credentials_table_ddl

    expected = " ".join(credentials_table_ddl("community").split())
    assert expected in flat


def test_whatsapp_connections_matches_seed_ddl_helper(flat: str):
    from noctusai_lib.integrations.whatsapp.connection_store import whatsapp_connections_table_ddl

    expected = " ".join(whatsapp_connections_table_ddl("community").split())
    assert expected in flat
