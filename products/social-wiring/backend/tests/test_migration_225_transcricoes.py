"""Structural (parse-based) tests for `225_transcricoes.sql` — the shared transcription
layer (transcription-contract.md sections 3 and 5). `tests/support/rpc_fakes.py ::
reservar_transcricao` is the contract fake pinned against the numbers asserted here."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION = MIGRATIONS / "225_transcricoes.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file()
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    return " ".join(code.split())


def test_parses(sql):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_number_is_unique_in_the_directory():
    assert len(list(MIGRATIONS.glob("225_*.sql"))) == 1


def test_forward_only_and_search_path(flat):
    assert "SET search_path = social_wiring, public;" in flat
    assert "DROP TABLE" not in flat and "DROP COLUMN" not in flat


def test_columns_of_the_contract(flat):
    for col in (
        "id UUID PRIMARY KEY", "org_id UUID NOT NULL REFERENCES public.organizations", "user_id UUID NOT NULL",
        "contexto_tipo TEXT NOT NULL", "contexto_ref TEXT NOT NULL", "storage_path TEXT NOT NULL",
        "bytes BIGINT NOT NULL", "duracao_s NUMERIC(8, 2) NOT NULL", "formato TEXT NOT NULL", "status TEXT NOT NULL",
        "texto TEXT", "erro_codigo TEXT", "modelo TEXT", "rtf NUMERIC(8, 3)", "criado_em TIMESTAMPTZ NOT NULL",
        "iniciado_em TIMESTAMPTZ", "concluido_em TIMESTAMPTZ", "audio_apagado_em TIMESTAMPTZ",
        "minutos_reembolsados BOOLEAN NOT NULL DEFAULT false", "hook_aplicado_em TIMESTAMPTZ",
    ):
        assert col in flat, col
    assert "CHECK (status IN ('na_fila', 'processando', 'concluida', 'falhou', 'cancelada'))" in flat
    assert "CHECK (formato IN ('webm', 'ogg', 'mp4', 'mp3', 'wav'))" in flat
    assert "CHECK (NOT minutos_reembolsados OR status IN ('falhou', 'cancelada'))" in flat


def test_indexes(flat):
    assert "(user_id, criado_em DESC)" in flat and "(org_id, criado_em DESC)" in flat and "(status)" in flat


def test_rls_owner_select_and_service_role_writes_only(flat):
    assert "ALTER TABLE social_wiring.transcricoes ENABLE ROW LEVEL SECURITY" in flat
    assert "REVOKE INSERT, UPDATE, DELETE ON social_wiring.transcricoes FROM anon, authenticated" in flat
    assert re.search(r'ON social_wiring\.transcricoes FOR SELECT TO authenticated USING \(user_id = \(SELECT auth\.uid\(\)\)\)', flat)
    # no authenticated write policy
    assert not re.search(r"ON social_wiring\.transcricoes FOR (ALL|INSERT|UPDATE|DELETE) TO authenticated", flat)
    assert "ON social_wiring.transcricoes FOR ALL TO service_role" in flat


def test_rpc_is_locked_down_and_atomic(flat):
    assert "CREATE OR REPLACE FUNCTION social_wiring.reservar_transcricao(" in flat
    assert "SECURITY INVOKER" in flat and "SET search_path = social_wiring, public" in flat
    assert "pg_advisory_xact_lock(hashtextextended('transcricoes:user:' || p_user::text, 0))" in flat
    assert re.search(r"REVOKE EXECUTE ON FUNCTION social_wiring\.reservar_transcricao\([^)]*\) FROM PUBLIC, anon, authenticated", flat)
    assert re.search(r"GRANT EXECUTE ON FUNCTION social_wiring\.reservar_transcricao\([^)]*\) TO service_role", flat)


def test_quota_numbers_are_the_contract(flat):
    assert "v_n >= 2 THEN" in flat  # in flight per user
    assert "v_n >= 10 THEN" in flat  # per hour per user
    assert "v_soma + p_duracao_s > 1800" in flat  # user 30 min / 24 h
    assert "v_soma + p_duracao_s > 7200" in flat  # org 120 min / day
    assert "v_n >= 20 THEN" in flat  # global queue depth
    assert "v_soma + p_duracao_s > 36000" in flat  # global 600 min / day
    for codigo in ("limite_usuario", "cota_diaria_usuario", "cota_diaria_org", "fila_cheia", "capacidade_diaria"):
        assert f"'{codigo}'" in flat
    assert flat.count("'http', 429") == 4 and flat.count("'http', 503") == 2
    assert flat.count("NOT minutos_reembolsados") >= 4  # refunded minutes never count


def test_bucket_is_private(flat):
    assert "VALUES ('sw-transcricoes', 'sw-transcricoes', false) ON CONFLICT (id) DO NOTHING" in flat
    assert "'sw-transcricoes', 'sw-transcricoes', true" not in flat


def test_cerebro_fks_with_set_null(flat):
    for tbl in ("cs_brain_answers", "cs_brain_imports", "cs_extractions"):
        assert f"ARRAY['{tbl}'" in flat
    # built with format(); the two literal halves are adjacent in the file
    assert "FOREIGN KEY (transcricao_id) ' 'REFERENCES social_wiring.transcricoes (id) ON DELETE SET NULL'" in flat


def test_the_224_deferral_marker_is_gone():
    assert "NOC-REMEDIATE[fk-transcricoes]" not in (MIGRATIONS / "224_cs_cerebro.sql").read_text(encoding="utf-8")
    assert "NOC-REMEDIATE" not in MIGRATION.read_text(encoding="utf-8")
