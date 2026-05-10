"""
Fixtures for real-DB integration tests against a live Supabase instance
(adconnect schema).

Uses the service-role key (bypasses RLS) to seed fixtures, then issues
follow-up queries with anon-key + JWT to verify RLS row visibility.

Tests skip automatically when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
are not set — the worktree never has them, so this suite is dormant by
default. CI / staging runs supply the env vars to flip it on.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.realdb


def _get_credentials():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        pytest.skip(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping real-DB tests"
        )
    return url, key


@pytest.fixture(scope="session")
def core_db():
    """Service-role client for the public schema (org/user management)."""
    from supabase import create_client

    url, key = _get_credentials()
    return create_client(url, key)


@pytest.fixture(scope="session")
def adconnect_db():
    """Service-role client for the adconnect schema."""
    from supabase import create_client
    from supabase.lib.client_options import ClientOptions

    url, key = _get_credentials()
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
