"""
Fixtures for real-DB integration tests against a live Supabase instance (ERP schema).

Uses the service-role key (bypasses RLS) for speed.  The `erp_db` client targets
the ``erp`` schema; `core_db` targets ``public`` for org/user management.

Tests skip automatically when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are not set.
"""
from __future__ import annotations

import os
import uuid

import pytest
from supabase import create_client
from supabase.lib.client_options import ClientOptions

pytestmark = pytest.mark.realdb


def _get_credentials():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        pytest.skip("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping real-DB tests")
    return url, key


@pytest.fixture(scope="session")
def core_db():
    """Service-role client for the public schema (org/user management)."""
    url, key = _get_credentials()
    return create_client(url, key)


@pytest.fixture(scope="session")
def erp_db():
    """Service-role client for the erp schema."""
    url, key = _get_credentials()
    return create_client(url, key, options=ClientOptions(schema="erp"))


@pytest.fixture(scope="session")
def test_org(core_db):
    """Create a test organization, yield it, then delete on teardown."""
    slug = f"test-realdb-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert({
        "nome": f"RealDB ERP Test {slug}",
        "slug": slug,
        "plano": "free",
        "category": "test",
    }).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture(scope="session")
def test_user(core_db, test_org):
    """Create a real auth user assigned to test_org, yield, then delete."""
    email = f"erp-test-{uuid.uuid4().hex[:8]}@realdb.test"
    user_resp = core_db.auth.admin.create_user({
        "email": email,
        "password": f"TestPass!{uuid.uuid4().hex[:8]}",
        "email_confirm": True,
        "user_metadata": {"org_id": test_org["id"]},
    })
    user = user_resp.user
    yield user
    try:
        core_db.auth.admin.delete_user(user.id)
    except Exception:
        pass


@pytest.fixture
def cleanup(erp_db):
    """Collects (table, id) tuples and deletes them in reverse order after the test."""
    records: list[tuple[str, str]] = []
    yield records
    for table, rid in reversed(records):
        try:
            erp_db.table(table).delete().eq("id", rid).execute()
        except Exception:
            pass
