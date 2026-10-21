"""Structural pins for migration 300 (imóvel -> condomínio FK + casa de rua).
Behaviour of the CHECK + same-org trigger is proven by noctus.dev.
verify_db_guards (probes `imovel_dados.condominio_ou_casa_de_rua` and
`imovel_dados.condominio_id.mesma_org`)."""
from __future__ import annotations

from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[1] / "migrations", "imovel_condominio_fk")
CODE = "\n".join(l for l in SQL.splitlines() if not l.strip().startswith("--"))


def test_fk_and_flag_columns():
    assert "ADD COLUMN IF NOT EXISTS condominio_id UUID REFERENCES social_wiring.condominios (id)" in CODE
    assert "ADD COLUMN IF NOT EXISTS casa_de_rua BOOLEAN NOT NULL DEFAULT false" in CODE
    assert "ON social_wiring.imovel_dados (condominio_id)" in CODE


def test_exclusivity_check_and_same_org_trigger():
    assert "CHECK (NOT (casa_de_rua AND condominio_id IS NOT NULL))" in CODE
    assert "BEFORE INSERT OR UPDATE OF condominio_id, org_id ON social_wiring.imovel_dados" in CODE
    assert "c.org_id = NEW.org_id" in CODE


def test_backfill_only_turns_explicit_false_into_casa_de_rua_before_the_check():
    assert "SET casa_de_rua = true" in CODE and "WHERE em_condominio IS FALSE" in CODE
    assert CODE.index("SET casa_de_rua = true") < CODE.index("ADD CONSTRAINT imovel_dados_condominio_ou_casa_de_rua")
    assert "INSERT INTO social_wiring.condominios" not in CODE  # never auto-created from names


def test_view_resolves_fk_first_and_keeps_column_order():
    assert "COALESCE(d.condominio_id, a.condominio_id) AS condominio_id" in CODE
    assert "ON d.condominio_id IS NULL" in CODE and "COALESCE(d.casa_de_rua, false) = false" in CODE
    sel = CODE[CODE.index("CREATE OR REPLACE VIEW"):]
    assert sel.index("i.org_id") < sel.index("codigo_canonical") < sel.index("AS condominio_id") \
        < sel.index("a.alias_normalizado") < sel.index("AS vinculo")
    assert "security_invoker = true" in CODE


def test_no_write_to_the_vista_mirror():
    for verb in ("UPDATE social_wiring.imoveis", "INSERT INTO social_wiring.imoveis"):
        assert verb not in CODE
