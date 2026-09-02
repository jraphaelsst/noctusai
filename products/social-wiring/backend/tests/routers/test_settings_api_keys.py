"""Operator-settable API keys — /api/settings/api-keys*.

The three keys the certidões / matrículas workflows need per-org, set in
the UI, Fernet-encrypted into the EXISTING ``social_wiring.credentials``
table (no new table, no new crypto), resolved through
``app.services.api_keys_store.resolve_api_key``.

Coverage:
  - Auth boundary: unauthenticated is strictly 401 (never "401 or 404").
  - Admin gate: a plain member gets 403 on both writes; owner passes.
  - Write-only: the value never appears in ANY response body.
  - Round-trip through the injected store: PUT then GET reports
    ``configured`` + ``source="local"`` + a masked tail.
  - Non-secret keys are shown in full (an e-mail is not a secret).
  - DELETE re-resolves and stays honest when the platform tier still
    answers — "removed" must not mean "gone" when it is still live.
  - Resolver falls back to the platform tier, and to env through the
    REAL seed chain.
  - ENCRYPTION_KEY missing ⇒ 503 and NOTHING written (never plaintext).
  - Unknown key ⇒ 404; blank value ⇒ 422; unconfigured test ⇒ 422.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.security.token_store import FakeCredentialStore
from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse

from app.services.api_keys_store import (
    MANAGED_API_KEYS,
    provider_for,
    resolve_api_key,
    resolve_api_key_detail,
)

ORG_ID = "11111111-1111-4111-8111-111111111111"


def _mock_sb(*, org_role: str | None = None):
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=org_role))
    )
    return mock_sb


def _build_client(*, org_role: str | None, authenticated: bool = True):
    from noctusai_lib.testing import bind_consent_module_to_mock

    mock_sb = _mock_sb(org_role=org_role)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def admin_client():
    yield from _build_client(org_role="owner")


@pytest.fixture
def member_client():
    yield from _build_client(org_role=None)


@pytest.fixture
def anon_api_keys_client():
    """Same app, no Authorization header — the only shape that can
    produce an honest 401 (`KB § PATTERNS/compliance/
    auth-boundary-false-green.md`)."""
    yield from _build_client(org_role="owner")


def _auth_header():
    return {"Authorization": "Bearer test-token"}


def _fake_store():
    """A Fake shaped like the REAL one this product builds — the
    ``credentials`` table has no JSON metadata column, so
    ``metadata_column=None`` + the three denormalized columns (mirrors
    ``credential_vault._METADATA_COLUMNS``). Same fail-loud parity on an
    unmapped metadata key."""
    return FakeCredentialStore(
        metadata_column=None,
        metadata_columns={
            "channel_id": "channel_id",
            "channel_title": "channel_title",
            "scopes": "scopes",
        },
    )


@pytest.fixture
def store_override():
    """Override BOTH store DI seams (write-raising + read-optional) with
    the SAME FakeCredentialStore, so a PUT then a GET in one test observe
    the same rows. Per KB § PATTERNS/backend/di-test-seam.md (Class-B) —
    no monkeypatch of our own code."""
    from app.main import app
    from app.routers.settings_router import (
        get_api_key_store_dep,
        get_api_key_store_optional_dep,
    )

    store = _fake_store()
    previous = {
        dep: app.dependency_overrides.get(dep)
        for dep in (get_api_key_store_dep, get_api_key_store_optional_dep)
    }
    app.dependency_overrides[get_api_key_store_dep] = lambda: store
    app.dependency_overrides[get_api_key_store_optional_dep] = lambda: store
    yield store
    for dep, prev in previous.items():
        if prev is None:
            app.dependency_overrides.pop(dep, None)
        else:
            app.dependency_overrides[dep] = prev


@pytest.fixture
def no_platform_tier():
    """Neutralise the AMBIENT platform chain for the router tests.

    ``create_product_app`` wires ``configure_credentials`` against the
    REAL shared Supabase project, so without this a GET would read (and
    possibly resolve from) live rows — the same ambient-DB hazard
    ``isolate_meta_config_db`` exists for. Substitutes the tier-2 SOURCE
    only; the local tier under test is untouched.
    """
    from app.routers import settings_router

    original = settings_router.resolve_api_key_detail

    def _isolated(name, org_id, *, store=..., **kwargs):
        kwargs["resolver"] = lambda _key, _org: None
        if store is ...:
            return original(name, org_id, **kwargs)
        return original(name, org_id, store=store, **kwargs)

    # self-patch-ok: swaps the tier-2 SOURCE the router reads, exactly as
    # `isolate_meta_config_db` does for the Meta app-config store. The
    # resolution logic under test is the real one.
    settings_router.resolve_api_key_detail = _isolated
    yield
    settings_router.resolve_api_key_detail = original


class TestAuthBoundary:
    def test_list_requires_authentication(self, anon_api_keys_client):
        resp = anon_api_keys_client.get("/api/settings/api-keys")
        assert resp.status_code == 401, resp.text

    def test_write_requires_authentication(self, anon_api_keys_client):
        resp = anon_api_keys_client.put(
            "/api/settings/api-keys/infosimples_token", json={"value": "tok"}
        )
        assert resp.status_code == 401, resp.text

    def test_delete_requires_authentication(self, anon_api_keys_client):
        resp = anon_api_keys_client.delete(
            "/api/settings/api-keys/infosimples_token"
        )
        assert resp.status_code == 401, resp.text


class TestAdminGate:
    def test_member_cannot_write(self, member_client, store_override, no_platform_tier):
        resp = member_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok-123"},
            headers=_auth_header(),
        )
        assert resp.status_code == 403, resp.text
        assert store_override.get(ORG_ID, provider_for("infosimples_token")) is None

    def test_member_cannot_delete(self, member_client, store_override, no_platform_tier):
        resp = member_client.delete(
            "/api/settings/api-keys/infosimples_token", headers=_auth_header()
        )
        assert resp.status_code == 403, resp.text

    def test_member_can_read(self, member_client, store_override, no_platform_tier):
        """Read is open to any org member — only writes are admin-gated,
        the same split every other org config on this router uses."""
        resp = member_client.get("/api/settings/api-keys", headers=_auth_header())
        assert resp.status_code == 200, resp.text

    def test_owner_can_write(self, admin_client, store_override, no_platform_tier):
        resp = admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok-123"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text


class TestListing:
    def test_lists_every_managed_key_as_unconfigured(
        self, admin_client, store_override, no_platform_tier
    ):
        resp = admin_client.get("/api/settings/api-keys", headers=_auth_header())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [item["key"] for item in body["items"]] == list(MANAGED_API_KEYS)
        assert body["total"] == len(MANAGED_API_KEYS)
        for item in body["items"]:
            assert item["configured"] is False
            assert item["source"] is None
            assert item["hint"] is None

    def test_unknown_key_is_404(self, admin_client, store_override, no_platform_tier):
        resp = admin_client.put(
            "/api/settings/api-keys/stripe_secret",
            json={"value": "sk_live_x"},
            headers=_auth_header(),
        )
        assert resp.status_code == 404, resp.text


class TestWriteOnly:
    def test_put_response_never_contains_the_value(
        self, admin_client, store_override, no_platform_tier
    ):
        resp = admin_client.put(
            "/api/settings/api-keys/openai_api_key",
            json={"value": "sk-SUPER-SECRET-VALUE"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        assert "sk-SUPER-SECRET-VALUE" not in resp.text
        body = resp.json()
        assert body["configured"] is True
        assert body["source"] == "local"
        assert body["hint"] == "...ALUE"

    def test_list_response_never_contains_the_value(
        self, admin_client, store_override, no_platform_tier
    ):
        admin_client.put(
            "/api/settings/api-keys/openai_api_key",
            json={"value": "sk-SUPER-SECRET-VALUE"},
            headers=_auth_header(),
        )
        resp = admin_client.get("/api/settings/api-keys", headers=_auth_header())
        assert resp.status_code == 200, resp.text
        assert "sk-SUPER-SECRET-VALUE" not in resp.text
        entry = next(i for i in resp.json()["items"] if i["key"] == "openai_api_key")
        assert entry["configured"] is True
        assert entry["hint"] == "...ALUE"
        assert entry["source"] == "local"
        assert entry["updated_at"] is not None

    def test_stored_bundle_is_written_under_the_namespaced_provider(
        self, admin_client, store_override, no_platform_tier
    ):
        admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok-abcdef"},
            headers=_auth_header(),
        )
        stored = store_override.get(ORG_ID, "api_key:infosimples_token")
        assert stored is not None
        assert stored.tokens == {"value": "tok-abcdef"}

    def test_blank_value_is_rejected_and_never_clears(
        self, admin_client, store_override, no_platform_tier
    ):
        admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok-abcdef"},
            headers=_auth_header(),
        )
        resp = admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "   "},
            headers=_auth_header(),
        )
        assert resp.status_code == 422, resp.text
        stored = store_override.get(ORG_ID, provider_for("infosimples_token"))
        assert stored.tokens == {"value": "tok-abcdef"}

    def test_empty_string_is_rejected_by_the_schema(
        self, admin_client, store_override, no_platform_tier
    ):
        resp = admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": ""},
            headers=_auth_header(),
        )
        assert resp.status_code == 422, resp.text

    def test_unknown_field_is_rejected(
        self, admin_client, store_override, no_platform_tier
    ):
        """StrictHttpModel — an extra key is a 422, not a silent drop."""
        resp = admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok", "is_secret": False},
            headers=_auth_header(),
        )
        assert resp.status_code == 422, resp.text


class TestNonSecretKey:
    def test_email_is_shown_in_full(
        self, admin_client, store_override, no_platform_tier
    ):
        admin_client.put(
            "/api/settings/api-keys/infosimples_email_envio",
            json={"value": "juridico@empresa.com.br"},
            headers=_auth_header(),
        )
        resp = admin_client.get("/api/settings/api-keys", headers=_auth_header())
        entry = next(
            i for i in resp.json()["items"] if i["key"] == "infosimples_email_envio"
        )
        assert entry["is_secret"] is False
        assert entry["hint"] == "juridico@empresa.com.br"


class TestDelete:
    def test_removes_the_local_override(
        self, admin_client, store_override, no_platform_tier
    ):
        admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok-abcdef"},
            headers=_auth_header(),
        )
        resp = admin_client.delete(
            "/api/settings/api-keys/infosimples_token", headers=_auth_header()
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["configured"] is False
        assert body["source"] is None
        assert store_override.get(ORG_ID, provider_for("infosimples_token")) is None

    def test_is_idempotent_when_nothing_was_stored(
        self, admin_client, store_override, no_platform_tier
    ):
        resp = admin_client.delete(
            "/api/settings/api-keys/infosimples_token", headers=_auth_header()
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["configured"] is False

    def test_says_the_key_is_still_live_from_the_platform_tier(
        self, admin_client, store_override
    ):
        """Dropping the local override must not report "gone" when the
        platform chain still answers — the operator would stop looking."""
        from app.routers import settings_router

        original = settings_router.resolve_api_key_detail

        def _platform_answers(name, org_id, *, store=..., **kwargs):
            kwargs["resolver"] = lambda _key, _org: "platform-value-9999"
            if store is ...:
                return original(name, org_id, **kwargs)
            return original(name, org_id, store=store, **kwargs)

        # self-patch-ok: substitutes the tier-2 SOURCE only (same shape as
        # the `no_platform_tier` fixture); the resolution logic is real.
        settings_router.resolve_api_key_detail = _platform_answers
        try:
            admin_client.put(
                "/api/settings/api-keys/infosimples_token",
                json={"value": "tok-local"},
                headers=_auth_header(),
            )
            resp = admin_client.delete(
                "/api/settings/api-keys/infosimples_token", headers=_auth_header()
            )
        finally:
            settings_router.resolve_api_key_detail = original
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["configured"] is True
        assert body["source"] == "platform"
        assert "platform-value-9999" not in resp.text


class TestEncryptionKeyMissing:
    """A missing/malformed ENCRYPTION_KEY must 503 the WRITE — never fall
    back to storing plaintext. The refusal itself lives in
    ``credential_vault.require_fernet``; these assert (a) the store
    builder really refuses, and (b) the router maps that refusal to a 503
    BEFORE the route body runs, so no write is even reachable."""

    def test_put_is_503_and_the_route_body_never_runs(
        self, admin_client, monkeypatch
    ):
        from app.config import settings as app_settings

        # Clears the AMBIENT deployment config (the developer's root .env
        # carries a real ENCRYPTION_KEY), reproducing the misconfigured
        # deployment exactly. `build_credential_store` reads this
        # singleton as its canonical runtime source, so this is the only
        # honest way to stage the gap — the router + vault logic under
        # test is entirely real, and the DELETE case below proves the
        # same gate covers both writes.
        monkeypatch.setattr(  # self-patch-ok: neutralises ambient .env, not our logic
            app_settings, "encryption_key", "", raising=False
        )
        resp = admin_client.put(
            "/api/settings/api-keys/infosimples_token",
            json={"value": "tok-should-never-persist"},
            headers=_auth_header(),
        )
        # 503 is raised while RESOLVING the store dependency, so the
        # handler — and therefore any write — is unreachable by
        # construction, not merely unobserved.
        assert resp.status_code == 503, resp.text
        # Seed error envelope: {"error": {"code", "message"}}.
        assert "ENCRYPTION_KEY" in resp.json()["error"]["message"]
        assert "tok-should-never-persist" not in resp.text

    def test_delete_is_503_too(self, admin_client, monkeypatch):
        from app.config import settings as app_settings

        monkeypatch.setattr(  # self-patch-ok: neutralises ambient .env, not our logic
            app_settings, "encryption_key", "", raising=False
        )
        resp = admin_client.delete(
            "/api/settings/api-keys/infosimples_token", headers=_auth_header()
        )
        assert resp.status_code == 503, resp.text

    def test_read_survives_a_missing_key_via_the_platform_tier(
        self, admin_client, monkeypatch
    ):
        """The READ path must NOT 503 — the platform tier can still
        answer, and an operator locked out of the status page cannot even
        see what is wrong."""
        from app.config import settings as app_settings

        monkeypatch.setattr(  # self-patch-ok: neutralises ambient .env, not our logic
            app_settings, "encryption_key", "", raising=False
        )
        resp = admin_client.get("/api/settings/api-keys", headers=_auth_header())
        assert resp.status_code == 200, resp.text

    def test_build_store_refuses_without_a_key(self):
        from app.services.api_keys_store import build_api_key_store
        from app.services.credential_vault import EncryptionNotConfigured

        with pytest.raises(EncryptionNotConfigured):
            build_api_key_store(object(), encryption_key="")

    def test_build_store_refuses_a_malformed_key(self):
        from app.services.api_keys_store import build_api_key_store
        from app.services.credential_vault import EncryptionNotConfigured

        with pytest.raises(EncryptionNotConfigured):
            build_api_key_store(object(), encryption_key="not-a-fernet-key")


class TestTestEndpoint:
    def test_unconfigured_key_is_422_with_the_pt_br_sentence(
        self, admin_client, store_override, no_platform_tier
    ):
        resp = admin_client.post(
            "/api/settings/api-keys/infosimples_token/test", headers=_auth_header()
        )
        assert resp.status_code == 422, resp.text
        assert "Configurações → Chaves de API" in resp.json()["error"]["message"]

    def test_untestable_key_is_400(
        self, admin_client, store_override, no_platform_tier
    ):
        admin_client.put(
            "/api/settings/api-keys/infosimples_email_envio",
            json={"value": "juridico@empresa.com.br"},
            headers=_auth_header(),
        )
        resp = admin_client.post(
            "/api/settings/api-keys/infosimples_email_envio/test",
            headers=_auth_header(),
        )
        assert resp.status_code == 400, resp.text

    def test_unknown_key_is_404(self, admin_client, store_override, no_platform_tier):
        resp = admin_client.post(
            "/api/settings/api-keys/stripe_secret/test", headers=_auth_header()
        )
        assert resp.status_code == 404, resp.text

    def test_requires_authentication(self, anon_api_keys_client):
        resp = anon_api_keys_client.post(
            "/api/settings/api-keys/infosimples_token/test"
        )
        assert resp.status_code == 401, resp.text


class TestResolver:
    """The seam the certidões / matrículas branches import."""

    def test_local_store_wins(self):
        store = _fake_store()
        store.put(ORG_ID, provider_for("infosimples_token"), {"value": "local-tok"})
        result = resolve_api_key_detail(
            "infosimples_token",
            ORG_ID,
            store=store,
            resolver=lambda _k, _o: "platform-tok",
        )
        assert result.value == "local-tok"
        assert result.source == "local"

    def test_falls_back_to_the_platform_tier(self):
        """Nothing stored locally ⇒ a key already configured for this org
        elsewhere keeps working, without re-entry."""
        result = resolve_api_key_detail(
            "infosimples_token",
            ORG_ID,
            store=_fake_store(),
            resolver=lambda key, org: "platform-tok" if key == "infosimples_token" else None,
        )
        assert result.value == "platform-tok"
        assert result.source == "platform"
        assert result.updated_at is None

    def test_falls_back_when_the_local_tier_is_unavailable(self):
        """``store=None`` is how the router says "ENCRYPTION_KEY is
        unusable" — the read must still resolve, not 503."""
        result = resolve_api_key_detail(
            "openai_api_key",
            ORG_ID,
            store=None,
            resolver=lambda _k, _o: "platform-key",
        )
        assert result.value == "platform-key"
        assert result.source == "platform"

    def test_env_tier_is_labelled_env_through_the_real_seed_chain(self, monkeypatch):
        """End-to-end through the REAL ``resolve_credential``: the seed's
        own ``_reset_for_testing`` hook drops the configured public
        client, so tiers 1-2 are skipped without any network call and the
        env tier is what answers."""
        from noctusai_lib.config import credentials as seed_credentials
        from app.config import settings as app_settings

        seed_credentials._reset_for_testing()
        monkeypatch.setenv("INFOSIMPLES_TOKEN", "env-token-value")
        try:
            result = resolve_api_key_detail(
                "infosimples_token", ORG_ID, store=_fake_store()
            )
        finally:
            # Restore the ambient wiring `create_product_app` installed,
            # through the seed's own public entry point.
            seed_credentials.configure_credentials(
                supabase_url=app_settings.supabase_url,
                supabase_anon_key=app_settings.supabase_anon_key,
                supabase_service_role_key=app_settings.supabase_service_role_key,
            )
        assert result.value == "env-token-value"
        assert result.source == "env"

    def test_miss_returns_none_and_never_raises(self):
        assert (
            resolve_api_key_detail(
                "openai_api_key",
                ORG_ID,
                store=_fake_store(),
                resolver=lambda _k, _o: None,
            ).value
            is None
        )

    def test_public_signature_delegates_to_the_detail_function(self):
        """``resolve_api_key(name, org_id)`` — the exact two-positional
        signature the peer branches import — returns the bare value the
        detail function resolved, and nothing else."""
        from app.services import api_keys_store

        original = api_keys_store.resolve_api_key_detail
        calls: list[tuple] = []

        def _recorded(name, org_id, **kwargs):
            calls.append((name, org_id, kwargs))
            return api_keys_store.ApiKeyResolution(
                name=name, value="sk-local", source="local"
            )

        # self-patch-ok: asserts the DELEGATION contract of a 1-line
        # public shim; the resolution behaviour it delegates to is
        # covered for real by every other test in this class.
        api_keys_store.resolve_api_key_detail = _recorded
        try:
            assert resolve_api_key("openai_api_key", ORG_ID) == "sk-local"
        finally:
            api_keys_store.resolve_api_key_detail = original
        assert calls == [("openai_api_key", ORG_ID, {})]

    def test_no_org_skips_the_local_tier(self):
        """A background job with no org context must not silently read
        another org's row — tier 1 is org-scoped by construction."""
        store = _fake_store()
        store.put(ORG_ID, provider_for("openai_api_key"), {"value": "sk-local"})
        result = resolve_api_key_detail(
            "openai_api_key", None, store=store, resolver=lambda _k, _o: None
        )
        assert result.value is None
        assert result.source is None


class TestLlmKeyProvider:
    def test_maps_a_provider_name_to_its_key(self):
        from app.services import api_keys_store

        seen: list[str] = []

        def _fake_detail(name, org_id, **_kwargs):
            seen.append(name)
            return api_keys_store.ApiKeyResolution(
                name=name, value="sk-x", source="local"
            )

        original = api_keys_store.resolve_api_key_detail
        # self-patch-ok: this asserts the NAME MAPPING (`openai` →
        # `openai_api_key`), which is the whole content of the adapter;
        # the resolution itself is covered by TestResolver above.
        api_keys_store.resolve_api_key_detail = _fake_detail
        try:
            assert api_keys_store.llm_key_provider("openai", ORG_ID) == "sk-x"
        finally:
            api_keys_store.resolve_api_key_detail = original
        assert seen == ["openai_api_key"]
