"""Fixtures for the ``email_marketing`` module tests.

Mounts the module via its own ``register()`` contract on top of a
seed-factory app — exactly the shape ``app/main.py``'s assembly loop
produces once the ``MODULES`` append lands. This keeps the module's
tests green in isolation (before the architect splices the MODULES line
into ``main.py``) AND validates the real ``register()`` seam end-to-end
(routers + standard_routers + scheduler.configure() + consent-feature
registration), not a hand-rolled mock.

Mirrors the product-level ``tests/conftest.py`` seed-patch shape
(class-level ``DatabaseModule`` patch + per-fixture consent re-bind).
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

import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)

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
        from app.modules.email_marketing import register
        from app.rate_limit import limiter

        reg = register()
        standard = list(reg.standard_routers)
        app = create_product_app(
            name="Social Wiring (email_marketing test harness)",
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
