"""SEC hotfix 2026-10-06 — a user whose ``user_metadata.org_id`` names ANOTHER
org must only ever act on their TRUSTED org (``public.noctus_users``).

The shared ``client`` fixture authenticates a user whose METADATA org is
``test-org-123``; each test points the trusted ``noctus_users`` row at a
DIFFERENT org and asserts every service-role write/read lands there — never in
the metadata org. KB § PATTERNS/backend/no-metadata-authz.md
"""
from __future__ import annotations

import asyncio
from uuid import NAMESPACE_OID, uuid5

import pytest
from fastapi import HTTPException

from noctusai_lib.testing import TEST_USER_ID

METADATA_ORG = "test-org-123"  # what the spoofing user put in user_metadata
TRUSTED_ORG = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def spoofed(client):
    client.mock_supabase.set_table_data(
        "noctus_users",
        [
            {"id": TEST_USER_ID, "org_id": TRUSTED_ORG, "org_role": "owner"},
            # the legacy bridge keys the lookup on the coerced UUID of a
            # non-UUID fixture id (identity for real Supabase UUID ids)
            {"id": str(uuid5(NAMESPACE_OID, TEST_USER_ID)), "org_id": TRUSTED_ORG, "org_role": "owner"},
        ],
    )
    return client


def test_email_marketing_contact_created_in_trusted_org(spoofed):
    resp = spoofed.post(
        "/api/email-marketing/contacts", json={"email": "x@example.com", "nome": "X"}
    )
    assert resp.status_code == 200, resp.text
    rows = spoofed.mock_supabase.table("contacts").inserted_payloads
    assert rows and all(r["org_id"] == TRUSTED_ORG for r in rows), rows
    assert not any(r.get("org_id") == METADATA_ORG for r in rows)


def test_email_marketing_settings_domain_scoped_to_trusted_org(spoofed):
    # Domain creation registers at Resend first (P1b(c)); the adapter's DI seam
    # takes the seed Fake so this test stays about org scoping.
    from noctusai_lib.integrations.resend import FakeResendDomains
    from app.modules.email_marketing.routers.settings import get_resend_domains

    app = spoofed.raw().app
    app.dependency_overrides[get_resend_domains] = lambda: FakeResendDomains()
    try:
        resp = spoofed.post("/api/email-marketing/settings/domains", json={"domain": "a.com"})
    finally:
        app.dependency_overrides.pop(get_resend_domains, None)
    assert resp.status_code == 200, resp.text
    rows = spoofed.mock_supabase.table("sender_domains").inserted_payloads
    assert [r["org_id"] for r in rows] == [TRUSTED_ORG]


def test_media_creation_brand_kit_created_in_trusted_org(spoofed):
    resp = spoofed.post("/api/media-creation/brand-kits", json={"name": "Kit"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["org_id"] == TRUSTED_ORG


def test_media_creation_trusted_row_missing_is_refused_not_metadata(client):
    client.mock_supabase.set_table_data("noctus_users", [])
    resp = client.post("/api/media-creation/brand-kits", json={"name": "Kit"})
    assert resp.status_code == 403, resp.text


def test_legacy_jwt_bridge_org_is_trusted_row_not_metadata(spoofed):
    from app.dependencies import _legacy_jwt_resolver

    ctx = asyncio.new_event_loop().run_until_complete(_legacy_jwt_resolver("jwt"))
    assert str(ctx.org_id) == TRUSTED_ORG


def test_legacy_jwt_bridge_refuses_user_without_trusted_row(client):
    from app.dependencies import _legacy_jwt_resolver

    client.mock_supabase.set_table_data("noctus_users", [])
    with pytest.raises(HTTPException) as exc:
        asyncio.new_event_loop().run_until_complete(_legacy_jwt_resolver("jwt"))
    assert exc.value.status_code == 403
