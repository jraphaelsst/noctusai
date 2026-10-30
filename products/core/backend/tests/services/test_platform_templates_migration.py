"""Static checks for the platform_templates migration (platform_templates)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_sql

BACKEND = Path(__file__).resolve().parents[2]
SQL = migration_sql(BACKEND, "platform_templates")
FLAT = " ".join(SQL.split())


def test_seeded_design_system_equals_platform_tokens():
    m = re.search(r"'design_system', 'org-design-system',.*?'json',\s*'(\{.*?\})',\s*1, 'active'", SQL, re.S)
    assert m, "seed row not found"
    seeded = json.loads(m.group(1).replace("''", "'"))
    tok = json.loads((BACKEND / "app/services/brand/platform_tokens.json").read_text(encoding="utf-8"))
    assert seeded["schema"] == "noctus.brand-tokens/v1"
    assert seeded["light"] == tok["light"] and seeded["dark"] == tok["dark"] and seeded["radius"] == tok["radius"]


def test_invariants_present():
    assert "ENABLE ROW LEVEL SECURITY" in FLAT
    assert "REVOKE ALL ON public.platform_templates FROM PUBLIC, anon, authenticated" in FLAT
    assert "WHERE status = 'active'" in FLAT  # one active per scope
    assert "append-only" in FLAT and "BEFORE UPDATE OR DELETE" in FLAT
    assert "REVOKE EXECUTE ON FUNCTION public.platform_template_activate" in FLAT


def test_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 8
