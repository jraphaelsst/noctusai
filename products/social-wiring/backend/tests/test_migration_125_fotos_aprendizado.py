"""Structural (parse-based) tests for `125_fotos_aprendizado.sql`.

Pins the override-trigger's service-role-bypass-aware design: it must
only enforce the platform-admin-override rule when `auth.uid()` is
non-NULL (an `authenticated`-role write), never block a service-role
write — see the migration's own header for the full rationale.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "125_fotos_aprendizado.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


def test_all_four_learning_tables_exist(flat: str):
    for table in (
        "fotos_regras_org",
        "fotos_conjuntos_regras",
        "fotos_guias_efetivos",
        "fotos_propostas_cursor",
    ):
        assert f"CREATE TABLE IF NOT EXISTS social_wiring.{table}" in flat


def test_override_trigger_exists_and_is_wired(flat: str):
    assert "CREATE OR REPLACE FUNCTION social_wiring.fotos_regra_org_override_guard()" in flat
    assert "CREATE OR REPLACE TRIGGER fotos_regra_org_override_guard" in flat
    assert "BEFORE UPDATE ON social_wiring.fotos_regras_org" in flat
    assert "EXECUTE FUNCTION social_wiring.fotos_regra_org_override_guard()" in flat


def test_override_guard_only_fires_for_authenticated_role_not_service_role(flat: str):
    """The trigger body must gate the RAISE on `(SELECT auth.uid()) IS
    NOT NULL` — a service-role write (auth.uid() NULL) must never be
    blocked, since the app layer already gated it before the DB was
    reached."""
    bloco = flat.split("CREATE OR REPLACE FUNCTION social_wiring.fotos_regra_org_override_guard()")[1]
    bloco = bloco.split("$$;", 1)[0]
    assert "(SELECT auth.uid()) IS NOT NULL" in bloco
    assert "RAISE EXCEPTION" in bloco
    assert "NOT public.is_platform_admin()" in bloco


def test_override_guard_stamps_the_audit_flag_and_updated_at(flat: str):
    bloco = flat.split("CREATE OR REPLACE FUNCTION social_wiring.fotos_regra_org_override_guard()")[1]
    bloco = bloco.split("$$;", 1)[0]
    assert "NEW.override_platform_admin := true" in bloco
    assert "NEW.updated_at := now()" in bloco


def test_regras_org_status_vocabulary(flat: str):
    assert "CHECK (status IN ('proposta', 'aprovada', 'rejeitada'))" in flat


def test_regras_org_select_is_admin_tier_only_no_corretor(flat: str):
    """Corretor is absent from the /regras role matrix entirely (contract
    §7) — SELECT must be admin-tier or platform-admin, no creator-based
    branch."""
    bloco = flat.split('CREATE POLICY "fotos_regras_org_select_admins"')[1]
    bloco = bloco.split(";", 1)[0]
    assert "criado_por" not in bloco
    assert "owner" in bloco and "manager" in bloco


def test_no_authenticated_write_policy_anywhere(flat: str):
    """Approve/reject/propose flows are backend service-role writes,
    app-layer role-gated — no INSERT/UPDATE/DELETE policy for
    `authenticated` in this file."""
    for table in (
        "fotos_regras_org",
        "fotos_conjuntos_regras",
        "fotos_guias_efetivos",
        "fotos_propostas_cursor",
    ):
        assert f'CREATE POLICY "service_role_bypass" ON social_wiring.{table}' in flat
    assert "FOR ALL TO authenticated" not in flat
    assert "FOR INSERT TO authenticated" not in flat
    assert "FOR UPDATE TO authenticated" not in flat


def test_conjunto_regras_versioned_and_unique_per_org(flat: str):
    assert "UNIQUE (org_id, versao)" in flat


def test_guias_efetivos_references_estilo_and_conjunto(flat: str):
    assert "guia_estilo_id UUID NOT NULL REFERENCES social_wiring.fotos_guias_estilo (id)" in flat
    assert "conjunto_regras_id UUID REFERENCES social_wiring.fotos_conjuntos_regras (id)" in flat
