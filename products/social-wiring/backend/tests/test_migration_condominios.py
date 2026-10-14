"""Structural pins for the condominios migration (resolved by NAME, never number)."""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "condominios")
CODE = "\n".join(l for l in SQL.splitlines() if not l.strip().startswith("--"))


@pytest.mark.parametrize("t", ["condominios", "condominio_aliases", "condominio_eventos"])
def test_rls_on_and_no_authenticated_writes(t):
    assert f"ALTER TABLE social_wiring.{t} ENABLE ROW LEVEL SECURITY" in CODE
    assert f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.{t} FROM anon, authenticated" in CODE
    assert f'ON social_wiring.{t}\n    FOR SELECT TO authenticated' in CODE.replace('"' + t + '_select_own_org" ', "").replace(
        f'CREATE POLICY "{t}_select_own_org" ', "")


def test_alias_unique_per_org_and_name_unique_per_org_cidade():
    assert "UNIQUE (org_id, alias_normalizado)" in CODE
    assert "(org_id, nome_normalizado, COALESCE(cidade, ''))" in CODE


def test_eventos_append_only_trigger():
    assert "BEFORE UPDATE OR DELETE ON social_wiring.condominio_eventos" in CODE


def test_view_is_security_invoker_and_manual_wins():
    assert "security_invoker = true" in CODE
    assert CODE.index("empreendimento_manual") < CODE.index("i.empreendimento)")


def test_status_pagina_row_seeded_producao():
    assert "('condominios', 'producao')" in CODE and "ON CONFLICT (nome_pagina) DO NOTHING" in CODE


def test_no_write_to_the_vista_mirror():
    for verb in ("UPDATE social_wiring.imoveis", "INSERT INTO social_wiring.imoveis", "DELETE FROM social_wiring.imoveis"):
        assert verb not in CODE
