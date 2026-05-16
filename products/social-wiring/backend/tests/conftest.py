"""
Pytest configuration and shared fixtures for Social Wiring backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Add BOTH seed source roots to sys.path FIRST. `purge_shadowing_editable_finders`
# (called below) drops the `noctusai_seed` editable finder too (its mapping
# points at seed/framework/backend, outside `_LIB`), so without
# `_FRAMEWORK` on the path `import noctusai_seed` fails at collection. The
# `_LIB`-only shim the W0.3 scaffold/reference carried predates the
# separate-finders layout — this restores framework resolution by path.
# (Cross-product test-infra follow-up: fold `noctusai_seed` path-restore
# into the shared shim — out of this product's scope.)
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
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_lib.testing import (  # noqa: F401 — re-exported for test imports
    MockSupabaseResponse,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_consent_module_to_mock,
)


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    # Canonical seed-level patch (mirrors products/personal-finance
    # conftest). Class-level patch on DatabaseModule covers every
    # DatabaseModule instance — both app.database._db and the separate
    # instance dependencies.py builds — so we never resolve
    # `app.database._db` at collection time (which broke the older
    # product-level-patch shape the W0.3 scaffold/reference carried).
    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Idempotent — safe even if no consent features registered.
        # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
