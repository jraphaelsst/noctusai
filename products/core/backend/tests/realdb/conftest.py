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
    "ai_feedback",
    "api_keys",
    "audit_logs",
    "invitations",
    "product_usage",
    "roles",
    "subscriptions",
)


@pytest.fixture(scope="session")
def test_org(admin_db):
    """Create a test organization, yield it, then delete on teardown.

    Teardown clears every NO-ACTION FK dependent first (audit_logs, roles,
    subscriptions, …) so the final DELETE on organizations doesn't trip
    23503. CASCADE dependents (licenses, noctus_users, notifications,
    org_settings, webhook_endpoints) clear themselves.

    NOTE — `audit_logs` is append-only BY DESIGN: core migration 053
    (`guard_audit_logs_append_only` trigger, `products/core/backend/
    migrations/053_audit_trail_expansion.sql`) refuses any DELETE against
    it. A real-DB run targeting a database with 053 applied therefore
    CANNOT clear this org's audit_logs rows, and consequently cannot
    delete the org itself (FK 23503 on the final DELETE below). That is
    expected, not a teardown bug — real-DB runs must point at a
    disposable Supabase branch (never prod), where a leftover test org
    is thrown away with the whole branch.
    """
    slug = f"test-realdb-{uuid.uuid4().hex[:8]}"
    org = admin_db.table("organizations").insert({
        "nome": f"RealDB Test {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    for tbl in _ORG_NO_ACTION_DEPENDENTS:
        try:
            admin_db.table(tbl).delete().eq("org_id", org["id"]).execute()
        except Exception as exc:
            # Loud, never silent: expected for `audit_logs` (append-only,
            # see docstring above); for any other table this is a genuine
            # teardown problem (stale schema, missing table, permission
            # drift) worth someone's attention.
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
            f"({org['slug']!r}) was NOT deleted. Expected when audit_logs "
            "still holds rows for it (append-only, migration 053); point "
            "real-DB runs at a disposable Supabase branch, never prod.",
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
        except Exception:
            pass
