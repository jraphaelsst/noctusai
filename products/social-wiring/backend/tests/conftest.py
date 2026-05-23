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
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


@pytest.fixture
def settings_override():
    """DI-seam analog for Pydantic-settings singleton overrides.

    `app.config.settings` is a module-level `SocialWiringSettings()` instance
    that production code reads attributes off at request time. Direct
    `monkeypatch.setattr(settings, "X", "Y")` semantically provides a real
    config value (not neutering logic), but trips `check_no_self_monkeypatch`
    because the AST detector cannot distinguish "patching a settings field"
    from "patching a guard function." This fixture is the centralized
    test-time override seam — single call site for the same mutation, with
    automatic restore on teardown. Per KB § PATTERNS/di-test-seam.md the
    fully-correct fix is a production DI seam (`Depends(get_settings)` +
    `app.dependency_overrides`); filed as the follow-up project
    `social-wiring-settings-di-rewrite` so this fixture becomes a thin
    forwarder once the production refactor lands.

    Usage:

        def test_x(client, settings_override):
            settings_override(encryption_key="", youtube_client_id="cid")
            ...

    Multiple calls in one test are additive (later override wins).
    """
    from app.config import settings as _settings
    _saved: dict = {}

    def _apply(**overrides):
        for key, value in overrides.items():
            if key not in _saved:
                _saved[key] = getattr(_settings, key)
            setattr(_settings, key, value)
        return _settings

    yield _apply

    # Restore every touched attribute to its pre-test value.
    for key, value in _saved.items():
        setattr(_settings, key, value)


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
