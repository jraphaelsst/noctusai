"""
Fixtures for real-DB integration tests against a live Supabase instance
(adconnect schema). Mirrors `products/erp-imobiliario/backend/tests/realdb/conftest.py`.

Tests skip automatically when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY
are not set. Apply migrations 001 + 002 first.
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
def adconnect_db():
    """Service-role client for the adconnect schema."""
    url, key = _get_credentials()
    return create_client(url, key, options=ClientOptions(schema="adconnect"))


@pytest.fixture(scope="session")
def test_brand_org(core_db):
    """Create a brand-org for the test session, yield it, then delete on teardown."""
    slug = f"test-adconnect-{uuid.uuid4().hex[:8]}"
    org = (
        core_db.table("organizations")
        .insert({
            "nome": f"RealDB AdConnect Test {slug}",
            "slug": slug,
            "plano": "free",
            "category": "test",
        })
        .execute()
        .data[0]
    )
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()


@pytest.fixture
def cleanup(adconnect_db):
    """Collects (table, id) tuples and deletes them in reverse order after the test."""
    records: list[tuple[str, str]] = []
    yield records
    for table, rid in reversed(records):
        try:
            adconnect_db.table(table).delete().eq("id", rid).execute()
        except Exception:
            pass
