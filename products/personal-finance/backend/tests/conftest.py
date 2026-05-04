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

_LIB = _Path(__file__).resolve().parents[4] / "seed" / "lib" / "backend"
if str(_LIB) not in _sys.path:
    _sys.path.insert(0, str(_LIB))


def _pf_purge_shadowing_editable_finders() -> None:
    """Drop pip-editable `_EditableFinder` classes whose MAPPING['noctusai_lib']
    points outside this worktree's seed/lib root.

    The seed-lib conftest checks `getattr(finder, "MAPPING", None)` directly,
    but pip's PEP-660 finder stores MAPPING on the FINDER MODULE (not the
    class). We resolve via `sys.modules[finder.__module__].MAPPING`.
    """
    local_root = str(_LIB.resolve())
    keep: list = []
    for finder in _sys.meta_path:
        # Class-level MAPPING (legacy / hypothetical):
        mapping = getattr(finder, "MAPPING", None)
        if mapping is None:
            # Module-level MAPPING (pip's __editable___pkg_finder.py shape):
            mod_name = getattr(finder, "__module__", None)
            mod = _sys.modules.get(mod_name) if mod_name else None
            mapping = getattr(mod, "MAPPING", None)
        if isinstance(mapping, dict) and "noctusai_lib" in mapping:
            target = str(_Path(mapping["noctusai_lib"]).resolve())
            if not target.startswith(local_root):
                continue
        keep.append(finder)
    _sys.meta_path[:] = keep
    for name in list(_sys.modules):
        if name == "noctusai_lib" or name.startswith("noctusai_lib."):
            del _sys.modules[name]


_pf_purge_shadowing_editable_finders()
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
