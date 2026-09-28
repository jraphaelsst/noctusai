"""SEC-1 (2026-09-28) — org-scoped admin surfaces in core require
`settings:manage` (or a platform admin), and secrets never leave the API raw.

Fixtures (tests/conftest.py): `client` is an authenticated plain member —
`check_permission` denies, `get_current_admin` 403s, no `noctus_users.role`
row, so `require_org_permission` has no path to allow. `admin_client` is
allowed. Every denial is asserted as a strict `== 403` AND as "nothing was
written".
"""
from __future__ import annotations

import pytest


# ── /api/settings ──────────────────────────────────────────────────────────


class TestOrgSettingsWritesNeedSettingsManage:
    def test_member_cannot_upsert_org_setting(self, client):
        resp = client.put("/api/settings/org/openai_api_key", json={"value": "sk-mine", "is_secret": True})
        assert resp.status_code == 403
        assert client.mock_supabase.table("org_settings").upserted_payloads == []

    def test_member_cannot_delete_org_setting(self, client):
        client.mock_supabase.set_table_data("org_settings", [{"id": "s1", "org_id": "org-1", "key": "k"}])
        resp = client.delete("/api/settings/org/k")
        assert resp.status_code == 403
        assert [r["key"] for r in client.mock_supabase.table("org_settings")._data] == ["k"]

    def test_member_can_still_list_org_settings_masked(self, client):
        client.mock_supabase.set_table_data("org_settings", [
            {"id": "s1", "org_id": "org-1", "key": "openai_api_key", "value": "sk-secret-value", "is_secret": True},
        ])
        resp = client.get("/api/settings/org")
        assert resp.status_code == 200
        assert "sk-secret" not in resp.json()["data"][0]["value"]


class TestResolveIsPlatformAdminOnly:
    def test_member_gets_403(self, client):
        client.mock_supabase.set_table_data("platform_settings", [
            {"key": "openai_api_key", "value": "sk-platform-raw", "is_secret": True},
        ])
        resp = client.get("/api/settings/resolve/openai_api_key")
        assert resp.status_code == 403
        assert "sk-platform-raw" not in resp.text

    def test_admin_gets_secret_values_masked(self, admin_client):
        admin_client.mock_supabase.set_table_data("org_settings", [])
        admin_client.mock_supabase.set_table_data("platform_settings", [
            {"key": "openai_api_key", "value": "sk-platform-raw-1234", "is_secret": True},
        ])
        resp = admin_client.get("/api/settings/resolve/openai_api_key")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source"] == "platform"
        assert "sk-platform-raw" not in data["value"]
        assert data["value"].endswith("1234")

    def test_admin_gets_non_secret_value_verbatim(self, admin_client):
        admin_client.mock_supabase.set_table_data("org_settings", [])
        admin_client.mock_supabase.set_table_data("platform_settings", [
            {"key": "redis_url", "value": "redis://x:6379", "is_secret": False},
        ])
        resp = admin_client.get("/api/settings/resolve/redis_url")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == "redis://x:6379"


# ── /api/webhooks ──────────────────────────────────────────────────────────


class TestWebhooksNeedSettingsManage:
    @pytest.mark.parametrize("method,url,body", [
        ("get", "/api/webhooks", None),
        ("post", "/api/webhooks", {"url": "https://evil.example/h", "events": ["subscription.created"]}),
        ("patch", "/api/webhooks/wh-1", {"url": "https://evil.example/h"}),
        ("delete", "/api/webhooks/wh-1", None),
        ("get", "/api/webhooks/wh-1/deliveries", None),
    ])
    def test_member_gets_403(self, client, method, url, body):
        sb = client.mock_supabase
        sb.set_table_data("webhook_endpoints", [
            {"id": "wh-1", "org_id": "org-1", "url": "https://ok.example/h", "secret": "whsec_x"},
        ])
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client, method)(url, **kwargs)
        assert resp.status_code == 403
        builder = sb.table("webhook_endpoints")
        assert builder.inserted_payloads == []
        assert builder.updated_payloads == []
        assert [r["id"] for r in builder._data] == ["wh-1"]

    def test_update_response_never_carries_the_signing_secret(self, admin_client):
        admin_client.mock_supabase.set_table_data("webhook_endpoints", [
            {"id": "wh-1", "org_id": "org-1", "url": "https://ok.example/h", "secret": "whsec_x"},
        ])
        resp = admin_client.patch("/api/webhooks/wh-1", json={"url": "https://ok.example/h2"})
        assert resp.status_code == 200
        assert "secret" not in resp.json()["data"]

    def test_create_returns_signing_secret_once_not_the_raw_column(self, admin_client):
        admin_client.mock_supabase.set_table_data("webhook_endpoints", [])
        resp = admin_client.post("/api/webhooks", json={
            "url": "https://ok.example/h", "events": ["subscription.created"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["signing_secret"].startswith("whsec_")
        assert "secret" not in data


# ── /api/api-keys ──────────────────────────────────────────────────────────


class TestApiKeyWritesNeedSettingsManage:
    def test_member_cannot_create(self, client):
        resp = client.post("/api/api-keys", json={"name": "mine", "scopes": ["read", "write"]})
        assert resp.status_code == 403
        assert client.mock_supabase.table("api_keys").inserted_payloads == []

    def test_member_cannot_rescope(self, client):
        client.mock_supabase.set_table_data("api_keys", [{"id": "k1", "org_id": "org-1", "name": "k", "scopes": ["read"]}])
        resp = client.patch("/api/api-keys/k1", json={"scopes": ["read", "write"]})
        assert resp.status_code == 403
        assert client.mock_supabase.table("api_keys").updated_payloads == []

    def test_member_cannot_revoke(self, client):
        client.mock_supabase.set_table_data("api_keys", [{"id": "k1", "org_id": "org-1", "is_active": True}])
        resp = client.delete("/api/api-keys/k1")
        assert resp.status_code == 403
        assert client.mock_supabase.table("api_keys").updated_payloads == []

    def test_member_can_still_list_prefixes(self, client):
        client.mock_supabase.set_table_data("api_keys", [])
        resp = client.get("/api/api-keys")
        assert resp.status_code == 200


# ── require_org_permission: the platform-operator branch ───────────────────


class TestPlatformOperatorBranch:
    def test_platform_admin_row_passes_without_a_role_grant(self, client):
        """`check_permission` denies (plain member role), but the caller's
        trusted `noctus_users.role` is 'admin' — the NoctusAI operator, acting
        inside their own trusted org."""
        client.mock_supabase.set_table_data("noctus_users", [
            {"id": "test-user-123", "org_id": "org-1", "role": "admin", "org_role": "member"},
        ])
        client.mock_supabase.set_table_data("api_keys", [])
        resp = client.post("/api/api-keys", json={"name": "ops", "scopes": ["read"]})
        assert resp.status_code == 200, resp.text

    def test_org_owner_role_cascade_is_not_a_platform_admin(self, client):
        """`org_role='owner'` must NOT satisfy the operator branch — only
        `role='admin'` does (the strict resolver, not the SSO cascade)."""
        client.mock_supabase.set_table_data("noctus_users", [
            {"id": "test-user-123", "org_id": "org-1", "role": "user", "org_role": "owner"},
        ])
        resp = client.post("/api/api-keys", json={"name": "x", "scopes": ["read"]})
        assert resp.status_code == 403
