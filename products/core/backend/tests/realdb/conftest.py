"""
Fixtures for real-DB integration tests against a live Supabase instance.

These tests use the service-role key (bypasses RLS) for speed and simplicity.
All test data is cleaned up after each test via the `cleanup` fixture.

Tests skip automatically when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are not set.
"""
from __future__ import annotations

import os
import uuid

import pytest
from supabase import create_client

pytestmark = pytest.mark.realdb


def _get_credentials():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        pytest.skip("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping real-DB tests")
    return url, key


@pytest.fixture(scope="session")
def admin_db():
    """Service-role client for the public schema (core tables)."""
    url, key = _get_credentials()
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
        except Exception:
            # Stale schema or missing table — keep going so the org delete
            # still runs against everything that does exist.
            pass
    admin_db.table("organizations").delete().eq("id", org["id"]).execute()


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
