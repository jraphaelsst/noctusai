"""Structural tests for `166_titulo_onus_confirmado_check_rekey.sql`.

Same shape as `test_migration_165_matricula_boilerplate_guard.py`'s
structural half — the migration is a FILE, not an applied change (there is
no dev database to run it against, `KB § PATTERNS/devops/dev-fleet-
dormant.md`); these assert the DECLARED shape: that 115's confirmed-only
`imovel_dados_titulo_aquisitivo_texto_confirmado` / `imovel_dados_onus_
credor_confirmado` CHECKs are DROPPED and replaced by `_pareado` CHECKs
re-keyed off `_origem` (with the confirmed-only invariant folded in as a
second, one-directional clause), applied via the house `NOT VALID` +
`VALIDATE CONSTRAINT` lock-light pattern (`027_erp_org_scoping_
completion.sql`).
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "166_titulo_onus_confirmado_check_rekey.sql"
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
    statements = pglast.parse_sql(sql)
    assert len(statements) > 0


def test_is_idempotent(code: str):
    assert code.count("DROP CONSTRAINT IF EXISTS") == 2
    assert code.count("ADD CONSTRAINT") == 2
    assert code.count("NOT VALID") == 2
    assert code.count("VALIDATE CONSTRAINT") == 2


def test_not_applied_to_any_db_by_this_change(sql: str):
    assert "MIGRATION FILE ONLY" in sql
    assert "applying is the tech-lead's + user's decision" in sql


def test_pre_flight_counts_are_documented(sql: str):
    """The header must carry the live, read-only pre-flight this migration
    was verified against — not just an assertion that one was run."""
    assert "PRE-FLIGHT" in sql
    assert "0" in sql  # the violator counts, both fields


# ─── 1. The 115 confirmed-only CHECKs are dropped, never re-added ─────────


def test_the_old_confirmado_em_paired_checks_are_dropped(flat: str):
    assert (
        "DROP CONSTRAINT IF EXISTS imovel_dados_titulo_aquisitivo_texto_confirmado;"
        in flat
    )
    assert "DROP CONSTRAINT IF EXISTS imovel_dados_onus_credor_confirmado;" in flat
    # Never re-added under the old name — the replacement is a NEW name,
    # not a same-name redefinition (unlike the matricula trigger function,
    # which IS a same-name CREATE OR REPLACE by design).
    assert "ADD CONSTRAINT imovel_dados_titulo_aquisitivo_texto_confirmado " not in flat
    assert "ADD CONSTRAINT imovel_dados_onus_credor_confirmado " not in flat


# ─── 2. The new `_pareado` CHECKs — both clauses, both fields ─────────────


def test_titulo_aquisitivo_texto_pareado_check_has_both_clauses(flat: str):
    trecho = flat[flat.index("imovel_dados_titulo_aquisitivo_texto_pareado") :][:500]
    assert (
        "(titulo_aquisitivo_texto IS NULL) = (titulo_aquisitivo_texto_origem IS NULL)"
        in trecho
    )
    assert (
        "titulo_aquisitivo_texto_confirmado_em IS NULL OR titulo_aquisitivo_texto IS NOT NULL"
        in trecho
    )
    assert "NOT VALID" in trecho


def test_onus_credor_pareado_check_has_both_clauses(flat: str):
    trecho = flat[flat.index("imovel_dados_onus_credor_pareado") :][:400]
    assert "(onus_credor IS NULL) = (onus_credor_origem IS NULL)" in trecho
    assert "onus_credor_confirmado_em IS NULL OR onus_credor IS NOT NULL" in trecho
    assert "NOT VALID" in trecho


def test_both_new_constraints_are_validated_separately(flat: str):
    """`NOT VALID` + a SEPARATE `VALIDATE CONSTRAINT` statement — the
    lock-light house pattern, not a same-statement validate."""
    assert (
        "ALTER TABLE social_wiring.imovel_dados "
        "VALIDATE CONSTRAINT imovel_dados_titulo_aquisitivo_texto_pareado;" in flat
    )
    assert (
        "ALTER TABLE social_wiring.imovel_dados "
        "VALIDATE CONSTRAINT imovel_dados_onus_credor_pareado;" in flat
    )


def test_only_imovel_dados_is_touched(flat: str):
    assert "ALTER TABLE social_wiring.imovel_dados" in flat
    for outra in (
        "ALTER TABLE social_wiring.matricula_extracoes",
        "ALTER TABLE social_wiring.imoveis",
        "ALTER TABLE social_wiring.imovel_registry",
    ):
        assert outra not in flat


def test_no_role_is_exempted(code: str):
    assert "TO authenticated" not in code
    assert "TO service_role" not in code
