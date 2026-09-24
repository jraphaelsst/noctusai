"""Structural tests for `167_empresas_crednet_cartao_cnpj.sql`.

Parse-based, like `test_migration_164_cin_documento_tipo.py` and
`test_migration_154_imovel_extracao_proveniencia.py` (whose shapes this
mirrors) — the migration is a FILE, not an applied change (contract §A: "It
is not applied by the slice"). These pin: every table's existence and RLS,
the CNPJ shape check, the group-provenance quintet on `empresas`, the
certidao_consultas/resultados wiring, the `clientes.nome_mae` quintet, the
document-type + retention seeding (idempotent against the partial index),
the `superficie` CHECK widened with `'empresa'`, and the backfill's
"situação is NOT copied" contract (§H4).
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "167_empresas_crednet_cartao_cnpj.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    """SQL with comment lines stripped — header prose must never satisfy a
    check about actual SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    """`code` with whitespace runs collapsed."""
    return " ".join(code.split())


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    upper = code.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE"):
        assert forbidden not in upper
    # The backfill's malformed-CNPJ NOTICE reads existing rows only — no
    # DELETE FROM anywhere in this file.
    assert "DELETE FROM" not in upper


def test_every_new_table_is_idempotent_and_rls_enabled(flat: str):
    for table in (
        "empresas",
        "cliente_empresa_participacoes",
        "empresa_documentos",
        "empresa_documento_acessos",
        "empresa_campo_conflitos",
    ):
        assert f"CREATE TABLE IF NOT EXISTS social_wiring.{table} (" in flat
        assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY;" in flat
        assert f'"{table}_select_own_org" ON social_wiring.{table}' in flat
        assert f'"{table}_service_role" ON social_wiring.{table}' in flat


def test_empresas_cnpj_shape_check(flat: str):
    assert "cnpj TEXT NOT NULL CHECK (cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$')" in flat


def test_empresas_unique_org_cnpj(flat: str):
    assert "CONSTRAINT uq_sw_empresas_org_cnpj UNIQUE (org_id, cnpj)" in flat


def test_empresas_group_provenance_quintet(flat: str):
    for col in (
        "dados_origem", "dados_documento_id", "dados_em",
        "dados_confirmado_por", "dados_confirmado_em",
    ):
        assert f"{col} " in flat


def test_empresas_situacao_cadastral_check(flat: str):
    assert (
        "situacao_cadastral IS NULL OR situacao_cadastral IN "
        "('ativa', 'baixada', 'inapta', 'suspensa', 'nula')" in flat
    )


def test_participacoes_unique_and_origem_check(flat: str):
    assert (
        "CONSTRAINT uq_sw_cliente_empresa_participacoes UNIQUE (cliente_id, empresa_id)"
        in flat
    )
    assert "origem IN ('serasa_crednet', 'manual', 'certidao_consulta')" in flat


def test_empresa_documentos_tipo_check(flat: str):
    assert "tipo_documento TEXT NOT NULL CHECK (tipo_documento IN ('cartao_cnpj'))" in flat


def test_empresa_documento_acessos_widened_with_extract(flat: str):
    assert "acao IN ('view', 'download', 'delete', 'extract')" in flat


def test_empresa_campo_conflitos_one_open_per_field(flat: str):
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_empresa_campo_conflitos_aberto "
        "ON social_wiring.empresa_campo_conflitos (empresa_id, campo) WHERE status = 'pendente';"
        in flat
    )


def test_certidao_consultas_gets_empresa_link_gated_to_cnpj(flat: str):
    assert "ADD COLUMN IF NOT EXISTS empresa_id UUID" in flat
    assert (
        "CHECK (empresa_id IS NULL OR tipo_documento = 'cnpj')" in flat
    )


def test_certidao_resultados_gets_fonte_cliente_documento_id(flat: str):
    assert "ADD COLUMN IF NOT EXISTS fonte_cliente_documento_id UUID" in flat


def test_clientes_nome_mae_quintet(flat: str):
    for col in (
        "nome_mae TEXT", "nome_mae_origem TEXT", "nome_mae_documento_id UUID",
        "nome_mae_em TIMESTAMPTZ", "nome_mae_confirmado_por UUID",
        "nome_mae_confirmado_em TIMESTAMPTZ",
    ):
        assert col in flat


def test_cliente_documentos_crednet_columns(flat: str):
    for col in (
        "extracao_nome_mae TEXT", "extracao_nome_mae_confianca TEXT",
        "extracao_nome_mae_rotulo TEXT", "extracao_crednet JSONB",
    ):
        assert col in flat


def test_seeds_serasa_crednet_document_type(flat: str):
    assert "INSERT INTO social_wiring.cliente_documento_tipos" in flat
    assert "'serasa_crednet', 'financeiro', 1825, false, true" in flat
    assert "ON CONFLICT (tipo_documento) DO UPDATE" in flat


def test_superficie_check_widened_with_empresa(flat: str):
    assert (
        "CHECK (superficie IN ('cliente', 'atendimento', 'imovel', 'empresa'))" in flat
    )


def test_seeds_platform_retention_rows_idempotently(flat: str):
    assert "(NULL, 'cliente', 'serasa_crednet', 1825," in flat
    assert "(NULL, 'empresa', 'cartao_cnpj', 1825," in flat
    assert (
        "ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING"
        in flat
    )


def test_backfill_does_not_copy_situacao(flat: str):
    """Contract §H4: the backfill INSERT into `empresas` names only
    `org_id, cnpj, razao_social, dados_origem` — `situacao_cadastral` /
    `data_situacao_cadastral` are never in that column list, so they stay
    NULL for every backfilled empresa."""
    assert (
        "INSERT INTO social_wiring.empresas (org_id, cnpj, razao_social, dados_origem)"
        in flat
    )
    assert "situacao_cadastral" not in flat.split(
        "INSERT INTO social_wiring.empresas (org_id, cnpj, razao_social, dados_origem)"
    )[1].split("ON CONFLICT (org_id, cnpj) DO NOTHING;")[0]


def test_backfill_is_distinct_on_normalized_cnpj_and_conflict_safe(flat: str):
    assert "DISTINCT ON (c.org_id, norm.cnpj_norm)" in flat
    assert "ON CONFLICT (org_id, cnpj) DO NOTHING;" in flat


def test_backfill_reports_malformed_cnpjs_not_silently(flat: str):
    assert "RAISE NOTICE" in flat
    assert "malformed" in flat.lower() or "malformado" in flat.lower()


def test_backfill_links_consultas_and_participacoes_idempotently(flat: str):
    assert "UPDATE social_wiring.certidao_consultas c SET empresa_id = e.id" in flat
    assert "INSERT INTO social_wiring.cliente_empresa_participacoes" in flat
    assert "ON CONFLICT (cliente_id, empresa_id) DO NOTHING;" in flat


def test_notifies_postgrest(flat: str):
    assert "NOTIFY pgrst, 'reload schema';" in flat
