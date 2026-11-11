"""
Pytest configuration and shared fixtures for orbity backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.

Parallel-worktree venv shadowing: same purge-and-reinsert pattern as erp
(mirrors seed/lib/backend/tests/conftest.py). The editable finder for
noctusai_lib can point at a sibling worktree; this conftest pops those
finders and inserts the current repo root so tests resolve against THIS
checkout's seed source.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]  # .../noctusai
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"

for _p in (_LIB, _FRAMEWORK):
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

import os

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


# The suite is a local/test process: say so explicitly (the webhook accepts an unsigned call ONLY in an explicit local env).
os.environ.setdefault("APP_ENV", "test")


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


@pytest.fixture(autouse=True)
def _legacy_enabled_line_policy():
    """Tests drive the sender through the Fake WAHA, so they declare a send-enabled process default through the PUBLIC
    registry. Prod declares NONE for orbity (WhatsApp OFF, `NOC-REMEDIATE[orbity-waha-own-instance]`), so the seed fails
    closed there; the fail-closed behaviour itself is covered in the seed lib suite."""
    from noctusai_lib.integrations.whatsapp import LinePolicy, clear_line_policies, register_line_policy

    clear_line_policies()
    register_line_policy("*", LinePolicy("enabled", True, True, True))
    yield
    clear_line_policies()


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient(schema="orbity")
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Idempotent — safe even if no consent features registered.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
