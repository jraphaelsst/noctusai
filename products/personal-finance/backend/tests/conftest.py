"""
Pytest configuration for Personal Finance backend tests.
"""
# ── Worktree-aware seed-lib shadow purge ─────────────────────────────────
# Mirrors `seed/lib/backend/tests/conftest.py § _purge_shadowing_editable_finders`
# (Engineer 2 of Batch 1B fix). When a parallel worktree owns the editable
# install of `noctusai_lib`, that finder shadows our worktree's seed/lib
# source tree — so `from noctusai_lib.domain.metas import ...` resolves to
# the wrong (potentially older) source. We add THIS worktree's seed/lib to
# sys.path FIRST and drop any meta_path finder whose `noctusai_lib` mapping
# points outside this worktree.
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots: the purge helper drops sibling-worktree
# editable finders (correct behaviour), but the conftest must ALSO ensure
# THIS worktree's own seed source trees are importable via sys.path —
# otherwise `import noctusai_seed` fails with no fallback after the purge.
# Post-axis-swap fan-out (2026-05-20) mirroring ERP-P7's reference fix.
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
# ─────────────────────────────────────────────────────────────────────────

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_lib.testing import (  # noqa: F401
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

    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's mock_sb.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
