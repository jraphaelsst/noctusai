"""Structural (parse-based) tests for `122_llm_usage.sql`.

Instantiated from `noctusai_lib/integrations/llm/migrations/
llm_usage.sql.template` — the template that resolves
`NOC-REMEDIATE[llm-usage-image-columns]` (projects/edicao-fotos/
PROJECT.md §C2) by carrying the four image-edit columns the two
pre-existing hand-copies (erp-imobiliario 020, therapy-platform 006)
lack.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Provider path this test reads (gate_sweep runs it when it changes; contract_of.py).
CONTRACT_OF = ("products/core/backend/app/routers/admin_llm_usage.py",)

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "122_llm_usage.sql"
TEMPLATE = (
    Path(__file__).resolve().parents[4]
    / "seed"
    / "lib"
    / "backend"
    / "noctusai_lib"
    / "integrations"
    / "llm"
    / "migrations"
    / "llm_usage.sql.template"
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


def test_no_unsubstituted_placeholder_remains(code: str):
    assert "{{SCHEMA_NAME}}" not in code


def test_table_carries_the_image_edit_columns(flat: str):
    assert "CREATE TABLE IF NOT EXISTS social_wiring.llm_usage" in flat
    for col in ("image_input_tokens", "image_output_tokens", "model_version", "batch"):
        assert col in flat, col


def test_narrow_columns_still_present_for_backward_shape_parity(flat: str):
    for col in ("provider", "model", "operation", "prompt_tokens", "completion_tokens",
                "total_tokens", "cost_estimate_usd"):
        assert col in flat, col


def test_rls_scoped_by_org_service_role_writes(flat: str):
    assert "ALTER TABLE social_wiring.llm_usage ENABLE ROW LEVEL SECURITY" in flat
    assert 'CREATE POLICY "llm_usage_select_own_org" ON social_wiring.llm_usage' in flat
    assert "org_id IS NOT NULL AND org_id = public.current_org_id()" in flat
    assert 'CREATE POLICY "service_role_bypass" ON social_wiring.llm_usage' in flat


def test_body_matches_the_seed_template(sql: str):
    if not TEMPLATE.is_file():
        pytest.skip(f"seed template not found at {TEMPLATE}")
    template_body = TEMPLATE.read_text(encoding="utf-8").replace("{{SCHEMA_NAME}}", "social_wiring")
    assert template_body.strip() in sql


def test_never_stores_prompt_or_response_text(sql: str):
    assert "prompt_text" not in sql
    assert "response_text" not in sql


# ─── readers moved to the central ledger (D25) ─────────────────────────
# The hand-kept product→schema maps this file used to assert are gone: the
# core admin report and the budget guard read `public.ai_usage`, where every
# product lands by construction — social-wiring needs no registration.

_REPO = Path(__file__).resolve().parents[4]


def test_admin_llm_usage_router_reads_the_central_ledger():
    text = (_REPO / "products/core/backend/app/routers/admin_llm_usage.py").read_text(encoding="utf-8")
    assert "read_ai_usage_rows" in text
    assert "social_wiring" not in text  # no per-product schema map


def test_llm_budget_reads_the_central_ledger():
    text = (_REPO / "seed/lib/backend/noctusai_lib/integrations/llm/budget.py").read_text(encoding="utf-8")
    assert '_LEDGER_TABLE = "ai_usage"' in text
    assert "social_wiring" not in text
