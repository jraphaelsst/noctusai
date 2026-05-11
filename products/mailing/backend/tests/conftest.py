"""
Pytest configuration for Mailing Product backend tests.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_consent_module_to_mock,
)

def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the slowapi limiter between tests.

    slowapi keeps in-memory counters at module scope; without this fixture,
    decorated endpoints that get hit N+ times across the suite would
    surface 429s in unrelated tests. Added by
    `llm-endpoint-rate-limit-rollout-2026-05-11` after the rate-limit
    smoke test triggered cross-test pollution (1 baseline test flipped
    red on the same /api/ai/subjects endpoint).
    """
    from app.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()


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
