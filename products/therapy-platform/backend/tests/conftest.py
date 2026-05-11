"""
Pytest fixtures for the Therapy Platform backend.

Uses shared mock infrastructure from noctusai_lib.testing. Re-exports
all shared classes for backwards compatibility (tests import from conftest).

Key difference from ERP/PF: no org_id. Instead, users have roles
(platform_admin, clinic_admin, therapist, patient) and optional clinic_id.
"""
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

# Note: `app.main` is auto-imported at session start by
# `noctusai_lib.testing.pytest_plugin` (registered via the `pytest11`
# entry point in seed-lib's pyproject.toml). That triggers
# `create_product_app(consent_features=...)`, which loads the consent
# catalog for unit tests that import services directly. No per-product
# bootstrap line needed here.

# Re-export all shared classes so existing test imports
# (e.g. `from tests.conftest import MockSupabaseClient`) keep working.
__all__ = [
    "MockSupabaseResponse",
    "MockSelectBuilder",
    "MockFilterBuilder",
    "MockQueryBuilder",
    "MockRequestBuilder",
    "MockSupabaseClient",
    "MockUser",
    "MockUserResponse",
    "AuthClient",
]


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


def _make_client_context(role="therapist", clinic_id=None):
    """Create an AuthClient with mocked auth for a given role.

    Returns a context manager that keeps patches alive for the duration
    of the test.
    """
    # `validate_schema` intentionally False — therapy has ~20 known
    # column-level schema-drift points tracked by
    # `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`.
    # Flipping column validation on surfaces all of them (appointment_id on
    # session_audio_segments / session_interruptions; patient_id/therapist_id
    # on session_records; user_id on therapist_settings; rating vs star_rating
    # on reviews; therapist_id on whatsapp_messages; etc.). Those belong in the
    # reconciliation project, not in the mock-supabase close. Once that project
    # lands, flip this to validate_schema=True.
    #
    # `strict_unknown_tables=True` is **orthogonal** to validate_schema (added
    # 2026-05-11 by `therapy-platform-drift-sweep`). It raises
    # `MockUnknownTableError` if a test exercises a table absent from the
    # migration-derived schema cache — guards against regressing the 11
    # phantom-table references the sweep eliminated. Works regardless of
    # `validate_schema`. See `noctusai_lib.testing.mocks.MockRequestBuilder.
    # _check_table_known`.
    mock_sb = MockSupabaseClient(
        validate_schema=False,
        schema="therapy",
        strict_unknown_tables=True,
    )
    mock_user = MockUser(role=role, clinic_id=clinic_id)
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(mock_user))

    patcher1 = patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb)
    patcher2 = patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb)
    patcher3 = patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb)
    patcher1.start()
    patcher2.start()
    patcher3.start()

    from app.main import app
    # Per-fixture re-bind of the seed's consent module to THIS test's mock_sb.
    # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
    bind_consent_module_to_mock(mock_sb)
    tc = TestClient(app)
    client = AuthClient(tc, mock_sb)
    return client, (patcher1, patcher2, patcher3)


@pytest.fixture
def client():
    """Default test client — therapist role."""
    c, patchers = _make_client_context(role="therapist")
    yield c
    for p in patchers:
        p.stop()


@pytest.fixture
def patient_client():
    """Test client — patient role."""
    c, patchers = _make_client_context(role="patient")
    yield c
    for p in patchers:
        p.stop()


@pytest.fixture
def clinic_admin_client():
    """Test client — clinic admin role with clinic_id."""
    c, patchers = _make_client_context(role="clinic_admin", clinic_id="test-clinic-123")
    yield c
    for p in patchers:
        p.stop()


@pytest.fixture
def admin_client():
    """Test client — platform admin role."""
    c, patchers = _make_client_context(role="platform_admin")
    yield c
    for p in patchers:
        p.stop()
