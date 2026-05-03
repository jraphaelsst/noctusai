"""Phase 5 tests: backend endpoint logic for the shared LLM router +
Core credentials router.

Tests target the *logic* — masking, scope resolution, permission checks,
registry-driven enumeration — not the full HTTP round-trip (that's covered
by integration tests in each product's `tests/routers/` suite post-migration).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_LIB = Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"
_FRAMEWORK = Path(__file__).resolve().parents[3] / "seed" / "framework" / "backend"
_CORE = Path(__file__).resolve().parents[3] / "products" / "core" / "backend"
for p in (_LIB, _FRAMEWORK, _CORE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import noctusai_lib.integrations.llm  # noqa: F401,E402


# ── Core credentials router ─────────────────────────────────────

class TestCoreCredentialsMasking:
    def test_mask_short_value(self):
        from app.routers.credentials import _mask

        assert _mask(None) is None
        assert _mask("") is None
        assert _mask("abcd") == "****"
        assert _mask("a") == "****"

    def test_mask_long_value_reveals_last_four(self):
        from app.routers.credentials import _mask

        assert _mask("sk-1234567890ABCD") == "*" * 13 + "ABCD"
        assert len(_mask("sk-abcdefghij")) == len("sk-abcdefghij")

    def test_fetch_key_reads_from_data(self):
        from app.routers.credentials import _fetch_key

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"value": "sk-real"}
        ]
        # For platform_settings (single .eq), no org_id path taken.
        assert _fetch_key(db, "platform_settings", "openai_api_key") == "sk-real"

    def test_fetch_key_returns_none_on_missing(self):
        from app.routers.credentials import _fetch_key

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        assert _fetch_key(db, "platform_settings", "x") is None

    def test_fetch_key_returns_none_on_exception(self):
        from app.routers.credentials import _fetch_key

        db = MagicMock()
        db.table.side_effect = RuntimeError("db down")
        assert _fetch_key(db, "platform_settings", "x") is None


# ── Shared llm_router: /providers ─────────────────────────────────

class TestLLMRouterProviders:
    def test_has_any_stub_model_matches_catalog(self):
        """Phases 13/14 promoted Anthropic + Gemini to real; `stub` flags are
        now all False across the catalog."""
        from noctusai_seed.llm_router import _has_any_stub_model

        assert _has_any_stub_model("anthropic") is False
        assert _has_any_stub_model("gemini") is False
        assert _has_any_stub_model("openai") is False

    def test_factory_returns_router_with_expected_routes(self):
        from noctusai_seed.llm_router import create_llm_router

        deps = MagicMock()
        router = create_llm_router(deps)
        paths = {route.path for route in router.routes}
        assert "/api/llm/providers" in paths
        assert "/api/llm/models" in paths
        assert "/api/llm/preferences" in paths


# ── Shared llm_router: /models ────────────────────────────────────

class TestLLMRouterModels:
    def test_catalog_drives_filter(self):
        """The route's filter is just models_for(provider, kind) — verify the
        underlying filter we rely on."""
        from noctusai_lib.integrations.llm import models_for

        chat = models_for("openai", "chat")
        audio = models_for("openai", "audio")
        assert {m.kind for m in chat} == {"chat"}
        assert {m.kind for m in audio} == {"audio"}
        assert all(m.provider == "openai" for m in chat + audio)

    def test_unknown_provider_returns_empty(self):
        from noctusai_lib.integrations.llm import models_for

        assert models_for("does-not-exist") == []


# ── Preferences upsert (PUT) shape ────────────────────────────────

class TestPreferencesBody:
    def test_accepts_minimal_payload(self):
        from noctusai_seed.llm_router import PreferencesBody

        body = PreferencesBody(provider="openai")
        assert body.provider == "openai"
        assert body.chat_model is None
        assert body.embedding_model is None

    def test_rejects_empty_provider(self):
        from noctusai_seed.llm_router import PreferencesBody

        with pytest.raises(Exception):  # pydantic ValidationError
            PreferencesBody(provider="")


# ── Standard routers include llm_router ───────────────────────────

class TestStandardRoutersInclude:
    def test_build_standard_routers_includes_llm_when_opted_in(self):
        from fastapi import APIRouter

        from noctusai_seed.routers import build_standard_routers

        deps = MagicMock()
        deps.get_current_user = MagicMock()
        deps.get_user_role = MagicMock(return_value="owner")
        deps.get_org_id = MagicMock(return_value="org-123")

        class _FakeSettings:
            cors_origins = []
            debug = True
            product_slug = "test"

        routers = build_standard_routers(
            deps,
            _FakeSettings(),
            product_name="Test",
            version="0.1.0",
            names=["health", "notificacoes", "team", "llm"],
        )
        all_paths: set[str] = set()
        for r in routers:
            assert isinstance(r, APIRouter)
            for route in r.routes:
                all_paths.add(route.path)

        # Health, notifications, team are pre-existing; llm is new in Phase 5.
        assert "/api/health" in all_paths
        assert "/api/llm/providers" in all_paths
        assert "/api/llm/models" in all_paths
        assert "/api/llm/preferences" in all_paths


# ── Registry-driven provider list matches catalog ─────────────────

class TestProvidersReflectRegistry:
    def test_all_providers_appear_in_catalog(self):
        """Every registered provider must have at least one catalog entry.
        Without this, /api/llm/providers would list a provider but /models
        would return empty — broken UX."""
        from noctusai_lib.integrations.llm import all_providers, models_for
        from noctusai_lib.integrations.llm.registry import list_providers

        catalog_providers = set(all_providers())
        registered = set(list_providers())
        for p in registered:
            assert p in catalog_providers, (
                f"Provider {p!r} is registered but has zero catalog entries."
            )
            assert models_for(p), f"Provider {p!r} has no models in catalog."
