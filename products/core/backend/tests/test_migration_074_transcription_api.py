"""Static checks for core's transcription_api migration (platform transcription API: tables, quota RPC, bucket, kill switch).

No live database is available to these tests: the RPC body is asserted structurally and the file
is parsed with pglast; behaviour of the RPC is NOT executed here."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
# By name, never by number: a renumber at integrate must not break this test.
SQL = migration_sql(ROOT / "products/core/backend/migrations", "transcription_api")
FLAT = " ".join(SQL.split())
# The RPC is redefined by the no-quotas migration (owner 2026-11-14): assert the CURRENT definition.
SQL_RPC = migration_sql(ROOT / "products/core/backend/migrations", "transcription_api_no_quotas")
RPC = SQL_RPC[SQL_RPC.index("CREATE OR REPLACE FUNCTION public.reservar_transcricao_api"):]


def test_tables_created_idempotently_with_rls_and_service_role_only():
    for t in ("api_tokens", "api_token_audit", "jobs", "transcricoes_api"):
        assert f"CREATE TABLE IF NOT EXISTS public.{t}" in FLAT
        assert f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY" in FLAT
        assert re.search(rf'ON public\.{t}\s+FOR ALL TO service_role', SQL)
    assert "TO authenticated" not in SQL.replace("FROM PUBLIC, anon, authenticated", "")


def test_transcricoes_api_checks_and_indexes():
    assert "CHECK (caller_kind IN ('token', 'user'))" in FLAT
    assert "CHECK (status IN ('na_fila', 'processando', 'concluida', 'falhou', 'cancelada'))" in FLAT
    assert "minutos_reembolsados BOOLEAN NOT NULL DEFAULT false" in FLAT
    for cols in ("(caller_kind, caller_id, criado_em)", "(org_id, criado_em)", "(status, criado_em)"):
        assert f"ON public.transcricoes_api {cols}" in FLAT


def test_rpc_is_secdef_pinned_and_locked_down():
    assert "SECURITY DEFINER" in RPC
    assert "SET search_path = public, pg_temp" in RPC
    assert "REVOKE EXECUTE ON FUNCTION public.reservar_transcricao_api(TEXT, UUID, UUID, NUMERIC) FROM PUBLIC, anon, authenticated" in " ".join(RPC.split())
    assert "GRANT EXECUTE ON FUNCTION public.reservar_transcricao_api(TEXT, UUID, UUID, NUMERIC) TO service_role" in " ".join(RPC.split())


def test_rpc_has_only_load_guards_and_no_usage_quotas():
    for name, val in (("c_caller_em_andamento", "3"), ("c_fila_max", "20")):
        assert len(re.findall(rf"\b{name}\b\s+CONSTANT", RPC)) == 1
        assert re.search(rf"{name}\s+CONSTANT \w+\s+:=\s+{val};", RPC)
    # Owner decision 2026-11-14: no daily/hourly usage quota of any kind.
    for gone in ("c_caller_envios_hora", "c_caller_min_dia", "c_org_min_dia", "c_global_min_dia",
                 "limite_envios_hora", "cota_diaria_chamador", "cota_diaria_org", "capacidade_diaria",
                 "interval '24 hours'", "interval '1 hour'", "sum(duracao_s)"):
        assert gone not in RPC


def test_rpc_locks_per_caller_and_returns_every_codigo():
    assert "pg_advisory_xact_lock" in RPC and "transcricao_api:caller:" in RPC
    for codigo in ("limite_em_andamento", "fila_cheia"):
        assert f"'{codigo}'" in RPC
    assert "'na_fila'" in RPC and "retry_after_s" in RPC
    assert "INSERT INTO public.transcricoes_api" in RPC


def test_rpc_signature_unchanged_so_the_previous_image_still_works():
    assert "p_caller_kind TEXT" in RPC and "p_duracao_s   NUMERIC" in RPC
    assert "RETURNS jsonb" in RPC and "'ok', true, 'id', v_id" in RPC


def test_bucket_is_private_and_kill_switch_ships_off():
    assert "VALUES ('core-transcricoes', 'core-transcricoes', false)" in FLAT
    assert "public = false" in FLAT and "public = true" not in FLAT
    assert "('transcricao_api_habilitada', 'false'" in FLAT
    assert "ON CONFLICT (key) DO NOTHING" in FLAT


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 30
    assert len(pglast.parse_sql(SQL_RPC)) == 3
