"""Structural tests for the `lais_agente_roteamento` migration (Julia routing fields, contract 5 / 10.1 H3 /
11.1 / 11.4). The migration is a FILE, not an applied change; these pin the DECLARED shape. The CHECK
behaviour is exercised against the mock (derived from this very file) in
`routers/test_lais_agente_routes.py::TestAuthorizedNumbersPatch`, and the whole chain is replayed on
PGlite (twice) by the pre-commit `migration_replay` gate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_agente_roteamento")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file()
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


@pytest.mark.parametrize("fragment", [
    "ADD COLUMN IF NOT EXISTS agente_leads_ativo boolean NOT NULL DEFAULT false",
    "ADD COLUMN IF NOT EXISTS agente_leads_key text",
    "ADD COLUMN IF NOT EXISTS agente_leads_ativado_em timestamptz",
    "ADD COLUMN IF NOT EXISTS agente_handoff_notificar_user_id uuid",
    "ADD COLUMN IF NOT EXISTS agente_pausado boolean NOT NULL DEFAULT false",
    "ADD COLUMN IF NOT EXISTS agente_conversation_id uuid",
])
def test_the_contract_5_columns_are_declared_idempotently(flat, fragment):
    assert fragment in flat


def test_h3_the_invariant_is_a_db_check_not_only_application_code(flat):
    assert "whatsapp_connections_agente_exige_autorizados" in flat
    assert "NOT agente_leads_ativo OR ( jsonb_typeof(authorized_numbers) = 'array' AND jsonb_array_length(authorized_numbers) > 0 )" in flat
    assert "NOT agente_leads_ativo OR (agente_leads_ativado_em IS NOT NULL AND agente_leads_key IS NOT NULL)" in flat


def test_constraints_are_dropped_before_being_added_so_a_re_apply_is_safe(flat):
    assert flat.count("DROP CONSTRAINT IF EXISTS") == flat.count("ADD CONSTRAINT") == 2


def test_snapshot_table_shape_and_pk(flat):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.lais_agente_chats_preexistentes" in flat
    assert "PRIMARY KEY (connection_id, chat_id)" in flat
    for col in ("org_id uuid NOT NULL", "connection_id uuid NOT NULL", "chat_id text NOT NULL", "capturado_em timestamptz NOT NULL DEFAULT now()"):
        assert col in flat


def test_snapshot_table_rls_own_org_select_and_service_role_write(flat):
    assert "ENABLE ROW LEVEL SECURITY" in flat
    assert "FOR SELECT TO authenticated USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert "FOR ALL TO service_role USING (true) WITH CHECK (true)" in flat
    assert "anon" not in flat


def test_no_double_dash_inside_a_string_literal(sql):
    """The migration-derived mock schema parser strips `--` comments before tokenizing, so a
    `--` inside a quoted string swallows every statement after it (found on this migration)."""
    for stmt in re.findall(r"'((?:[^']|'')*)'", "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))):
        assert "--" not in stmt, stmt


def test_it_never_touches_rows_or_drops_anything_destructive(flat):
    for bad in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE", "UPDATE social_wiring"):
        assert bad not in flat
