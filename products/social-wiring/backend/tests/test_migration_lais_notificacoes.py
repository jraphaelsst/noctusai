"""Structural tests for migration 273 `lais_notificacoes` (lais-build-contract 8). The guard's BEHAVIOUR is proven
by the `verify_db_guards` probe registered for the named CHECK."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_notificacoes")


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


def test_rls_select_own_org_and_service_role(flat):
    t = "lais_notificacao_prefs"
    assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{t}_select_own_org" ON social_wiring.{t} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{t}_service_role" ON social_wiring.{t} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_pk_and_tipo_guard(flat):
    assert "PRIMARY KEY (org_id, user_id, tipo)" in flat
    assert "CONSTRAINT lais_notificacao_prefs_tipo_valido CHECK (tipo ~ '^[a-z][a-z0-9_]{2,39}$')" in flat


def test_status_pagina_row_copies_whatsapp_chat(flat):
    assert "'lais_notificacoes'" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat
