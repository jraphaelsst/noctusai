"""Structural (parse-based) tests for `127_fotos_storage_buckets.sql`.

Pins the two-bucket shape: `edicao-fotos` is org-scoped via the first
storage path segment (mirrors 057_card_hub_documentos.sql); `edicao-
fotos-referencias` is platform-scope (no org predicate), matching the
124 tables it backs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "127_fotos_storage_buckets.sql"


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


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DELETE FROM storage.buckets" not in code


def test_both_buckets_created_private_and_idempotent(flat: str):
    for bucket in ("edicao-fotos", "edicao-fotos-referencias"):
        assert f"VALUES ('{bucket}', '{bucket}', false)" in flat
    assert flat.count("ON CONFLICT (id) DO NOTHING;") >= 2


def test_edicao_fotos_object_rls_scoped_by_first_path_segment(flat: str):
    for verb in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert f'"ef_fotos_storage_{verb.lower()}"' in flat
    assert "(storage.foldername(name))[1] = public.current_org_id()::text" in flat
    assert "bucket_id = 'edicao-fotos'" in flat


def test_referencias_bucket_readable_broadly_writes_service_role_only(flat: str):
    assert '"ef_referencias_storage_select"' in flat
    # Two mentions per policy name (DROP POLICY IF EXISTS + CREATE
    # POLICY) — the CREATE is the second occurrence.
    bloco = flat.split('"ef_referencias_storage_select"')[2].split(";", 1)[0]
    assert "bucket_id = 'edicao-fotos-referencias'" in bloco
    assert "current_org_id" not in bloco
    assert '"ef_referencias_storage_service"' in flat
    assert "FOR ALL TO service_role" in flat.split('"ef_referencias_storage_service"')[2][:300]


def test_service_role_policies_exist_for_both_buckets(flat: str):
    assert '"ef_fotos_storage_service"' in flat
    assert '"ef_referencias_storage_service"' in flat
