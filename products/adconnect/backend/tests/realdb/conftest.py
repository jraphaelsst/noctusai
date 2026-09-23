"""
Fixtures for real-DB integration tests against a live Supabase instance
(adconnect schema).

Uses the service-role key (bypasses RLS) to seed fixtures, then issues
follow-up queries with anon-key + JWT to verify RLS row visibility.

Tests are opt-in only (`NOCTUS_REALDB_TESTS=1`) and refuse to run against
the production project even with the opt-in set — see
`noctusai_lib.testing.get_realdb_credentials` for why. adconnect is
currently asleep (see `deploy/fleet/active-scope.txt`); this suite stays
wired to the seed helper so it is the only credential path even while
dormant.
"""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.testing import get_realdb_credentials

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="session")
def core_db():
    """Service-role client for the public schema (org/user management)."""
    from supabase import create_client

    url, key = get_realdb_credentials()
    return create_client(url, key)


@pytest.fixture(scope="session")
def adconnect_db():
    """Service-role client for the adconnect schema."""
    from supabase import create_client
    from supabase.lib.client_options import ClientOptions

    url, key = get_realdb_credentials()
    return create_client(url, key, options=ClientOptions(schema="adconnect"))


@pytest.fixture()
def test_org(core_db):
    """Create a test organization, yield it, then delete on teardown."""
    slug = f"adconn-realdb-{uuid.uuid4().hex[:8]}"
    org = core_db.table("organizations").insert(
        {"nome": f"RealDB AdConnect Test {slug}", "slug": slug, "plano": "free"}
    ).execute().data[0]
    yield org
    core_db.table("organizations").delete().eq("id", org["id"]).execute()
