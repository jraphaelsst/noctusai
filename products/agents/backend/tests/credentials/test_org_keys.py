"""Per-ORG LLM keys (Lais A1, B1): the resolver an ``llm`` turn uses reads this
org's rows only, and the platform guard is per-provider.

Nothing of ours is patched: the encrypted store is the seed's real
``make_credential_store`` over an in-memory table double, ``org_settings`` is
the resolver's own DI seam, and the "platform Anthropic key" is planted through
the seed's real ``register_credential_override`` (the exact tier-0 hook
``studio/wiring.py`` installs) to prove the org resolver cannot see it.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from noctusai_lib.config import credentials as seed_credentials
from noctusai_lib.config.deploy_config import MissingProdConfigError
from noctusai_lib.security.api_keys import EncryptionNotConfigured, put_api_key
from noctusai_lib.security.app_config import FakeAppConfigStore

from app.credentials.org_keys import (
    LLM_API_KEY_SPECS,
    build_llm_key_store,
    make_org_llm_key_resolver,
    resolve_org_llm_key,
)
from app.credentials.resolver import CredentialResolver, require_resolved_runtime_config
from tests.credentials.conftest import make_settings

ORG_A, ORG_B = uuid4(), uuid4()
FERNET = Fernet.generate_key().decode()


class _Rows:
    """A tiny PostgREST-table double backing the seed's real credential store."""

    def __init__(self):
        self.rows: list[dict] = []
        self._f: dict = {}
        self._op = None
        self._payload = None

    # query builder
    def table(self, name):
        assert name == "credentials"
        t = _Rows.__new__(_Rows)
        t.rows, t._f, t._op, t._payload = self.rows, {}, None, None
        return t

    def schema(self, _):
        return self

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._f[col] = val
        return self

    def limit(self, *_a):
        return self

    def upsert(self, payload, **_k):
        self._op, self._payload = "upsert", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        class R:
            data = None

        r = R()
        match = [x for x in self.rows if all(x.get(c) == v for c, v in self._f.items())]
        if self._op == "select":
            r.data = match
        elif self._op == "upsert":
            self.rows[:] = [x for x in self.rows if not (
                x["org_id"] == self._payload["org_id"] and x["provider"] == self._payload["provider"])]
            row = {"id": str(uuid4()), "created_at": "2026-01-01T00:00:00+00:00",
                   "updated_at": "2026-01-01T00:00:00+00:00", **self._payload}
            self.rows.append(row)
            r.data = [row]
        else:
            for x in match:
                self.rows.remove(x)
            r.data = match
        return r


@pytest.fixture
def store():
    return build_llm_key_store(_Rows(), encryption_key=FERNET)


@pytest.fixture(autouse=True)
def _clean_seed_credentials():
    seed_credentials._reset_for_testing()
    yield
    seed_credentials._reset_for_testing()


class TestResolveOrgLlmKey:
    def test_reads_only_the_callers_org_from_the_encrypted_store(self, store):
        put_api_key(store, str(ORG_A), "openai_api_key", "sk-a")
        put_api_key(store, str(ORG_B), "openai_api_key", "sk-b")
        none_settings = lambda key, org: None  # noqa: E731
        assert resolve_org_llm_key("openai", ORG_A, store_factory=lambda: store,
                                   org_settings_reader=none_settings) == "sk-a"
        assert resolve_org_llm_key("openai", ORG_B, store_factory=lambda: store,
                                   org_settings_reader=none_settings) == "sk-b"
        assert resolve_org_llm_key("openai", uuid4(), store_factory=lambda: store,
                                   org_settings_reader=none_settings) is None

    def test_org_settings_is_the_second_org_scoped_tier(self, store):
        reader = lambda key, org: "sk-from-org-settings" if (key, org) == ("openai_api_key", str(ORG_A)) else None  # noqa: E731
        assert resolve_org_llm_key("openai", ORG_A, store_factory=lambda: store, org_settings_reader=reader) == "sk-from-org-settings"
        assert resolve_org_llm_key("openai", ORG_B, store_factory=lambda: store, org_settings_reader=reader) is None

    def test_platform_override_env_and_platform_settings_are_unreachable(self, store, monkeypatch):
        """The Julia-academia tier-0 override (a platform Anthropic key), an env
        key and a platform_settings row all exist — an org with no key of its own
        still resolves to None."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-env")
        seed_credentials.register_credential_override(
            lambda key, org: "sk-ant-PLATFORM" if key == "anthropic_api_key" else None
        )
        # Sanity: the seed's general chain DOES leak the platform key ...
        assert seed_credentials.resolve_credential("anthropic_api_key", str(ORG_A)) == "sk-ant-PLATFORM"
        # ... and this resolver cannot see it.
        assert resolve_org_llm_key("anthropic", ORG_A, store_factory=lambda: store) is None
        assert resolve_org_llm_key("openai", ORG_A, store_factory=lambda: store) is None

    def test_unusable_encryption_key_degrades_to_org_settings_not_to_a_crash(self):
        def broken():
            raise EncryptionNotConfigured("no key")

        reader = lambda key, org: "sk-os"  # noqa: E731
        assert resolve_org_llm_key("openai", ORG_A, store_factory=broken, org_settings_reader=reader) == "sk-os"
        assert resolve_org_llm_key("openai", ORG_A, store_factory=broken,
                                   org_settings_reader=lambda k, o: None) is None

    def test_unknown_provider_is_none(self, store):
        assert resolve_org_llm_key("gemini", ORG_A, store_factory=lambda: store) is None

    def test_resolver_factory_has_the_runtime_shape(self, store):
        put_api_key(store, str(ORG_A), "anthropic_api_key", "sk-ant-a")
        resolver = make_org_llm_key_resolver(store_factory=lambda: store, org_settings_reader=lambda k, o: None)
        assert resolver("anthropic", ORG_A) == "sk-ant-a"
        assert resolver("anthropic", ORG_B) is None

    def test_specs_name_the_two_provider_keys(self):
        assert [s.name for s in LLM_API_KEY_SPECS] == ["openai_api_key", "anthropic_api_key"]
        assert all(s.testable and s.is_secret for s in LLM_API_KEY_SPECS)


class TestPerProviderPlatformGuard:
    def test_openai_only_org_boots_without_an_anthropic_key_in_a_deploy_context(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")  # external deploy signal
        resolver = CredentialResolver(FakeAppConfigStore(), make_settings(anthropic_api_key=""))
        require_resolved_runtime_config(resolver, provider="openai")  # no raise

    def test_the_claude_sdk_path_still_requires_it(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        resolver = CredentialResolver(FakeAppConfigStore(), make_settings(anthropic_api_key=""))
        with pytest.raises(MissingProdConfigError) as exc:
            require_resolved_runtime_config(resolver)
        assert exc.value.missing_keys == ["ANTHROPIC_API_KEY"]
        with pytest.raises(MissingProdConfigError):
            require_resolved_runtime_config(resolver, provider="anthropic")

    def test_llm_agent_runtime_is_built_in_a_deploy_context_with_no_anthropic_key(self, monkeypatch):
        from types import SimpleNamespace

        from app.runtime import get_agent_runtime
        from app.runtime.llm_runtime import LlmToolRuntime

        monkeypatch.setenv("APP_ENV", "production")
        settings = SimpleNamespace(llm_turn_capacity=2, llm_history_messages=5, llm_max_tool_iterations=3,
                                   llm_daily_budget_usd=0.0, supabase_service_role_key="")
        rt = get_agent_runtime(settings, SimpleNamespace(runtime="llm"), ORG_A)
        assert isinstance(rt, LlmToolRuntime)
