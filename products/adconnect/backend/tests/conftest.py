"""
Pytest configuration and shared fixtures for AdConnect backend tests.

AdConnect uses the seed framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.
"""
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
    # AdConnect's product tables live in `adconnect.<table>` — bind the mock
    # to that schema so column-validation lookups resolve against the
    # canonical migrations/001_adconnect.sql tables.
    mock_sb = MockSupabaseClient(schema="adconnect")
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    # Two patch layers:
    #   1. Framework-level (DatabaseModule classmethods) — covers any code
    #      path that resolves the client lazily.
    #   2. Module-level binding patches — `app.database` re-exports
    #      `_db.get_admin_client` etc as module attributes at import time.
    #      The router modules import the NAME (`from ..database import
    #      get_admin_client`) — to redirect those to the mock we have to
    #      patch the names on app.database itself AND on each router that
    #      already bound them locally.
    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb), \
         patch("app.database.get_supabase_client", lambda: mock_sb), \
         patch("app.database.get_core_client", lambda: mock_sb), \
         patch("app.database.get_admin_client", lambda: mock_sb):

        # Importing main triggers the router-module imports, each of which
        # binds `get_admin_client = app.database.get_admin_client`. We
        # override those bindings AFTER import.
        from app.main import app
        from app.routers import products as _products_router
        from app.routers import distributors as _distributors_router

        with patch.object(_products_router, "get_admin_client", lambda: mock_sb), \
             patch.object(_distributors_router, "get_admin_client", lambda: mock_sb):

            # Per-fixture re-bind of the seed's consent module to THIS test's
            # mock_sb. Idempotent — safe even though AdConnect doesn't register
            # consent features yet. See KB § PATTERNS/testing.md § Consent-guard
            # product conftest pattern.
            bind_consent_module_to_mock(mock_sb)

            tc = TestClient(app)
            yield AuthClient(tc, mock_sb)
