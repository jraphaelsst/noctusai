"""Structural tests for `114_termos_negocio.sql`.

Parse-based, like `test_migration_113_transcricao_formatacao.py` — the
migration is a FILE, not an applied change, and there is no dev database to
run it against. These pin the DECLARED shape the service's behavior relies
on: the vocabularies match the service constants, the marco⇔parcela CHECK is
NULL-safe, the permuta link is guarded by triggers, the backfill does not use
a data-modifying CTE (its sibling statements could not see each other's rows),
and nothing is dropped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.modules.card_hub import negociacao_estruturada_service as svc

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "114_termos_negocio.sql"
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


def _flatten(text: str) -> str:
    """Comment lines stripped, whitespace runs collapsed, no padding just
    inside parentheses — the DDL wraps long `IN (...)` lists across lines,
    so a substring check must not depend on that layout."""
    code = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return _flatten(code)


@pytest.fixture(scope="module")
def flat_all_termos_migrations() -> str:
    """`flat`, UNIONED with every LATER migration that also `ALTER TABLE
    social_wiring.atendimento_negociacao_termos` — 114 created the table,
    but a service clause added afterwards (e.g. migration 163's
    `itens_integrantes_ausente_confirmado`) legitimately lives in its OWN
    migration file, never a hand-edit of 114 (forward-only, §1). Scoped
    ONLY to `test_every_service_clause_is_a_column` below — every other
    test here still pins 114's OWN declared shape specifically."""
    partes = [MIGRATION.read_text(encoding="utf-8")]
    for caminho in sorted(MIGRATION.parent.glob("*.sql")):
        if caminho == MIGRATION:
            continue
        texto = caminho.read_text(encoding="utf-8")
        if "ALTER TABLE social_wiring.atendimento_negociacao_termos" in texto:
            partes.append(texto)
    return _flatten("\n".join(partes))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DROP COLUMN" not in code


def test_header_records_the_lgpd_categoria(sql: str):
    assert "categoria: dados pessoais comuns" in sql
    assert "never logged" in sql


# ─── 1. termos ─────────────────────────────────────────────────────────────


def test_termos_is_one_row_per_atendimento_with_rls(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.atendimento_negociacao_termos" in flat
    assert "atendimento_id UUID PRIMARY KEY REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE" in flat
    assert "ALTER TABLE social_wiring.atendimento_negociacao_termos ENABLE ROW LEVEL SECURITY" in flat
    assert "USING (org_id = public.current_org_id())" in flat


def test_every_service_clause_is_a_column(flat_all_termos_migrations: str):
    for campo in svc.TERMOS_CAMPOS:
        assert re.search(rf"\b{campo}\b", flat_all_termos_migrations), (
            f"{campo} missing from 114 and every later migration that alters "
            "atendimento_negociacao_termos"
        )


@pytest.mark.parametrize(
    "valores",
    [svc.POSSE_MARCOS, svc.ONUS_QUITACOES, svc.CORRETAGEM_CONTRATANTES],
)
def test_vocabulary_checks_match_the_service(flat: str, valores):
    lista = ", ".join(f"'{v}'" for v in valores)
    assert f"IN ({lista})" in flat


def test_marco_parcela_check_is_null_safe(flat: str):
    for prefixo in ("posse", "permuta_posse"):
        assert (
            f"CHECK (({prefixo}_marco IS NOT DISTINCT FROM 'parcela') "
            f"= ({prefixo}_marco_parcela_id IS NOT NULL))"
        ) in flat


def test_marco_parcela_fk_is_not_set_null(code: str):
    """SET NULL would violate the marco CHECK on a parcela delete (a 500);
    the service's named 409 needs NO ACTION underneath."""
    bloco = code.split("CREATE TABLE IF NOT EXISTS social_wiring.atendimento_negociacao_termos")[1]
    bloco = bloco.split(");", 1)[0]
    for linha in re.findall(r"marco_parcela_id UUID\s+REFERENCES[^,]+,", bloco):
        assert "ON DELETE" not in linha


# ─── 2. parcelas ───────────────────────────────────────────────────────────


def test_parcela_tipo_check_gains_permuta_idempotently(flat: str):
    drop = "DROP CONSTRAINT IF EXISTS atendimento_negociacao_parcelas_tipo_check"
    add = "ADD CONSTRAINT atendimento_negociacao_parcelas_tipo_check"
    assert drop in flat and add in flat
    assert flat.index(drop) < flat.index(add)
    lista = ", ".join(f"'{t}'" for t in svc.TIPOS_PARCELA)
    assert f"CHECK (tipo IN ({lista}))" in flat


def test_dispara_corretagem_is_not_null_default_false(flat: str):
    assert "ADD COLUMN IF NOT EXISTS dispara_corretagem BOOLEAN NOT NULL DEFAULT false" in flat


# ─── 3. permuta link ───────────────────────────────────────────────────────


def test_link_table_is_unique_per_pair_and_rls_enabled(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.atendimento_parcela_permuta_ativos" in flat
    assert "UNIQUE (parcela_id, permuta_ativo_id)" in flat
    assert "ALTER TABLE social_wiring.atendimento_parcela_permuta_ativos ENABLE ROW LEVEL SECURITY" in flat


def test_link_and_tipo_are_trigger_guarded(flat: str):
    assert "BEFORE INSERT OR UPDATE ON social_wiring.atendimento_parcela_permuta_ativos" in flat
    assert "BEFORE UPDATE OF tipo ON social_wiring.atendimento_negociacao_parcelas" in flat
    assert "v_natureza IS DISTINCT FROM 'permuta_imovel'" in flat


def test_backfill_is_a_loop_not_a_data_modifying_cte(code: str, flat: str):
    assert "DO $$" in code
    assert "FOR r IN" in flat
    assert not re.search(r"WITH\s+\w+\s+AS\s*\(\s*INSERT", code, re.IGNORECASE)
    # Only payment currency is migrated, only within the same org, idempotently.
    assert "pa.natureza = 'permuta_imovel'" in flat
    assert "pa.org_id = n.org_id" in flat
    assert "AND NOT EXISTS" in flat


def test_legacy_columns_are_kept_and_marked(flat: str):
    for coluna in ("posse_data", "posse_condicoes", "permuta_ativo_id"):
        assert f"COMMENT ON COLUMN social_wiring.atendimento_negociacao.{coluna} IS 'LEGACY" in flat


# ─── 4. intermediários ─────────────────────────────────────────────────────


def test_intermediarios_gain_every_qualification_column(flat: str):
    for campo in (
        "favorecido_id", "pessoa_tipo", "documento", "email",
        *svc.ENDERECO_CAMPOS, "representante_nome", "representante_cpf",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {campo} " in flat, campo


def test_documento_shape_is_tied_to_pessoa_tipo(flat: str):
    assert "(pessoa_tipo = 'pf' AND documento ~ '^[0-9]{11}$')" in flat
    assert "(pessoa_tipo = 'pj' AND documento ~ '^[0-9A-Z]{12}[0-9]{2}$')" in flat
    assert "representante_cpf ~ '^[0-9]{11}$'" in flat


def test_favorecido_fk_sets_null(flat: str):
    assert (
        "FOREIGN KEY (favorecido_id) REFERENCES social_wiring.atendimento_favorecidos (id) ON DELETE SET NULL"
    ) in flat


# ─── 5. contratos ──────────────────────────────────────────────────────────


def test_contract_gains_signature_date_and_positive_prazo(flat: str):
    assert "ADD COLUMN IF NOT EXISTS assinatura_data DATE" in flat
    assert "ADD COLUMN IF NOT EXISTS prazo_pendencias_dias INTEGER" in flat
    assert "CHECK (prazo_pendencias_dias IS NULL OR prazo_pendencias_dias > 0)" in flat
