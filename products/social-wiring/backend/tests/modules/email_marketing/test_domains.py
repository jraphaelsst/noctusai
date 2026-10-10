"""Sender-domain verification over the seed Resend Domains adapter (P1b(c)).

The adapter is injected through the router's DI seam
(`app.dependency_overrides[get_resend_domains]`) — never a patch of our code.
"""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.integrations.resend import FakeResendDomains

from app.config import settings
from app.dependencies import get_settings
from app.modules.email_marketing.routers.settings import (
    RESEND_NOT_CONFIGURED_DETAIL,
    get_resend_domains,
    map_resend_status,
)

BASE = "/api/email-marketing/settings/domains"
ORG = "test-org-123"


@pytest.fixture
def fake(client):
    fake = FakeResendDomains(verifiable={"ok.example.com"})
    app = client.raw().app
    app.dependency_overrides[get_resend_domains] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_resend_domains, None)


def _message(resp) -> str:
    """The seed error envelope: `{"error": {"code", "message"}}`."""
    return resp.json()["error"]["message"]


def _rows(client):
    return client.mock_supabase.table("sender_domains").select("*").execute().data


class TestCreate:
    def test_create_registers_at_resend_and_stores_dns_records(self, client, fake):
        client.mock_supabase.set_table_data("sender_domains", [])
        resp = client.post(BASE, json={"domain": "OK.example.com "})
        assert resp.status_code == 200, resp.text
        row = resp.json()["data"]
        assert row["domain"] == "ok.example.com"
        assert row["org_id"] == ORG
        assert row["status"] == "pending"  # Resend "not_started"
        assert row["resend_domain_id"] in fake.domains
        kinds = {r["record"] for r in row["dns_records"]}
        assert kinds == {"SPF", "DKIM", "DMARC"}

    def test_no_resend_key_is_503_never_a_fake_verified(self, client):
        client.mock_supabase.set_table_data("sender_domains", [])
        app = client.raw().app
        app.dependency_overrides[get_settings] = lambda: settings.model_copy(update={"resend_api_key": ""})
        try:
            resp = client.post(BASE, json={"domain": "x.example.com"})
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert resp.status_code == 503
        assert _message(resp) == RESEND_NOT_CONFIGURED_DETAIL
        assert client.mock_supabase.table("sender_domains").inserted_payloads == []

    def test_create_without_auth_is_strict_401(self, client, fake):
        resp = client.raw().post(BASE, json={"domain": "ok.example.com"})
        assert resp.status_code == 401


class TestVerify:
    def _seed(self, client, fake, name, org=ORG, resend_id=True):
        rec = asyncio.run(fake.create(name))
        client.mock_supabase.set_table_data("sender_domains", [{
            "id": "d1", "org_id": org, "domain": name, "status": "pending",
            "resend_domain_id": rec.id if resend_id else None,
            "dns_records": rec.records, "verified_at": None,
        }])

    def test_verified_maps_to_verified_with_timestamp(self, client, fake):
        self._seed(client, fake, "ok.example.com")
        resp = client.get(f"{BASE}/d1/verify")
        assert resp.status_code == 200, resp.text
        row = resp.json()["data"]
        assert row["status"] == "verified"
        assert row["verified_at"]
        assert _rows(client)[0]["status"] == "verified"

    def test_failed_maps_to_failed_without_timestamp(self, client, fake):
        self._seed(client, fake, "nodns.example.com")
        resp = client.get(f"{BASE}/d1/verify")
        assert resp.status_code == 200
        row = resp.json()["data"]
        assert row["status"] == "failed"
        assert row["verified_at"] is None

    def test_other_orgs_domain_is_404(self, client, fake):
        self._seed(client, fake, "ok.example.com", org="other-org")
        resp = client.get(f"{BASE}/d1/verify")
        assert resp.status_code == 404
        assert _rows(client)[0]["status"] == "pending"

    def test_legacy_row_without_resend_id_is_409(self, client, fake):
        self._seed(client, fake, "ok.example.com", resend_id=False)
        resp = client.get(f"{BASE}/d1/verify")
        assert resp.status_code == 409
        assert "adicione novamente" in _message(resp)

    def test_verify_without_key_is_503(self, client):
        client.mock_supabase.set_table_data("sender_domains", [{
            "id": "d1", "org_id": ORG, "domain": "ok.example.com", "status": "pending",
            "resend_domain_id": "dom_1", "dns_records": [], "verified_at": None,
        }])
        app = client.raw().app
        app.dependency_overrides[get_settings] = lambda: settings.model_copy(update={"resend_api_key": ""})
        try:
            resp = client.get(f"{BASE}/d1/verify")
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert resp.status_code == 503
        assert _rows(client)[0]["status"] == "pending"

    def test_verify_without_auth_is_strict_401(self, client, fake):
        resp = client.raw().get(f"{BASE}/d1/verify")
        assert resp.status_code == 401


@pytest.mark.parametrize("resend,ours", [
    ("verified", "verified"), ("failed", "failed"), ("temporary_failure", "failed"),
    ("pending", "pending"), ("not_started", "pending"), ("anything-new", "pending"),
])
def test_status_mapping(resend, ours):
    assert map_resend_status(resend) == ours
