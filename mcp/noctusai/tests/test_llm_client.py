"""Phase 3 tests: LLM client state (configure/get/shutdown) + seed-injector.

Validates that:
  - `configure_llm` / `get_llm_config` / `shutdown_llm` work as a singleton
  - `get_provider` caches instances per name
  - `resolve_api_key` routes through the configured key_provider
  - `default_llm_config` produces a config with the 3-tier key provider
  - Provider cache is cleared on reconfigure and on shutdown
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "seed" / "backend" / "lib"
_FRAMEWORK = Path(__file__).resolve().parents[3] / "seed" / "backend" / "framework"
for p in (_LIB, _FRAMEWORK):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# Import-time side-effects need the LLM package to register providers.
import noctusai_lib.integrations.llm  # noqa: F401,E402


class TestConfigureAndGet:
    def setup_method(self):
        from noctusai_lib.integrations.llm.client import _reset_for_testing

        _reset_for_testing()

    def test_get_without_configure_raises(self):
        from noctusai_lib.integrations.llm.client import get_llm_config

        with pytest.raises(RuntimeError) as exc_info:
            get_llm_config()
        assert "configure_llm" in str(exc_info.value)

    def test_configure_and_retrieve(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config

        cfg = LLMConfig(key_provider=lambda p, org_id=None: "k")
        configure_llm(cfg)
        assert get_llm_config() is cfg

    def test_reconfigure_wins(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config

        cfg1 = LLMConfig(key_provider=lambda p, org_id=None: "k1")
        cfg2 = LLMConfig(key_provider=lambda p, org_id=None: "k2")
        configure_llm(cfg1)
        configure_llm(cfg2)
        assert get_llm_config() is cfg2


class TestGetProvider:
    def setup_method(self):
        from noctusai_lib.integrations.llm.client import _reset_for_testing

        _reset_for_testing()

    def test_defaults_to_configured_provider(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_provider

        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: "k",
            default_provider="openai",
        ))
        provider = get_provider()
        assert provider.name == "openai"

    def test_explicit_name_overrides_default(self, monkeypatch):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_provider

        monkeypatch.setenv("NOCTUSAI_ALLOW_STUB_PROVIDERS", "1")
        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k"))
        p = get_provider("anthropic")
        assert p.name == "anthropic"

    def test_provider_instances_are_cached(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_provider

        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k"))
        a = get_provider("openai")
        b = get_provider("openai")
        assert a is b

    def test_reconfigure_clears_provider_cache(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_provider

        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k"))
        a = get_provider("openai")
        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k2"))
        b = get_provider("openai")
        assert a is not b


class TestResolveApiKey:
    def setup_method(self):
        from noctusai_lib.integrations.llm.client import _reset_for_testing

        _reset_for_testing()

    def test_routes_through_config(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, resolve_api_key

        seen = []

        def provider(name, org_id=None):
            seen.append((name, org_id))
            return "sk-abc"

        configure_llm(LLMConfig(key_provider=provider))
        key = resolve_api_key("openai", "org-42")
        assert key == "sk-abc"
        assert seen == [("openai", "org-42")]

    def test_raises_when_provider_returns_none(self):
        from noctusai_lib.integrations.llm import LLMConfig, LLMNotConfigured
        from noctusai_lib.integrations.llm.client import configure_llm, resolve_api_key

        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: None))
        with pytest.raises(LLMNotConfigured) as exc_info:
            resolve_api_key("openai")
        assert exc_info.value.details["provider"] == "openai"


class TestShutdown:
    def setup_method(self):
        from noctusai_lib.integrations.llm.client import _reset_for_testing

        _reset_for_testing()

    def test_shutdown_clears_state(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config, get_provider, shutdown_llm

        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k"))
        get_provider("openai")  # populate cache
        asyncio.run(shutdown_llm())
        with pytest.raises(RuntimeError):
            get_llm_config()

    def test_shutdown_calls_provider_close(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm, shutdown_llm

        closed = []

        class FakeClosable:
            name = "fake-closable"

            async def close(self):
                closed.append(self.name)

        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k"))
        _provider_cache["fake-closable"] = FakeClosable()
        asyncio.run(shutdown_llm())
        assert closed == ["fake-closable"]

    def test_shutdown_tolerates_close_error(self):
        """A misbehaving provider must not prevent shutdown."""
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm, shutdown_llm

        class Broken:
            name = "broken"

            async def close(self):
                raise RuntimeError("boom")

        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k"))
        _provider_cache["broken"] = Broken()
        # Must not raise
        asyncio.run(shutdown_llm())


class TestDefaultLLMConfig:
    def test_returns_llm_config_instance(self):
        from noctusai_lib.integrations.llm import LLMConfig
        from noctusai_seed.llm_defaults import default_llm_config

        cfg = default_llm_config()
        assert isinstance(cfg, LLMConfig)

    def test_defaults_shape(self):
        from noctusai_seed.llm_defaults import default_llm_config

        cfg = default_llm_config()
        assert cfg.default_provider == "openai"
        assert cfg.default_chat_model == "gpt-4o-mini"
        assert cfg.default_embedding_model == "text-embedding-3-small"

    def test_overrides_applied(self):
        from noctusai_seed.llm_defaults import default_llm_config

        cfg = default_llm_config(default_chat_model="gpt-4o")
        assert cfg.default_provider == "openai"  # unchanged
        assert cfg.default_chat_model == "gpt-4o"  # overridden

    def test_key_provider_uses_resolve_credential(self, monkeypatch):
        """default_llm_config's key_provider routes through the 3-tier chain."""
        from noctusai_lib.config.credentials import _reset_for_testing
        from noctusai_seed.llm_defaults import default_llm_config

        _reset_for_testing()
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cfg = default_llm_config()
        assert cfg.key_provider("openai") == "sk-from-env"
        assert cfg.key_provider("nonexistent_provider") is None
