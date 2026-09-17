"""Structural tests for `134_contrato_assinatura.sql`.

Parse-based, like the sibling `atendimento_contrato_versoes` migration
tests before it (112/120) — the migration is a FILE, not an applied
change, and there is no dev database to run it against. These pin: the
new table's two partial-unique indexes, the two-policy RLS shape
(mirroring `atendimento_contratos` verbatim — 106), the widened `origem`
CHECK, the widened per-origem CHECKs on `contexto_sha256` and the docx
sibling (so an 'assinado' row can actually insert), and the trailing
schema-reload NOTIFY.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "134_contrato_assinatura.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    upper = code.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE"):
        assert forbidden not in upper


def test_creates_the_assinaturas_table(flat: str):
    assert (
        "CREATE TABLE IF NOT EXISTS social_wiring.atendimento_contrato_assinaturas"
        in flat
    )
    for coluna in (
        "contrato_id uuid not null references social_wiring.atendimento_contratos(id)",
        "versao_id uuid not null references social_wiring.atendimento_contrato_versoes(id)",
        "external_id text not null",
        "link_assinatura text not null",
        "versao_assinada_id uuid references social_wiring.atendimento_contrato_versoes(id)",
    ):
        assert coluna in flat


def test_status_check_matches_the_protocol_vocabulary(flat: str):
    assert (
        "check (status in ('pendente','parcial','concluido','cancelado','expirado'))"
        in flat
    )


def test_one_live_envelope_per_contract(flat: str):
    assert (
        "create unique index if not exists atendimento_contrato_assinaturas_viva"
        in flat
    )
    assert "where status in ('pendente','parcial')" in flat


def test_one_row_per_provider_document(flat: str):
    assert (
        "create unique index if not exists atendimento_contrato_assinaturas_externo"
        in flat
    )
    assert (
        "on social_wiring.atendimento_contrato_assinaturas (provedor, external_id)"
        in flat
    )


def test_rls_mirrors_atendimento_contratos_verbatim(flat: str):
    assert (
        "ALTER TABLE social_wiring.atendimento_contrato_assinaturas ENABLE ROW LEVEL SECURITY"
        in flat
    )
    assert (
        'CREATE POLICY "atendimento_contrato_assinaturas_select_own_org" '
        "ON social_wiring.atendimento_contrato_assinaturas FOR SELECT TO authenticated "
        "USING (org_id = public.current_org_id());"
    ) in flat
    assert (
        'CREATE POLICY "atendimento_contrato_assinaturas_service_role" '
        "ON social_wiring.atendimento_contrato_assinaturas FOR ALL TO service_role "
        "USING (true) WITH CHECK (true);"
    ) in flat
    # No third policy — no INSERT/UPDATE-for-authenticated shape invented.
    assert flat.count('CREATE POLICY "atendimento_contrato_assinaturas') == 2


def test_widens_origem_to_admit_assinado(flat: str):
    assert (
        "DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_origem_check"
        in flat
    )
    assert (
        "ADD CONSTRAINT atendimento_contrato_versoes_origem_check "
        "CHECK (origem IN ('upload', 'gerado', 'assinado'))"
    ) in flat


def test_widens_the_contexto_per_origem_check_so_assinado_can_insert(flat: str):
    """112's CHECK was exhaustive over ('gerado','upload') — an 'assinado'
    row satisfies neither branch and would be silently rejected without
    this widening."""
    assert (
        "DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_contexto_por_origem"
        in flat
    )
    assert "(origem = 'assinado' AND contexto_sha256 IS NULL)" in flat


def test_widens_the_docx_per_origem_check_so_assinado_can_insert(flat: str):
    """120's CHECK was likewise exhaustive over ('gerado','upload')."""
    assert (
        "DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_docx_por_origem"
        in flat
    )
    assert (
        "(origem = 'assinado' AND docx_storage_path IS NULL "
        "AND docx_tamanho_bytes IS NULL)"
    ) in flat
    assert "NOT VALID" in flat


def test_ends_with_a_schema_reload(flat: str):
    assert flat.rstrip().endswith("NOTIFY pgrst, 'reload schema';")
