"""Tests for `app/routers/api_keys_router.py` — Slice C (user decision
2026-09-17, "community uses social-wiring's mechanisms").

The generic contract (paths, response shapes, status codes, admin-gate
dispatch, encryption-gap -> 503) is already covered by the seed's own
`seed/framework/backend/tests/routers/test_api_keys_router.py`. These
tests assert ONLY what is product-specific: this product's spec list is
mounted, admin-gating uses `get_community_role` (this product's
`admin`/`moderador` vocabulary, not the generic owner/admin
`user_metadata` check), the store is `community.credentials`
(ENCRYPTION_KEY-gated), and the org-scoped local store wins over the
env-var tier (credential override precedence).

Auth-boundary tests assert strict `== 401`.
"""
from __future__ import annotations

from noctusai_lib.security.encrypted_tokens import generate_key

from app.config import settings
from tests.conftest import seed_community_role

_SPEC_KEYS = {
    "stripe_secret_key", "stripe_webhook_secret",
    "asaas_api_key", "asaas_webhook_token", "turnstile_secret_key",
}


def _set_encryption_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "encryption_key", generate_key().decode())  # self-patch-ok: configuration value, not a guard


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        resp = client.raw().get("/api/settings/api-keys")
        assert resp.status_code == 401

    def test_put_without_auth_401(self, client):
        resp = client.raw().put(
            "/api/settings/api-keys/stripe_secret_key", json={"value": "sk_x"}
        )
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        resp = client.raw().delete("/api/settings/api-keys/stripe_secret_key")
        assert resp.status_code == 401

    def test_test_without_auth_401(self, client):
        resp = client.raw().post("/api/settings/api-keys/stripe_secret_key/test")
        assert resp.status_code == 401


class TestListApiKeys:
    def test_lists_exactly_communitys_managed_keys(self, client):
        resp = client.get("/api/settings/api-keys")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(_SPEC_KEYS)
        assert {item["key"] for item in body["items"]} == _SPEC_KEYS

    def test_list_degrades_gracefully_without_encryption_key(self, client, monkeypatch):
        # Explicit unset (never rely on ambient absence) -> READ degrades
        # to the platform-chain-only tier, never a 503
        # (KB § seed-fake-real-adapter.md).
        monkeypatch.setattr(settings, "encryption_key", "")  # self-patch-ok: configuration value, not a guard
        resp = client.get("/api/settings/api-keys")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["configured"] is False


class TestAdminGate:
    def test_moderador_cannot_write(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)  # admin check runs AFTER the store dep — isolate it from the encryption gap
        seed_community_role(client, org_role="moderador")
        resp = client.put(
            "/api/settings/api-keys/stripe_secret_key", json={"value": "sk_x"}
        )
        assert resp.status_code == 403

    def test_moderador_cannot_delete(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)  # admin check runs AFTER the store dep — isolate it from the encryption gap
        seed_community_role(client, org_role="moderador")
        resp = client.delete("/api/settings/api-keys/stripe_secret_key")
        assert resp.status_code == 403


class TestEncryptionGap:
    def test_write_without_encryption_key_503(self, client, monkeypatch):
        # Explicit unset — never rely on an unset ambient ENCRYPTION_KEY:
        # the repo-root `.env` a dev machine loads for OTHER products can
        # carry a real value, which would silently pass this test for
        # the wrong reason.
        monkeypatch.setattr(settings, "encryption_key", "")  # self-patch-ok: configuration value, not a guard
        seed_community_role(client, org_role="admin")
        resp = client.put(
            "/api/settings/api-keys/stripe_secret_key", json={"value": "sk_x"}
        )
        assert resp.status_code == 503


class TestWritePersistence:
    def test_admin_put_persists_and_masks_hint(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        seed_community_role(client, org_role="admin")
        resp = client.put(
            "/api/settings/api-keys/stripe_secret_key", json={"value": "sk_live_abcd1234"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["hint"] == "...1234"
        assert body["source"] == "local"
        assert "sk_live_abcd1234" not in resp.text

    def test_admin_delete_removes_override(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        seed_community_role(client, org_role="admin")
        client.put("/api/settings/api-keys/stripe_secret_key", json={"value": "sk_x"})
        resp = client.delete("/api/settings/api-keys/stripe_secret_key")
        assert resp.status_code == 200
        assert resp.json()["configured"] is False


class TestCredentialOverridePrecedence:
    """Slice C: the org-stored override must win over the env tier."""

    def test_org_store_wins_over_env(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        seed_community_role(client, org_role="admin")
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_env_should_lose")

        client.put(
            "/api/settings/api-keys/stripe_secret_key", json={"value": "sk_local_should_win"}
        )
        resp = client.get("/api/settings/api-keys")
        item = next(i for i in resp.json()["items"] if i["key"] == "stripe_secret_key")
        assert item["source"] == "local"
        assert item["hint"] == "..._win"

    def test_env_alone_still_resolves(self, client, monkeypatch):
        # No local override -> the platform chain's env tier (Slice C's
        # env-fallback contract).
        monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", "env-only-token")
        resp = client.get("/api/settings/api-keys")
        item = next(i for i in resp.json()["items"] if i["key"] == "asaas_webhook_token")
        assert item["configured"] is True
        assert item["source"] == "env"


class TestTestApiKey:
    def test_untestable_key_400(self, client):
        # `stripe_webhook_secret` is `testable=False` — no tester registered.
        resp = client.post("/api/settings/api-keys/stripe_webhook_secret/test")
        assert resp.status_code == 400

    def test_testable_key_not_configured_422(self, client):
        resp = client.post("/api/settings/api-keys/stripe_secret_key/test")
        assert resp.status_code == 422
