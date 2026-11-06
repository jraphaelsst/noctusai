"""Access-tier burn-down (OWASP API1 BOLA / API2 broken authentication / API5 BFLA) for the routes that
used to be anonymous or accepted an unsigned OAuth ``state``.

Every assertion is a STRICT status (``== 401`` / ``== 403`` / ``== 400``): a 404/422 here would mean the route is
absent or validation ran before auth -- a false green (``KB § PATTERNS/compliance/auth-boundary-false-green.md``).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import MockSupabaseClient, bind_consent_module_to_mock


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app)
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/chat/message"),
        ("POST", "/api/chat/upload-file"),
        ("GET", "/api/chat/history/web:abc"),
        ("POST", "/api/chat/reset/web:abc"),
        ("GET", "/api/integrations/providers"),
        ("GET", "/api/meta/ads/sync/any-job"),
    ],
)
def test_formerly_anonymous_routes_require_a_session(client, method, path):
    assert client.request(method, path).status_code == 401


def test_youtube_settings_callback_refuses_an_unsigned_state(client):
    """``/api/youtube/oauth/callback`` took the org straight from ``state`` -- a forged state is a 400 now."""
    resp = client.get(
        "/api/youtube/oauth/callback?code=c&state=00000000-0000-4000-8000-0000000000bb:nonce",
        follow_redirects=False,
    )
    assert resp.status_code == 400
