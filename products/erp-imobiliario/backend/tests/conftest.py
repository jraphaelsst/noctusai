"""
Pytest configuration and shared fixtures for ERP backend tests.

Mock classes are imported from the shared testing package. This module
re-exports them so existing test files that do
``from tests.conftest import MockSupabaseClient`` continue to work.

After the seed framework migration, patches target DatabaseModule.get_client
and DatabaseModule.get_admin_client instead of app.database.get_supabase_client.

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
)

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
