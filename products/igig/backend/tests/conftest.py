"""
Pytest configuration and shared fixtures for IgIg backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots — this file previously added only `_LIB`,
# which left `noctusai_seed` unresolvable in a worktree once
# `purge_shadowing_editable_finders` drops the venv's editable finder
# pointing at a sibling checkout (every OTHER product's conftest.py
# already does this; found + fixed while verifying
# `seed-trusted-org-resolution`, 2026-07-14 — mirrors ERP-P7's reference
# fix, see `products/daily-life/backend/tests/conftest.py`).
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
def client():
    mock_sb = MockSupabaseClient()
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
        # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)


# ── PostgREST-backed surfaces (pipelines + card hubs, decision D-A1) ────────
class IgigMockClient(MockSupabaseClient):
    """`MockSupabaseClient` bound to schema `igig`, plus the ONE database
    function the esteira calls.

    `igig.incrementar_refacoes()` (migration 017) is an atomic
    `UPDATE … SET refacoes = refacoes + 1 RETURNING refacoes`. The seed mock
    answers every rpc with canned data, so a test could not tell whether the
    increment happened; this double performs the same UPDATE on the mock's own
    table and records the call. It stands in for the database, not for any
    igig code path.
    """

    def __init__(self) -> None:
        super().__init__(schema="igig")
        self.rpc_calls: list[tuple[str, dict]] = []

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, dict(params or {})))
        if name == "incrementar_refacoes":
            for row in self.table("tarefa")._data:
                if row.get("id") == params["p_tarefa_id"] and row.get("org_id") == params["p_org_id"]:
                    row["refacoes"] = int(row.get("refacoes") or 0) + 1
                    return MockSelectBuilder([{"refacoes": row["refacoes"]}])
            return MockSelectBuilder([])
        return super().rpc(name, params)


@pytest.fixture
def igig_db() -> IgigMockClient:
    return IgigMockClient()


@pytest.fixture
def core_db() -> MockSupabaseClient:
    return MockSupabaseClient()


@pytest.fixture
def crm_api(client, igig_db, core_db):
    """The app with EVERY data dependency on one shared `igig` mock.

    The pipeline/card-hub code reads through PostgREST (`get_db`,
    `get_admin_db`) and the older routes through the RecordStore
    (`get_repositorios*`). Pointing both at the SAME mock — the repositories
    via the real `SupabaseRecordStore` adapter production uses — means a row
    one seam writes is a row the other reads, as in production.
    """
    from noctusai_lib.integrations.persistence import SupabaseRecordStore

    from app.main import app
    from app.pipelines import get_admin_db, get_core_db, get_db
    from app.repositories import Repositorios
    from app.store import get_repositorios, get_repositorios_admin

    repos = Repositorios(SupabaseRecordStore(igig_db))
    overrides = {
        get_db: lambda: igig_db,
        get_admin_db: lambda: igig_db,
        get_core_db: lambda: core_db,
        get_repositorios: lambda: repos,
        get_repositorios_admin: lambda: repos,
    }
    app.dependency_overrides.update(overrides)
    yield client
    for dep in overrides:
        app.dependency_overrides.pop(dep, None)
