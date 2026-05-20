"""
Pytest configuration for Daily Life backend tests.

Mirrors the parallel-worktree venv shadowing fix from
``seed/lib/backend/tests/conftest.py`` — when the host venv carries an
editable-install of ``noctusai_lib`` pointing at a sibling worktree,
that finder shadows our local source tree and product code that imports
from the seed (e.g. ``noctusai_lib.domain.metas`` post-09fa759) fails
with ``ModuleNotFoundError``. Detect + drop the shadow so the local
``seed/lib/backend`` wins.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots: the purge helper drops sibling-worktree
# editable finders (correct behaviour), but the conftest must ALSO ensure
# THIS worktree's own seed source trees are importable via sys.path —
# otherwise `import noctusai_seed` fails with no fallback after the purge.
# Post-axis-swap fan-out (2026-05-20) mirroring ERP-P7's reference fix.
for _p in (_LIB, _FRAMEWORK):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
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

from noctusai_lib.testing import (
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
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Helper lives in seed-lib so all products share one path.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
