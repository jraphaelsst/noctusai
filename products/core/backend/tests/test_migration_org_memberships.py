"""Static checks for core org_memberships, the one-user↔many-orgs list (multi-org S1, 2026-10-12).

Pins the contract the later slices build on: expand-only, service-role writes, self-read only,
a home-org mirror that can never lack its membership, and a backfill that fails LOUDLY.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql

ROOT = Path(__file__).resolve().parents[4]
SQL = migration_sql(ROOT / "products/core/backend/migrations", "org_memberships")
FLAT = " ".join(SQL.split())


def test_one_membership_per_user_and_org():
    assert "CONSTRAINT org_memberships_user_org_key UNIQUE (user_id, org_id)" in FLAT


def test_status_vocabulary_and_ended_at_move_together():
    assert "CHECK (status IN ('invited', 'active', 'suspended', 'removed'))" in FLAT
    assert "CHECK ((status = 'removed') = (ended_at IS NOT NULL))" in FLAT


def test_clients_can_only_read_their_own_rows():
    assert "REVOKE ALL ON public.org_memberships FROM PUBLIC, anon, authenticated;" in FLAT
    assert "GRANT SELECT ON public.org_memberships TO authenticated;" in FLAT
    assert "FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));" in FLAT
    # No client write policy at all — memberships are granted server-side only.
    for verb in ("FOR INSERT", "FOR UPDATE", "FOR DELETE", "FOR ALL"):
        assert verb not in FLAT


def test_home_org_write_always_has_its_active_membership():
    assert "AFTER INSERT OR UPDATE OF org_id, org_role ON public.noctus_users" in FLAT
    assert "ON CONFLICT (user_id, org_id) DO UPDATE SET org_role = EXCLUDED.org_role, status = 'active', ended_at = NULL;" in FLAT


def test_mirror_sync_never_ends_a_membership():
    # Ending is the explicit remove-member path (S4), never a home switch side effect.
    body = SQL.split("FUNCTION public.org_memberships_sync_from_home()")[1].split("$$;")[0]
    assert "'removed'" not in body and "DELETE" not in body


def test_security_definer_helper_is_not_client_callable():
    assert "REVOKE EXECUTE ON FUNCTION public.org_memberships_sync_from_home() FROM PUBLIC, anon, authenticated;" in FLAT


def test_backfill_is_verified_loudly():
    assert "RAISE EXCEPTION 'org_memberships backfill: % profile(s) without a home membership'" in FLAT


def test_expand_only_no_existing_object_is_altered_or_dropped():
    assert "ALTER TABLE public.noctus_users" not in FLAT
    assert "DROP TABLE" not in FLAT and "DROP COLUMN" not in FLAT


def test_the_file_parses_as_postgres():
    pglast = pytest.importorskip("pglast")
    assert len(pglast.parse_sql(SQL)) >= 10
