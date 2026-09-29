"""Tests for `app/routers/api_keys_router.py` — owner decision 2026-09-28:
IgIg gets its own per-org Anthropic key (same mechanism `social-wiring`
and `community` consume).

The generic contract (paths, response shapes, status codes, admin-gate
dispatch, encryption-gap -> 503) is already covered by the seed's own
`seed/framework/backend/tests/routers/test_api_keys_router.py`. These
tests assert ONLY what is product-specific: this product's spec list is
mounted (just `anthropic_api_key`), admin-gating uses the TRUSTED
`public.noctus_users` cascade (`resolve_platform_role` / `get_user_role`
— never `user_metadata`), the store is `igig.credentials`
(`IGIG_COFRE_KEY`-gated), and the org-scoped local store wins over the
env-var tier (credential override precedence) — which is also THE
mechanism `app/services/assistente.py` relies on via
`noctusai_lib.integrations.llm.chat_completion`'s
`resolve_credential("anthropic_api_key", org_id)` call.

Auth-boundary tests assert strict `== 401`.
"""
from __future__ import annotations

from noctusai_lib.security.encrypted_tokens import generate_key
from noctusai_lib.testing import TEST_USER_ID

from app.config import settings

_SPEC_KEYS = {"anthropic_api_key"}


def _set_encryption_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "igig_cofre_key", generate_key().decode())  # self-patch-ok: configuration value, not a guard


def _isolate_platform_chain(monkeypatch) -> None:
    """Cut `resolve_credential`'s tier-1/tier-2 REAL Supabase network calls
    (`org_settings` / `platform_settings` — the SAME shared project prod
    uses) and clear the ambient `ANTHROPIC_API_KEY` env var.

    `anthropic_api_key` is not a product-invented spec name like
    community's `stripe_secret_key` — it is the SAME generic key every
    product's LLM stack resolves (`noctusai_lib.integrations.llm`'s
    `f"{provider}_api_key"`), so this environment's REAL platform-wide
    default (deliberately configured for production) is live in
    `platform_settings` and would otherwise leak into "nothing configured
    anywhere" assertions non-deterministically. `_get_public_client` is
    the seed's OWN external-network boundary (a real Supabase client),
    never IgIg's guard — patching it is the sanctioned "patch only
    external boundaries" case, not a self-monkeypatch."""
    monkeypatch.setattr(
        "noctusai_lib.config.credentials._get_public_client", lambda: None
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _seed_admin(client) -> None:
    """Grant the default mock user (`TEST_USER_ID`) org-admin via the
    TRUSTED `public.noctus_users` cascade — the only door `get_user_role`
    / `resolve_platform_role` read (never `user_metadata`, which any
    user can rewrite). `set_table_data` (not `.insert().execute()`) —
    the mock answers an UNSET `noctus_users` table with an implicit
    `org_role: "member"` row re-derived per call (SEC-2, 2026-09-28), so
    an `.insert()` only appends a second, never-selected row."""
    client.mock_supabase.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_role": "admin", "role": "user",
         "org_id": "test-org-123", "email": "admin@example.com"},
    ])


class TestAuthBoundary:
    def test_list_without_auth_401(self, client):
        resp = client.raw().get("/api/settings/api-keys")
        assert resp.status_code == 401

    def test_put_without_auth_401(self, client):
        resp = client.raw().put(
            "/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-x"}
        )
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        resp = client.raw().delete("/api/settings/api-keys/anthropic_api_key")
        assert resp.status_code == 401

    def test_test_without_auth_401(self, client):
        resp = client.raw().post("/api/settings/api-keys/anthropic_api_key/test")
        assert resp.status_code == 401


class TestListApiKeys:
    def test_lists_exactly_igigs_managed_keys(self, client, monkeypatch):
        _isolate_platform_chain(monkeypatch)
        resp = client.get("/api/settings/api-keys")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(_SPEC_KEYS)
        assert {item["key"] for item in body["items"]} == _SPEC_KEYS

    def test_list_degrades_gracefully_without_cofre_key(self, client, monkeypatch):
        # Explicit unset (never rely on ambient absence) -> READ degrades
        # to the platform-chain-only tier, never a 503
        # (KB § seed-fake-real-adapter.md).
        _isolate_platform_chain(monkeypatch)
        monkeypatch.setattr(settings, "igig_cofre_key", "")  # self-patch-ok: configuration value, not a guard
        resp = client.get("/api/settings/api-keys")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["configured"] is False


class TestAdminGate:
    def test_member_cannot_write(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)  # isolate the admin check from the cofre gap
        resp = client.put(
            "/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-x"}
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "admin_obrigatorio"

    def test_member_cannot_delete(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        resp = client.delete("/api/settings/api-keys/anthropic_api_key")
        assert resp.status_code == 403


class TestEncryptionGap:
    def test_write_without_cofre_key_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, "igig_cofre_key", "")  # self-patch-ok: configuration value, not a guard
        _seed_admin(client)
        resp = client.put(
            "/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-x"}
        )
        assert resp.status_code == 503


class TestWritePersistence:
    def test_admin_put_persists_and_masks_hint(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        _seed_admin(client)
        resp = client.put(
            "/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-abcd1234"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["hint"] == "...1234"
        assert body["source"] == "local"
        assert "sk-ant-abcd1234" not in resp.text

    def test_admin_delete_removes_override(self, client, monkeypatch):
        _isolate_platform_chain(monkeypatch)
        _set_encryption_key(monkeypatch)
        _seed_admin(client)
        client.put("/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-x"})
        resp = client.delete("/api/settings/api-keys/anthropic_api_key")
        assert resp.status_code == 200
        assert resp.json()["configured"] is False


class TestCredentialOverridePrecedence:
    """The org-stored override must win over the env tier — THE mechanism
    `app/services/assistente.py` relies on to pick up an org's own key."""

    def test_org_store_wins_over_env(self, client, monkeypatch):
        _set_encryption_key(monkeypatch)
        _seed_admin(client)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-should-lose")

        client.put(
            "/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-local-should-win"}
        )
        resp = client.get("/api/settings/api-keys")
        item = next(i for i in resp.json()["items"] if i["key"] == "anthropic_api_key")
        assert item["source"] == "local"
        assert item["hint"] == "...-win"

    def test_env_alone_still_resolves(self, client, monkeypatch):
        _isolate_platform_chain(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-only")
        resp = client.get("/api/settings/api-keys")
        item = next(i for i in resp.json()["items"] if i["key"] == "anthropic_api_key")
        assert item["configured"] is True
        assert item["source"] == "env"

    def test_override_resolves_the_stored_key_for_the_org(self, client, monkeypatch):
        """The exact seam `assistente.py`'s `chat_completion` call reads
        through — `resolve_credential("anthropic_api_key", org_id)` must
        return the org's own stored value once it is set, with NO other
        wiring beyond `register_credential_override` (already registered
        at `app.main` import time)."""
        from noctusai_lib.config.credentials import resolve_credential

        _set_encryption_key(monkeypatch)
        _seed_admin(client)
        client.put(
            "/api/settings/api-keys/anthropic_api_key", json={"value": "sk-ant-assistente"}
        )
        # `get_current_user_org`'s org_id fallback is the raw `user_metadata`
        # value the `client` fixture's `MockUser` carries.
        assert resolve_credential("anthropic_api_key", "test-org-123") == "sk-ant-assistente"


class TestTestApiKey:
    def test_testable_key_not_configured_422(self, client, monkeypatch):
        _isolate_platform_chain(monkeypatch)
        resp = client.post("/api/settings/api-keys/anthropic_api_key/test")
        assert resp.status_code == 422

    def test_unmanaged_key_404(self, client):
        resp = client.post("/api/settings/api-keys/not_a_real_key/test")
        assert resp.status_code == 404
