"""Structural tests for migration 272 `lais_visitas` (lais-build-contract 7 / 17). The guards' BEHAVIOUR is
proven by the `verify_db_guards` probes registered for each named CHECK/UNIQUE here."""
from __future__ import annotations

from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "lais_visitas")


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    return " ".join("\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast")
    assert pglast.parse_sql(sql)


@pytest.mark.parametrize("table", ["lais_visitas", "lais_visitas_config"])
def test_rls_select_own_org_and_service_role(flat, table):
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in flat
    assert f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} FOR SELECT TO authenticated ' \
           "USING (org_id = (SELECT public.current_org_id_for('social_wiring')))" in flat
    assert f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} FOR ALL TO service_role USING (true) WITH CHECK (true)' in flat


def test_cpf_is_hash_and_last_three_only(flat):
    assert "cpf_hash text" in flat and "cpf_final text" in flat
    assert not any(c in flat for c in (" cpf text", " cpf varchar", "cpf_numero"))
    assert "cpf_hash ~ '^[0-9a-f]{64}$' AND cpf_final ~ '^[0-9]{3}$'" in flat


def test_guards_and_agendamento_link(flat):
    assert "CONSTRAINT lais_visitas_status_valido CHECK (status IN ('solicitada', 'confirmada', 'remarcada', 'cancelada'))" in flat
    assert "CONSTRAINT lais_visitas_fim_apos_inicio CHECK (fim > inicio)" in flat
    assert "CONSTRAINT lais_visitas_config_objeto CHECK (jsonb_typeof(config) = 'object')" in flat
    assert ("CREATE UNIQUE INDEX IF NOT EXISTS lais_visitas_slot_vivo_uq ON social_wiring.lais_visitas (org_id, inicio) "
            "WHERE status IN ('solicitada', 'confirmada', 'remarcada')") in flat
    assert "agendamento_id uuid REFERENCES social_wiring.atendimento_agendamentos (id) ON DELETE SET NULL" in flat
    assert "org_id uuid PRIMARY KEY" in flat


def test_status_pagina_row_copies_whatsapp_chat(flat):
    assert "'lais_visitas'" in flat and "origem.nome_pagina = 'whatsapp_chat'" in flat
