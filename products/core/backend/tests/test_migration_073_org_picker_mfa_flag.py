"""Static checks for core 073: the org picker's aal2 requirement behind products.org_picker_requires_mfa
(owner decision 2026-10-09, CONTRACT decision 5 revised)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SQL = (ROOT / "products/core/backend/migrations/073_org_picker_mfa_flag.sql").read_text(encoding="utf-8")
FLAT = " ".join(SQL.split())


def _canon() -> str:
    tpl = ROOT / "seed/lib/backend/noctusai_lib/domain/sql_templates.py"
    spec = importlib.util.spec_from_file_location("_t073_sql_templates", tpl)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return " ".join(mod.org_identity_function_sql("current_org_id_for").split())


def test_column_defaults_to_the_2026_10_08_rule():
    assert "ADD COLUMN IF NOT EXISTS org_picker_requires_mfa boolean NOT NULL DEFAULT true" in FLAT


def test_owner_decision_switches_it_off_fleet_wide():
    assert "UPDATE public.products SET org_picker_requires_mfa = false;" in FLAT


def test_helper_honours_the_flag_and_the_flag_clause_survives_in_the_canon():
    # 073's copy is historical since core 078 (every entry is a choice) re-declared the helper;
    # it is ratified in mcp/noctusai/tests/org_identity_parity_baseline.json. The flag clause
    # must still be part of today's canonical rendering.
    clause = "(NOT p.org_picker_requires_mfa OR v_claims ->> 'aal' = 'aal2')"
    assert clause in FLAT
    assert clause in _canon()


def test_restore_path_is_documented():
    assert "UPDATE public.products SET org_picker_requires_mfa = true;" in SQL


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 5
