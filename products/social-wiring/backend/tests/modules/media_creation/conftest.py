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

        from app.config import settings
        from app.modules.media_creation import register
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
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)


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
