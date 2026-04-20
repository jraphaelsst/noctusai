"""
Structural (parse-based) tests for `migrations/016_metas_domain.sql`.

No database required — these tests read the SQL file and assert that the
expected tables, columns, enums, RLS policies, and seed rows are declared.
They catch regressions like "someone deleted a column" or "a policy was
renamed" before they hit a real Supabase instance.

For full correctness (actual migration running cleanly against Postgres),
see `tests/realdb/test_metas_realdb.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "016_metas_domain.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"Migration file missing at {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

EXPECTED_TABLES = [
    "equipes",
    "equipe_membros",
    "meta_periodos",
    "metas_empresa",
    "metas_equipe",
    "metas_configuracao",
    "regras_pontuacao",
    "meta_eventos",
    "meta_fechamentos",
]


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_is_created(sql, table):
    pattern = rf"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+erp\.{re.escape(table)}\s*\("
    assert re.search(pattern, sql), f"Missing CREATE TABLE for erp.{table}"


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_has_rls_enabled(sql, table):
    pattern = rf"ALTER TABLE\s+erp\.{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, sql), f"RLS not enabled for erp.{table}"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

NEW_ENUMS = [
    ("modalidade_evento", {"padrao", "compartilhada", "exclusividade"}),
    ("tipo_evento_meta", {"captacao", "visita", "venda", "locacao", "reuniao"}),
    ("papel_equipe", {"lider", "corretor"}),
    ("status_periodo", {"aberto", "em_avaliacao", "fechado"}),
]


@pytest.mark.parametrize("name, values", NEW_ENUMS)
def test_new_enum_is_created_with_expected_values(sql, name, values):
    pattern = rf"CREATE TYPE\s+erp\.{re.escape(name)}\s+AS ENUM\s*\(([^)]+)\)"
    match = re.search(pattern, sql)
    assert match, f"Missing CREATE TYPE for erp.{name}"
    # extract quoted values from the enum body
    declared = set(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert values.issubset(declared), f"erp.{name} missing values: {values - declared}"


@pytest.mark.parametrize("enum_type, value", [
    ("categoria_meta", "vgv"),
    ("tipo_meta", "quinzenal"),
    ("tipo_meta", "trimestral"),
])
def test_enum_value_added(sql, enum_type, value):
    pattern = rf"ALTER TYPE\s+erp\.{re.escape(enum_type)}\s+ADD VALUE\s+IF NOT EXISTS\s+'{re.escape(value)}'"
    assert re.search(pattern, sql), f"Missing ALTER TYPE for erp.{enum_type} -> '{value}'"


# ---------------------------------------------------------------------------
# Column extensions on erp.metas
# ---------------------------------------------------------------------------

METAS_EXTENSIONS = ["periodo_id", "equipe_id", "meta_vgv", "meta_vgv_realizado"]


@pytest.mark.parametrize("column", METAS_EXTENSIONS)
def test_erp_metas_extended_with_column(sql, column):
    pattern = rf"ADD COLUMN IF NOT EXISTS\s+{re.escape(column)}\b"
    assert re.search(pattern, sql), f"Missing ADD COLUMN on erp.metas: {column}"


# ---------------------------------------------------------------------------
# RLS policies — at minimum the admin full-access policy per table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_has_admin_full_policy(sql, table):
    # Admin policies named admin_full_<table>
    pattern = rf"CREATE POLICY\s+admin_full_{re.escape(table)}\s+ON\s+erp\.{re.escape(table)}"
    assert re.search(pattern, sql), f"Missing admin_full policy for erp.{table}"


def test_corretor_own_events_policy(sql):
    # Agents see their own meta_eventos
    assert re.search(
        r"CREATE POLICY\s+corretor_select_meta_eventos\s+ON\s+erp\.meta_eventos",
        sql,
    ), "Missing corretor_select_meta_eventos policy"
    # And the policy body references corretor_id = auth.uid()
    assert "corretor_id = (SELECT auth.uid())" in sql, "Expected corretor_id ownership check in RLS"


def test_leader_sees_team_events_policy(sql):
    # Leader (equipe_membros.papel = 'lider') visibility into team events
    assert "papel = 'lider'" in sql, "Leader check (papel = 'lider') missing from RLS policies"


# ---------------------------------------------------------------------------
# Seed point rules
# ---------------------------------------------------------------------------

EXPECTED_SEED_RULES = [
    ("captacao", "padrao", "1.0"),
    ("captacao", "compartilhada", "0.5"),
    ("captacao", "exclusividade", "2.0"),
    ("visita", "padrao", "1.0"),
    ("venda", "padrao", "50.0"),
    ("venda", "compartilhada", "25.0"),
    ("venda", "exclusividade", "125.0"),
    ("locacao", "padrao", "5.0"),
    ("reuniao", "padrao", "1.0"),
]


@pytest.mark.parametrize("evento, modalidade, pontos", EXPECTED_SEED_RULES)
def test_seed_contains_rule(sql, evento, modalidade, pontos):
    # Row pattern: (NULL, '<evento>', '<modalidade>', <pontos>, '<desc>')
    pattern = rf"\(NULL,\s*'{re.escape(evento)}',\s*'{re.escape(modalidade)}',\s*{re.escape(pontos)}"
    assert re.search(pattern, sql), f"Missing seed rule for ({evento}, {modalidade}) = {pontos}"


def test_seed_block_is_idempotent(sql):
    # Guarded by "IF NOT EXISTS" check so the migration can be re-run safely
    assert re.search(
        r"IF NOT EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+erp\.regras_pontuacao\s+WHERE\s+org_id\s+IS\s+NULL",
        sql,
    ), "Seed block should be wrapped in an idempotency guard"


# ---------------------------------------------------------------------------
# Scoring config sanity
# ---------------------------------------------------------------------------

def test_metas_configuracao_has_vgv_conversion(sql):
    assert re.search(r"vgv_por_ponto\s+NUMERIC\s+NOT NULL\s+DEFAULT\s+10000", sql), \
        "Default VGV→pontos conversion (R$10,000 per point) missing"
    assert re.search(r"metrica_ranking_padrao\s+TEXT\s+NOT NULL\s+DEFAULT\s+'unificado'", sql), \
        "Default ranking metric should be 'unificado'"


def test_event_fracao_constrained(sql):
    # fracao must be in (0, 1] — enforces non-zero and non-negative participation weight
    assert re.search(r"fracao\s+NUMERIC\s+NOT NULL\s+DEFAULT\s+1\.0\s+CHECK\s*\(\s*fracao\s*>\s*0", sql), \
        "fracao column must be CHECK-constrained > 0 and <= 1"


# ---------------------------------------------------------------------------
# Transactional boundary
# ---------------------------------------------------------------------------

def test_migration_wrapped_in_transaction(sql):
    # BEGIN; can appear after the header comment block — search the full body
    assert re.search(r"^BEGIN;\s*$", sql, re.MULTILINE), "Migration should open with BEGIN;"
    assert sql.rstrip().endswith("COMMIT;"), "Migration should end with COMMIT;"
