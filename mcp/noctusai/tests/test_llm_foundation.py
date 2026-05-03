"""Phase 1 foundation tests.

Covers:
  - credentials module (3-tier chain, Tier 3 env fallback, missing keys)
  - LLM exception hierarchy (inheritance + PT messages + status codes)
  - Registry (register / retrieve / unknown name)
  - Model catalog (shape, stub flags, provider filters)
"""
import sys
from pathlib import Path

import pytest

# Ensure the lib is importable even when the test runs from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB = _REPO_ROOT / "seed" / "lib" / "backend"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


# ── Credentials ─────────────────────────────────────────────────

class TestCredentialsChain:
    def test_tier_3_env_fallback_when_db_unconfigured(self, monkeypatch):
        """Without `configure_credentials()`, Tier 1+2 skip; Tier 3 (env) wins."""
        from noctusai_lib.config.credentials import _reset_for_testing, resolve_credential

        _reset_for_testing()
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        assert resolve_credential("openai_api_key") == "sk-from-env"

    def test_returns_none_when_nothing_configured(self, monkeypatch):
        from noctusai_lib.config.credentials import _reset_for_testing, resolve_credential

        _reset_for_testing()
        monkeypatch.delenv("MADE_UP_KEY_XYZ", raising=False)
        assert resolve_credential("made_up_key_xyz") is None

    def test_env_key_is_uppercased(self, monkeypatch):
        """Tier 3 reads key.upper() from the environment."""
        from noctusai_lib.config.credentials import _reset_for_testing, resolve_credential

        _reset_for_testing()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-xyz")
        assert resolve_credential("anthropic_api_key") == "ant-xyz"

    def test_org_id_ignored_when_db_unconfigured(self, monkeypatch):
        """Passing org_id without DB config still falls through to Tier 3."""
        from noctusai_lib.config.credentials import _reset_for_testing, resolve_credential

        _reset_for_testing()
        monkeypatch.setenv("GEMINI_API_KEY", "gem-env-fallback")
        assert resolve_credential("gemini_api_key", org_id="some-org") == "gem-env-fallback"


# ── LLM exceptions ──────────────────────────────────────────────

class TestLLMExceptions:
    def test_llm_not_configured_default_pt_message(self):
        from noctusai_lib.integrations.llm import LLMNotConfigured

        exc = LLMNotConfigured("openai")
        assert "API Key não configurada" in exc.message
        assert exc.status_code == 400
        assert exc.details == {"provider": "openai"}
        assert exc.code == "LLM_NOT_CONFIGURED"

    def test_llm_not_configured_custom_message(self):
        from noctusai_lib.integrations.llm import LLMNotConfigured

        exc = LLMNotConfigured("anthropic", message="custom override")
        assert exc.message == "custom override"

    def test_llm_api_error_wraps_provider(self):
        from noctusai_lib.integrations.llm import LLMAPIError

        exc = LLMAPIError("openai", "rate limit exceeded")
        assert "Openai" in exc.message
        assert "rate limit exceeded" in exc.message
        assert exc.status_code == 502  # default: Bad Gateway

    def test_provider_not_implemented_mentions_guard_flag(self):
        from noctusai_lib.integrations.llm import ProviderNotImplemented

        exc = ProviderNotImplemented("anthropic")
        assert "stub" in exc.message.lower()
        assert "NOCTUSAI_ALLOW_STUB_PROVIDERS" in exc.message
        assert exc.status_code == 501
        assert exc.details == {"provider": "anthropic"}

    def test_all_inherit_appexception(self):
        from noctusai_lib.primitives.exceptions import AppException
        from noctusai_lib.integrations.llm import (
            LLMAPIError,
            LLMNotConfigured,
            ProviderNotImplemented,
        )

        assert issubclass(LLMNotConfigured, AppException)
        assert issubclass(LLMAPIError, AppException)
        assert issubclass(ProviderNotImplemented, AppException)


# ── Provider registry ───────────────────────────────────────────

class TestRegistry:
    """Registry tests save and restore the global registry state so they
    don't interfere with provider registrations from other test modules
    (Python caches imports — provider-module side effects only run once per
    process, so blowing away the registry permanently hides them from later
    tests that expect openai/anthropic/gemini to be registered)."""

    def setup_method(self):
        from noctusai_lib.integrations.llm import registry as _r

        self._saved = dict(_r._PROVIDERS)
        _r._PROVIDERS.clear()

    def teardown_method(self):
        from noctusai_lib.integrations.llm import registry as _r

        _r._PROVIDERS.clear()
        _r._PROVIDERS.update(self._saved)

    def test_unknown_provider_raises(self):
        from noctusai_lib.integrations.llm.registry import get_provider_class

        with pytest.raises(KeyError) as exc_info:
            get_provider_class("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_register_and_retrieve(self):
        from noctusai_lib.integrations.llm.registry import (
            get_provider_class,
            list_providers,
            register,
        )

        class Dummy:
            name = "dummy-test"

        register("dummy-test", Dummy)
        assert get_provider_class("dummy-test") is Dummy
        assert "dummy-test" in list_providers()

    def test_re_registration_wins(self):
        """Later register() call with the same name overwrites the earlier one."""
        from noctusai_lib.integrations.llm.registry import get_provider_class, register

        class First:
            name = "x"

        class Second:
            name = "x"

        register("x", First)
        register("x", Second)
        assert get_provider_class("x") is Second


# ── Model catalog ───────────────────────────────────────────────

class TestModelCatalog:
    def test_openai_chat_models_present(self):
        from noctusai_lib.integrations.llm import models_for

        chat = models_for("openai", "chat")
        ids = {m.id for m in chat}
        assert "gpt-4o" in ids
        assert "gpt-4o-mini" in ids

    def test_openai_has_embedding_and_audio(self):
        from noctusai_lib.integrations.llm import models_for

        assert any(m.kind == "embedding" for m in models_for("openai"))
        assert any(m.kind == "audio" for m in models_for("openai"))

    def test_anthropic_catalog_populated_real(self):
        """Phase 13 made Anthropic real — catalog entries now report stub=False."""
        from noctusai_lib.integrations.llm import models_for

        anthropic = models_for("anthropic")
        assert anthropic, "Anthropic catalog must not be empty"
        assert not any(m.stub for m in anthropic)

    def test_gemini_catalog_populated_real(self):
        """Phase 14 made Gemini real — catalog entries now report stub=False."""
        from noctusai_lib.integrations.llm import models_for

        gemini = models_for("gemini")
        assert gemini
        assert not any(m.stub for m in gemini)

    def test_openai_not_stub(self):
        from noctusai_lib.integrations.llm import models_for

        openai_models = models_for("openai")
        assert openai_models
        assert not any(m.stub for m in openai_models)

    def test_all_providers(self):
        from noctusai_lib.integrations.llm import all_providers

        providers = set(all_providers())
        assert providers >= {"openai", "anthropic", "gemini"}

    def test_is_stub_model(self):
        from noctusai_lib.integrations.llm import is_stub_model

        # After Phases 13/14, Anthropic + Gemini are real — no stub entries
        # remain in the catalog. is_stub_model reflects that.
        assert is_stub_model("anthropic", "claude-opus-4-7") is False
        assert is_stub_model("openai", "gpt-4o-mini") is False
        assert is_stub_model("unknown", "mystery") is False

    def test_model_entries_are_frozen(self):
        """ModelEntry is a frozen dataclass — mutation must fail."""
        from dataclasses import FrozenInstanceError

        from noctusai_lib.integrations.llm import MODELS

        with pytest.raises(FrozenInstanceError):
            MODELS[0].label = "hacked"  # type: ignore[misc]


# ── LLMConfig ───────────────────────────────────────────────────

class TestLLMConfig:
    def test_minimal_construction(self):
        from noctusai_lib.integrations.llm import LLMConfig

        cfg = LLMConfig(key_provider=lambda p, org_id=None: "test-key")
        assert cfg.default_provider == "openai"
        assert cfg.default_chat_model == "gpt-4o-mini"
        assert cfg.cache_enabled is False

    def test_overrides_applied(self):
        from noctusai_lib.integrations.llm import LLMConfig

        cfg = LLMConfig(
            key_provider=lambda p, org_id=None: None,
            default_provider="anthropic",
            default_chat_model="claude-sonnet-4-6",
        )
        assert cfg.default_provider == "anthropic"
        assert cfg.default_chat_model == "claude-sonnet-4-6"

    def test_key_provider_receives_provider_and_org(self):
        """The callable signature is `(provider, org_id=None)` — verify both reach it."""
        from noctusai_lib.integrations.llm import LLMConfig

        calls = []

        def provider(p, org_id=None):
            calls.append((p, org_id))
            return "key-for-" + p

        cfg = LLMConfig(key_provider=provider)
        assert cfg.key_provider("openai", "org-a") == "key-for-openai"
        assert cfg.key_provider("anthropic") == "key-for-anthropic"
        assert calls == [("openai", "org-a"), ("anthropic", None)]
