"""Pins `.github/workflows/sync-product-scope.yml` — the toggle → git leg (2026-09-22).

Migration 051's trigger dispatches the full catalog state; this workflow turns it
into the two scope files. What must never regress:
  • it regenerates through the SAME generators as `--refresh-build-scope`
    (no second, drifting rendering of the files);
  • the payload is validated as slugs before use (it is external input);
  • no database credential is referenced — the payload IS the state;
  • a woken product gets its tests dispatched (the "product treatment").
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
WF = REPO / ".github" / "workflows" / "sync-product-scope.yml"
MIGRATION = REPO / "products" / "core" / "backend" / "migrations" / "051_product_scope_sync_trigger.sql"


def _text() -> str:
    return WF.read_text(encoding="utf-8")


def test_triggered_only_by_the_catalog_dispatch():
    on = yaml.safe_load(_text()).get(True) or yaml.safe_load(_text()).get("on")
    assert on == {"repository_dispatch": {"types": ["product-scope-changed"]}}


def test_uses_the_shared_generators():
    t = _text()
    assert "refresh_build_scope(_live=" in t and "refresh_active_scope(_active=" in t


def test_payload_is_validated_as_slugs():
    t = _text()
    assert "^[a-z0-9][a-z0-9-]{0,62}$" in t
    assert "LIVE_JSON" in t and "<= set(out[\"ACTIVE_JSON\"])" in t


def test_no_database_credentials_in_ci():
    assert "SUPABASE" not in _text()


def test_woken_products_get_their_tests():
    t = _text()
    assert "gh workflow run test.yml --ref dev" in t
    assert "steps.regen.outputs.woke != ''" in t


def test_trigger_and_workflow_agree_on_the_event_name():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "'product-scope-changed'" in sql
    assert "github_product_scope_dispatch_token" in sql
    assert "FOR EACH STATEMENT" in sql and "UPDATE OF ativo, deploy_scope" in sql
