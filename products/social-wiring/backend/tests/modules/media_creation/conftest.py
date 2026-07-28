"""Fixtures for the ``media_creation`` module tests.

Mirrors the ``email_marketing`` module conftest: mounts the module via its
own ``register()`` contract on top of a seed-factory app so the tests
exercise the real registration seam (not a hand-rolled mock).

Seed shadow-finder purge is owned by the parent ``tests/conftest.py``.
This conftest deliberately does NOT re-purge — see the subtree
``tests/modules/conftest.py`` docstring for the mechanism.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[6]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
for _p in (_FRAMEWORK, _LIB):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import pytest  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from noctusai_lib.testing import (  # noqa: E402,F401
    AuthClient,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)


@pytest.fixture(autouse=True)
def _unconfigured_meta(monkeypatch):
    """Pin the Meta adapter to the UNCONFIGURED (Fake) shape for this module.

    `PublishService._resolve_meta_adapter` reads `META_SYSTEM_USER_TOKEN`
    straight off the process environment, so whether these tests exercise
    `FakeMetaAdapter` or the real Graph adapter depended on whether the RUNNER
    happened to have Meta credentials exported. They pass locally (no creds)
    and fail under the pre-deploy gate (creds inherited from the MCP server's
    env) — a test whose outcome tracks ambient credentials is a false-green
    generator in one direction and a false-red in the other.

    The publish tests assert the unconfigured contract explicitly
    (`configured is False`, `media_id` prefixed `IG1_carousel_`), so removing
    the variable makes the precondition they already assume EXPLICIT rather
    than ambient. Tests that want the configured shape inject an adapter
    directly, which takes precedence over this.
    """
    monkeypatch.delenv("META_SYSTEM_USER_TOKEN", raising=False)


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id="test-org-123"))
    )

    with patch(
        "noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb
    ), patch(
        "noctusai_seed.database.DatabaseModule.get_core_client",
        return_value=mock_sb,
    ), patch(
        "noctusai_seed.database.DatabaseModule.get_admin_client",
        return_value=mock_sb,
    ):
        from noctusai_seed import create_product_app
        from noctusai_lib.integrations.image_gen import FakeImageGenAdapter

        from app.config import settings
        from app.modules.media_creation import register
        from app.modules.media_creation.routers.generation import (
            get_generation_service,
            get_post_service,
        )
        from app.modules.media_creation.services.generation_service import (
            GenerationService,
        )
        from app.modules.media_creation.services.post_service import PostService
        from app.rate_limit import limiter

        reg = register()
        standard = list(reg.standard_routers)
        app = create_product_app(
            name="Social Wiring (media_creation test harness)",
            schema="social_wiring",
            settings=settings,
            version="0.1.0",
            limiter=limiter,
            standard_routers=standard,
            routers=list(reg.routers),
        )
        bind_consent_module_to_mock(mock_sb)

        # DI-test seam (KB § PATTERNS/di-test-seam.md Class-A): override the
        # generation/post service factories so the render + LLM endpoints run
        # offline against the mock Supabase client. The GenerationService gets
        # an injected ``FakeImageGenAdapter`` so ``_resolve_image_gen_adapter``
        # short-circuits before the real Supabase-backed ``resolve_credential``
        # key provider (the "supabase_url is required" failure the patch fixes).
        # NOT a self-monkeypatch — a real production seam swapped at the boundary.
        _org_id = "test-org-123"
        app.dependency_overrides[get_post_service] = lambda: PostService(
            mock_sb, _org_id
        )
        app.dependency_overrides[get_generation_service] = lambda: GenerationService(
            mock_sb, _org_id, image_gen_adapter=FakeImageGenAdapter()
        )
        try:
            tc = TestClient(app)
            yield AuthClient(tc, mock_sb)
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def seeded_kit(client):
    """Pre-insert one brand kit so post tests can reference it directly."""
    client.mock_supabase.from_("mc_brand_kits").insert(
        {
            "id": "kit-1",
            "org_id": "test-org-123",
            "name": "Granja Premium",
            "persona": "Voice: editorial, calm, premium. Forbidden: hype.",
            "design_system": "Variant: premium. Palette: warm dark earth tones.",
            "default_lang": "pt-BR",
        }
    ).execute()
    yield "kit-1"
