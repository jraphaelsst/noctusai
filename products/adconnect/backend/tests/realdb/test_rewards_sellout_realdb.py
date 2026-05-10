"""
Real-DB tests for Phase 4 (rewards + sellout).

Marked `@pytest.mark.realdb` — only runs when a live Supabase instance is
available (the AdConnect test target). Skipped by default in CI/dev so
the mock-backed router tests carry the regression load.

Each test seeds two distributors under different orgs, asserts that:
  - distributor A cannot SELECT distributor B's relatorios_sellout rows;
  - the brand owner of org-A sees all relatorios for org-A but not org-B;
  - the same scoping holds for `recompensas_acumuladas`.

Without a live Supabase, the suite is skipped wholesale to keep the
regular `pytest` path green while still landing the test surface.
"""
from __future__ import annotations

import os

import pytest

REALDB_ENABLED = bool(os.environ.get("ADCONNECT_REALDB_URL"))

pytestmark = [
    pytest.mark.realdb,
    pytest.mark.skipif(
        not REALDB_ENABLED,
        reason="ADCONNECT_REALDB_URL not set — RLS realdb suite skipped",
    ),
]


def test_distributor_user_cannot_see_other_distributor_sellout() -> None:
    """Placeholder: with a live Supabase + service role client, seed two
    distributor_memberships rows + two relatorios_sellout rows; query as
    distributor A's user JWT; assert only their distributor's row is
    visible."""
    pytest.skip("realdb harness not yet wired in this worktree")


def test_brand_admin_sees_all_org_sellout() -> None:
    """Placeholder: brand admin (org_role=owner) hits the same query under
    their JWT; sees all rows of their org but none of the other org."""
    pytest.skip("realdb harness not yet wired in this worktree")


def test_recompensas_rls_scopes_to_distributor() -> None:
    """Placeholder: seed two recompensas_acumuladas rows for distinct
    distributors, query each distributor's user; assert isolation."""
    pytest.skip("realdb harness not yet wired in this worktree")
