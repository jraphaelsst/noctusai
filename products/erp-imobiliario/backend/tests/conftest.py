"""
Pytest configuration and shared fixtures for ERP backend tests.

Mock classes are imported from the shared testing package. This module
re-exports them so existing test files that do
``from tests.conftest import MockSupabaseClient`` continue to work.

After the seed framework migration, patches target DatabaseModule.get_client
and DatabaseModule.get_admin_client instead of app.database.get_supabase_client.

-----------------------------------------------------------------------------
Parallel-worktree venv shadowing (defensive — mirrors seed/lib/backend/tests/conftest.py)
-----------------------------------------------------------------------------
The shared host venv has `noctusai_lib` editable-installed pointing at ONE
worktree's seed/lib/backend path. When a sibling worktree runs tests, the
editable finder shadows the local checkout and tests resolve `noctusai_lib`
to the wrong worktree (potentially missing modules added on this branch).
This conftest detects shadowing finders bound to other worktrees and pops
them before any `from noctusai_lib...` import below executes. Mirrors the
seed-side fix shipped by Batch 1B (`ai-plumbing-seed-absorption`), extended
to product-side tests by `erp-metas-seed-wiring` (Batch 1C). See the project's
bundled proposal §"cross-product follow-up: seed-shadow-purge in product
conftests" for the rationale to mirror this in PF + daily-life conftests.

-----------------------------------------------------------------------------
Schema-validation rationale (mock-supabase-schema-validation Phase 3, 2026-04-24)
-----------------------------------------------------------------------------
MockSupabaseClient is constructed with validate_schema=False. Flipping to True
surfaces ~8 known schema-drift points between migration files and runtime code:
  * erp.ativos: code uses `descricao` (migration has `descricao_seo`); code uses
    `org_id` (not in migration).
  * erp.clientes: code uses `org_id` on insert (not in migration).
  * erp.lancamentos: code uses `contrato_id` (not in migration), `referencia`
    (not in migration).
  * erp.metas: code uses `meta_vgv` (migration has `meta_pretendida` /
    `meta_realizada`).
  * erp.profiles: code uses `avatar_url` (migration has `avatar`), `org_id`
    (not in migration).
  * erp.whatsapp_config: code uses `webhook_secret` (not in migration).

These belong to an `erp-schema-drift-reconciliation` follow-up project, not the
mock-supabase close. Same shape as therapy's schema drift (tracked by
`products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`).
Once reconciled, flip this to `validate_schema=True, schema="erp"`.
"""
import sys
from pathlib import Path
_REPO = Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots: the purge helper drops sibling-worktree
# editable finders (correct behaviour), but the conftest must ALSO ensure
# THIS worktree's own seed source trees are importable via sys.path —
# otherwise `import noctusai_seed` fails with no fallback after the purge.
# The post-axis-swap (2026-05-16) helper already handles each package
# against its own legitimate in-repo root; sys.path is the consumer-side
# half of the same contract.
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


from datetime import date

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


# Dev benchmarks that are misnamed with the `test_` prefix but contain no
# pytest test functions. They invoke the real OpenAI API and are meant to be
# run manually, not discovered during unit-test runs.
collect_ignore = [
    "test_embedding_vs_rules.py",
    "test_mock_matching_local.py",
    "test_mock_matching_large.py",
]


from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Import shared mocks and re-export for backwards compatibility
# ---------------------------------------------------------------------------
from noctusai_lib.testing import (  # noqa: F401 — re-exported
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
    patch_credentials_to_mock,
)
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401

# ---------------------------------------------------------------------------
# ERP-specific defaults
# ---------------------------------------------------------------------------

def _erp_user(**kwargs) -> MockUser:
    """Create a MockUser with ERP defaults (org_id populated)."""
    kwargs.setdefault("org_id", "test-org-123")
    return MockUser(**kwargs)


def _erp_user_response(**kwargs) -> MockUserResponse:
    """Create a MockUserResponse with ERP defaults."""
    return MockUserResponse(user=_erp_user(**kwargs))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user():
    return _erp_user()


@pytest.fixture
def mock_supabase():
    return MockSupabaseClient(validate_schema=False, schema="erp")  # See rationale below


@pytest.fixture
def client():
    """
    Test client with fully mocked Supabase and automatic auth headers.

    Access mock objects via:
        client.mock_supabase   — the MockSupabaseClient instance
        client.mock_log        — the MagicMock patched over log_action
    """
    mock_sb = MockSupabaseClient(validate_schema=False, schema="erp")  # See rationale below
    mock_sb.auth.get_user = MagicMock(return_value=_erp_user_response())
    # ERP routers call rpc("get_data_sp") for São Paulo date; provide a default
    mock_sb.set_rpc_data("get_data_sp", [date.today().isoformat()])
    mock_log = MagicMock()

    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch_credentials_to_mock(mock_sb), \
         patch("app.dependencies.log_action", mock_log):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Helper lives in seed-lib so all products share one path.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        ac = AuthClient(tc, mock_sb)
        # Attach ERP-specific mock_log for tests that need it
        ac._mock_log = mock_log
        yield ac
