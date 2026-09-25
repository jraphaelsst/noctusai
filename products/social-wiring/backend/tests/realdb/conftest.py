"""Fixtures for real-DB integration tests against a live Supabase instance
(social_wiring schema).

Uses the service-role key (bypasses RLS). `sw_db` targets the
`social_wiring` schema; `core_db` targets `public` for org management.

Tests are opt-in only (`NOCTUS_REALDB_TESTS=1`) and refuse to run against
the production project even with the opt-in set — see
`noctusai_lib.testing.get_realdb_credentials` for why. social-wiring runs
against the SAME prod Supabase project dev shares (no separate dev
project), so this suite is a no-op skip in every environment that has not
pointed `SUPABASE_URL` at a disposable branch — same posture `erp-
imobiliario`/`core`/`adconnect`'s own `tests/realdb/` suites already take.
"""
from __future__ import annotations

import uuid

import pytest
from supabase import create_client
from supabase.lib.client_options import ClientOptions

from noctusai_lib.testing import get_realdb_credentials

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="session")
def core_db():
    """Service-role client for the public schema (org management)."""
    url, key = get_realdb_credentials()
    return create_client(url, key)


@pytest.fixture(scope="session")
def sw_db():
    """Service-role client for the social_wiring schema."""
    url, key = get_realdb_credentials()
    return create_client(url, key, options=ClientOptions(schema="social_wiring"))


@pytest.fixture(scope="session")
def test_org(core_db):
    """Create a test organization, yield it, then delete on teardown."""
    slug = f"test-realdb-sw-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert(
        {
            "nome": f"RealDB SW Test {slug}",
            "slug": slug,
            "plano": "free",
            "category": "test",
        }
    ).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()
