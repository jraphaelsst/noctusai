"""Tests for `noctusai_lib.security.api_keys`.

The lifted (`community uses social-wiring's mechanisms`, Slice A) org-scoped
managed-API-keys mechanism. Exercises the dataclasses, `mask_value`,
`require_fernet`, the store builder + read/put/delete helpers (via the
seed's own `FakeCredentialStore` — `build_api_key_store(client=None, ...)`
degrades to Fake, exactly like `token_store.make_credential_store`'s own
contract, so no Supabase double is needed here), the two-tier resolution
seam, `make_local_credential_override`, and the DDL template.
"""
from __future__ import annotations

import pytest

from noctusai_lib.security.api_keys import (
    ApiKeyOption,
    ApiKeyResolution,
    ApiKeySpec,
    EncryptionNotConfigured,
    PROVIDER_PREFIX,
    build_api_key_store,
    credentials_table_ddl,
    delete_api_key,
    get_spec,
    make_local_credential_override,
    mask_value,
    provider_for,
    put_api_key,
    read_local_api_key,
    require_fernet,
    resolve_api_key,
    resolve_api_key_detail,
)
from noctusai_lib.security.encrypted_tokens import generate_key


SPECS = (
    ApiKeySpec(
        name="openai_api_key",
        label="OpenAI API Key",
        description="test",
        is_secret=True,
        testable=True,
        input_type="password",
    ),
    ApiKeySpec(
        name="llm_vision_provider",
        label="Provider",
        description="test",
        is_secret=False,
        input_type="select",
        options=(
            ApiKeyOption(value="openai", label="OpenAI"),
            ApiKeyOption(value="anthropic", label="Anthropic"),
        ),
        default="openai",
    ),
)


class TestApiKeySpec:
    def test_allowed_values_from_options(self):
        spec = SPECS[1]
        assert spec.allowed_values == ("openai", "anthropic")

    def test_allowed_values_empty_when_no_options(self):
        assert SPECS[0].allowed_values == ()

    def test_get_spec_found_and_missing(self):
        assert get_spec("openai_api_key", SPECS) is SPECS[0]
        assert get_spec("nope", SPECS) is None


class TestProviderFor:
    def test_default_prefix(self):
        assert provider_for("openai_api_key") == "api_key:openai_api_key"

    def test_custom_prefix(self):
        assert provider_for("openai_api_key", prefix="custom:") == "custom:openai_api_key"

    def test_default_prefix_constant(self):
        assert PROVIDER_PREFIX == "api_key:"


class TestMaskValue:
    def test_none_value_returns_none(self):
        assert mask_value(None, SPECS[0]) is None

    def test_empty_value_returns_none(self):
        assert mask_value("", SPECS[0]) is None

    def test_secret_masks_to_last_four(self):
        assert mask_value("sk-abcdef1234", SPECS[0]) == "...1234"

    def test_short_secret_collapses_to_dots(self):
        assert mask_value("ab", SPECS[0]) == "••••"

    def test_non_secret_returned_verbatim(self):
        assert mask_value("openai", SPECS[1]) == "openai"


class TestRequireFernet:
    def test_empty_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            require_fernet(None)
        with pytest.raises(EncryptionNotConfigured):
            require_fernet("")

    def test_malformed_key_raises(self):
        with pytest.raises(EncryptionNotConfigured):
            require_fernet("not-a-valid-fernet-key")

    def test_valid_key_returns_fernet(self):
        key = generate_key().decode()
        fernet = require_fernet(key)
        assert fernet.encrypt(b"x")  # usable


class TestBuildApiKeyStore:
    def test_missing_key_raises_encryption_not_configured(self):
        with pytest.raises(EncryptionNotConfigured):
            build_api_key_store(None, encryption_key=None)

    def test_no_client_degrades_to_fake_store(self):
        """`client=None` -> Fake, mirroring `token_store.make_credential_store`'s
        own contract — this is the seam that lets these tests avoid a
        Supabase query-builder double entirely."""
        key = generate_key().decode()
        store = build_api_key_store(None, encryption_key=key)
        # Fake round-trips exactly like the Real would.
        store.put("org1", "api_key:openai_api_key", {"value": "sk-test"})
        got = store.get("org1", "api_key:openai_api_key")
        assert got.tokens == {"value": "sk-test"}


class TestReadPutDeleteApiKey:
    def _store(self):
        key = generate_key().decode()
        return build_api_key_store(None, encryption_key=key)

    def test_put_then_read_roundtrips(self):
        store = self._store()
        put_api_key(store, "org1", "openai_api_key", "sk-abc")
        stored = read_local_api_key(store, "org1", "openai_api_key")
        assert stored.tokens == {"value": "sk-abc"}

    def test_read_missing_returns_none(self):
        store = self._store()
        assert read_local_api_key(store, "org1", "openai_api_key") is None

    def test_delete_returns_true_when_present_false_when_absent(self):
        store = self._store()
        put_api_key(store, "org1", "openai_api_key", "sk-abc")
        assert delete_api_key(store, "org1", "openai_api_key") is True
        assert delete_api_key(store, "org1", "openai_api_key") is False

    def test_uses_provider_prefix_namespacing(self):
        store = self._store()
        put_api_key(store, "org1", "openai_api_key", "sk-abc")
        # Stored under the namespaced provider, not the bare key name.
        assert store.get("org1", "openai_api_key") is None
        assert store.get("org1", "api_key:openai_api_key") is not None


class TestResolveApiKeyDetail:
    def test_local_tier_wins_when_configured(self):
        key = generate_key().decode()
        store = build_api_key_store(None, encryption_key=key)
        put_api_key(store, "org1", "openai_api_key", "sk-local")
        resolution = resolve_api_key_detail(
            "openai_api_key", "org1", store=store, resolver=lambda k, o: "sk-platform"
        )
        assert resolution == ApiKeyResolution(
            name="openai_api_key", value="sk-local", source="local", updated_at=resolution.updated_at
        )
        assert resolution.configured is True

    def test_falls_back_to_platform_chain_when_local_empty(self):
        key = generate_key().decode()
        store = build_api_key_store(None, encryption_key=key)
        resolution = resolve_api_key_detail(
            "openai_api_key", "org1", store=store, resolver=lambda k, o: "sk-platform"
        )
        assert resolution.value == "sk-platform"
        assert resolution.source == "platform"

    def test_env_source_detected_when_chain_matches_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        resolution = resolve_api_key_detail(
            "openai_api_key", "org1", store=None, resolver=lambda k, o: "sk-env"
        )
        assert resolution.source == "env"

    def test_miss_returns_none_source(self):
        resolution = resolve_api_key_detail(
            "openai_api_key", "org1", store=None, resolver=lambda k, o: None
        )
        assert resolution.value is None
        assert resolution.source is None
        assert resolution.configured is False

    def test_no_store_no_store_factory_skips_local_tier(self):
        resolution = resolve_api_key_detail(
            "openai_api_key", "org1", resolver=lambda k, o: "sk-platform"
        )
        assert resolution.source == "platform"

    def test_store_factory_lazily_builds_and_degrades_on_encryption_not_configured(self):
        def _raising_factory():
            raise EncryptionNotConfigured("no key")

        resolution = resolve_api_key_detail(
            "openai_api_key",
            "org1",
            store_factory=_raising_factory,
            resolver=lambda k, o: "sk-platform",
        )
        assert resolution.value == "sk-platform"

    def test_resolve_api_key_returns_bare_value(self):
        assert resolve_api_key("openai_api_key", "org1", resolver=lambda k, o: "sk-x") == "sk-x"
        assert resolve_api_key("openai_api_key", "org1", resolver=lambda k, o: None) is None


class TestMakeLocalCredentialOverride:
    def test_unmanaged_key_returns_none_without_building_store(self):
        calls = []

        def _factory():
            calls.append(1)
            return build_api_key_store(None, encryption_key=generate_key().decode())

        override = make_local_credential_override(SPECS, _factory)
        assert override("not_a_managed_key", "org1") is None
        assert calls == []  # short-circuited before touching the store

    def test_none_org_id_returns_none(self):
        override = make_local_credential_override(
            SPECS, lambda: build_api_key_store(None, encryption_key=generate_key().decode())
        )
        assert override("openai_api_key", None) is None

    def test_managed_key_reads_from_store(self):
        key = generate_key().decode()
        store = build_api_key_store(None, encryption_key=key)
        put_api_key(store, "org1", "openai_api_key", "sk-local")

        override = make_local_credential_override(SPECS, lambda: store)
        assert override("openai_api_key", "org1") == "sk-local"

    def test_never_recurses_into_resolve_credential(self):
        """The override is store-ONLY — it must not itself call
        `resolve_credential` (that would recurse forever via
        `register_credential_override`)."""
        store = build_api_key_store(None, encryption_key=generate_key().decode())
        override = make_local_credential_override(SPECS, lambda: store)
        # A miss in the local store is a real miss — None, not a fallback.
        assert override("openai_api_key", "org1") is None


class TestCredentialsTableDdl:
    def test_contains_org_scoped_rls_and_service_role_bypass(self):
        ddl = credentials_table_ddl("social_wiring")
        assert "CREATE TABLE social_wiring.credentials" in ddl
        assert "org_id = current_org_id()" in ddl
        assert '"service_role_bypass"' in ddl
        assert "ENABLE ROW LEVEL SECURITY" in ddl

    def test_custom_table_name(self):
        ddl = credentials_table_ddl("acme", table="my_creds")
        assert "CREATE TABLE acme.my_creds" in ddl
        assert "idx_acme_my_creds_org" in ddl
