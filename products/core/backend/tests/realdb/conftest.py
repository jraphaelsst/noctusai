"""
Fixtures for real-DB integration tests against a live Supabase instance.

These tests use the service-role key (bypasses RLS) for speed and simplicity.
All test data is cleaned up after each test via the `cleanup` fixture.

Tests are opt-in only (`NOCTUS_REALDB_TESTS=1`) and refuse to run against the
production project even with the opt-in set — see
`noctusai_lib.testing.get_realdb_credentials` for why (2026-09-23 prod-leak
incident: mere credential presence used to be enough to run this suite).
"""
from __future__ import annotations

import uuid
import warnings

import pytest
from supabase import create_client

from noctusai_lib.testing import get_realdb_credentials

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="session")
def admin_db():
    """Service-role client for the public schema (core tables)."""
    url, key = get_realdb_credentials()
    return create_client(url, key)


_ORG_NO_ACTION_DEPENDENTS = (
    # Tables that reference organizations.id with ON DELETE NO ACTION.
    # Listed in safe-deletion order (children of dependents first when
    # such ordering matters). Must match the FK map in 001_noctusai_core.sql.
    #
    # `audit_logs` is deliberately NOT in this tuple — a bare service-role
    # DELETE against it is refused unconditionally by
    # `guard_audit_logs_append_only` (core migration 053) outside its one
    # sanctioned erasure door. It is cleared separately below via
    # `public.erase_test_org_audit_logs` (migration 054).
    "ai_feedback",
    "api_keys",
    "invitations",
    "product_usage",
    "roles",
    "subscriptions",
)


@pytest.fixture(scope="session")
def test_org(admin_db):
    """Create a test organization, yield it, then delete on teardown.

    Teardown clears `audit_logs` first (via the sanctioned erasure RPC,
    below), then every other NO-ACTION FK dependent (roles, subscriptions,
    …) so the final DELETE on organizations doesn't trip 23503. CASCADE
    dependents (licenses, noctus_users, notifications, org_settings,
    webhook_endpoints) clear themselves.

    NOTE — `audit_logs` is append-only BY DESIGN: core migration 053
    (`guard_audit_logs_append_only` trigger, `products/core/backend/
    migrations/053_audit_trail_expansion.sql`) refuses any DELETE against
    it outside `public.purge_expired_audit_logs()` (400-day retention) or
    `public.erase_test_org_audit_logs()` (migration 054) — the second
    sanctioned door, opened specifically for this fixture: it erases an
    org's audit_logs rows ONLY when `category = 'test' AND slug LIKE
    'test-realdb-%'`, exactly what this fixture stamps. A bare
    `DELETE FROM audit_logs` (the shape every other table in
    `_ORG_NO_ACTION_DEPENDENTS` uses) is refused by the trigger — that is
    why this table is handled separately via the RPC, not the loop below.
    """
    slug = f"test-realdb-{uuid.uuid4().hex[:8]}"
    org = admin_db.table("organizations").insert({
        "nome": f"RealDB Test {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    try:
        admin_db.rpc("erase_test_org_audit_logs", {"p_org_id": org["id"]}).execute()
    except Exception as exc:
        # Loud, never silent. Expected failure modes: migration 054 not
        # yet applied to this database, or (should never happen given the
        # slug this fixture stamps) the org doesn't match the RPC's own
        # `category = 'test' AND slug LIKE 'test-realdb-%'` guard. Either
        # way audit_logs rows for this org are left behind, and the final
        # organizations DELETE below will then trip 23503.
        warnings.warn(
            f"test_org teardown: erase_test_org_audit_logs(p_org_id="
            f"{org['id']!r}) failed ({exc!r}) — org {org['id']!r} "
            f"({org['slug']!r})'s audit_logs rows may be left behind.",
            stacklevel=2,
        )
    for tbl in _ORG_NO_ACTION_DEPENDENTS:
        try:
            admin_db.table(tbl).delete().eq("org_id", org["id"]).execute()
        except Exception as exc:
            # Loud, never silent — a genuine teardown problem (stale
            # schema, missing table, permission drift) worth attention.
            warnings.warn(
                f"test_org teardown: DELETE FROM {tbl} WHERE org_id="
                f"{org['id']!r} failed ({exc!r}) — org {org['id']!r} "
                f"({org['slug']!r}) may be left behind.",
                stacklevel=2,
            )
    try:
        admin_db.table("organizations").delete().eq("id", org["id"]).execute()
    except Exception as exc:
        warnings.warn(
            f"test_org teardown: DELETE FROM organizations WHERE id="
            f"{org['id']!r} failed ({exc!r}) — org {org['id']!r} "
            f"({org['slug']!r}) was NOT deleted. Expected when "
            "erase_test_org_audit_logs above also failed (audit_logs "
            "rows still block the FK); point real-DB runs at a disposable "
            "Supabase branch, never prod.",
            stacklevel=2,
        )


@pytest.fixture
def cleanup(admin_db):
    """Collects (table, id) tuples and deletes them in reverse order after the test."""
    records: list[tuple[str, str]] = []
    yield records
    for table, rid in reversed(records):
        try:
            admin_db.table(table).delete().eq("id", rid).execute()
        except Exception as exc:
            # Loud, never silent — same discipline as test_org's teardown
            # above: a swallowed cleanup failure here is exactly how the
            # 2026-09-23 prod-leak incident went unnoticed.
            warnings.warn(
                f"cleanup fixture: DELETE FROM {table} WHERE id={rid!r} "
                f"failed ({exc!r}) — row may be left behind.",
                stacklevel=2,
            )
