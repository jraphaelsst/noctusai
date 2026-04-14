"""
Pytest fixtures for the Therapy Platform backend.

Uses shared mock infrastructure from noctusai_shared.testing. Re-exports
all shared classes for backwards compatibility (tests import from conftest).

Key difference from ERP/PF: no org_id. Instead, users have roles
(platform_admin, clinic_admin, therapist, patient) and optional clinic_id.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_shared.testing import (
    MockSupabaseResponse,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
)

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_client_context(role="therapist", clinic_id=None):
    """Create an AuthClient with mocked auth for a given role.

    Returns a context manager that keeps patches alive for the duration
    of the test.
    """
    mock_sb = MockSupabaseClient()
    mock_user = MockUser(role=role, clinic_id=clinic_id)
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(mock_user))

    patcher1 = patch("app.dependencies.get_supabase_client", return_value=mock_sb)
    patcher2 = patch("app.database.get_supabase_client", return_value=mock_sb)
    patcher1.start()
    patcher2.start()

    from app.main import app
    tc = TestClient(app)
    client = AuthClient(tc, mock_sb)
    return client, (patcher1, patcher2)


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
