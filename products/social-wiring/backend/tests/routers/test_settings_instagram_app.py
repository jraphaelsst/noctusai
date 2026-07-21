"""Tests for the Instagram App config tab — PUT/GET
/api/settings/instagram-app* (byte-for-byte mirror of
``test_settings_meta_app.py``, keyed on the Instagram Business Login app
credential pair instead of the Meta/Facebook-Login one).

Coverage:
  - Admin gate: owner/admin roles can write; a plain member gets 403.
  - Secret is write-only: never echoed in the PUT/GET response body.
  - Partial update: app_id-only / app_secret-only PUT leaves the other
    half untouched (round-trips through the SAME injected store — the
    ``get_app_config_store_dep`` DI seam, per KB § PATTERNS/backend/
    di-test-seam.md, no monkeypatch of our own code).
  - Blank/omitted app_secret never overwrites a previously-set secret.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.security.app_config import FakeAppConfigStore
from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse


def _make_client(*, org_role: str | None = None):
    """Local client fixture builder — mirrors ``conftest.client`` but lets
    each test pick the caller's ``org_role`` (conftest's shared fixture
    hardcodes a bare MockUser with no role, so the admin-gate tests need
    their own)."""
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(
            MockUser(org_id="test-org-123", org_role=org_role)
        )
    )
    return mock_sb


@pytest.fixture
def admin_client():
    from noctusai_lib.testing import bind_consent_module_to_mock

    mock_sb = _make_client(org_role="owner")
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def member_client():
    from noctusai_lib.testing import bind_consent_module_to_mock

    mock_sb = _make_client(org_role=None)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app, raise_server_exceptions=True)


def _auth_header():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def fake_store_override():
    """Override BOTH the write (raising) and read (optional) app-config
    store DI seams with the SAME FakeAppConfigStore instance, so a PUT
    then a GET in one test observe the same underlying rows. Torn down
    automatically."""
    from app.main import app
    from app.routers.settings_router import (
        get_app_config_store_dep,
        get_app_config_store_optional_dep,
    )

    store = FakeAppConfigStore()
    prev_dep = app.dependency_overrides.get(get_app_config_store_dep)
    prev_opt = app.dependency_overrides.get(get_app_config_store_optional_dep)
    app.dependency_overrides[get_app_config_store_dep] = lambda: store
    app.dependency_overrides[get_app_config_store_optional_dep] = lambda: store
    yield store
    if prev_dep is None:
        app.dependency_overrides.pop(get_app_config_store_dep, None)
    else:
        app.dependency_overrides[get_app_config_store_dep] = prev_dep
    if prev_opt is None:
        app.dependency_overrides.pop(get_app_config_store_optional_dep, None)
    else:
        app.dependency_overrides[get_app_config_store_optional_dep] = prev_opt


class TestAdminGate:
    def test_member_role_403(self, member_client, fake_store_override):
        resp = member_client.put(
            "/api/settings/instagram-app",
            json={"app_id": "new-app-id"},
            headers=_auth_header(),
        )
        assert resp.status_code == 403, resp.text

    def test_owner_role_allowed(self, admin_client, fake_store_override):
        resp = admin_client.put(
            "/api/settings/instagram-app",
            json={"app_id": "new-app-id"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text


class TestSecretNeverEchoed:
    def test_put_response_never_contains_the_secret(
        self, admin_client, fake_store_override
    ):
        resp = admin_client.put(
            "/api/settings/instagram-app",
            json={"app_id": "app-123", "app_secret": "SUPER-SECRET-VALUE"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        assert "SUPER-SECRET-VALUE" not in resp.text
        body = resp.json()
        assert body["app_id_configured"] is True
        assert body["app_secret_configured"] is True
        assert "app_secret" not in body

    def test_status_response_never_contains_the_secret(
        self, admin_client, fake_store_override
    ):
        fake_store_override.put("instagram_app_secret", "SUPER-SECRET-VALUE")
        resp = admin_client.get(
            "/api/settings/instagram-app/status", headers=_auth_header()
        )
        assert resp.status_code == 200, resp.text
        assert "SUPER-SECRET-VALUE" not in resp.text
        assert resp.json()["app_secret_configured"] is True

    def test_app_id_masked_shows_only_last_4_chars(
        self, admin_client, fake_store_override
    ):
        resp = admin_client.put(
            "/api/settings/instagram-app",
            json={"app_id": "1234567890"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["app_id_masked"] == "...7890"
        assert "1234567890" not in resp.text


class TestPartialUpdate:
    def test_app_id_only_leaves_secret_untouched(
        self, admin_client, fake_store_override
    ):
        fake_store_override.put("instagram_app_secret", "ORIGINAL-SECRET")
        resp = admin_client.put(
            "/api/settings/instagram-app",
            json={"app_id": "only-id-update"},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        assert fake_store_override.get("instagram_app_id") == "only-id-update"
        assert fake_store_override.get("instagram_app_secret") == "ORIGINAL-SECRET"

    def test_blank_secret_never_overwrites(self, admin_client, fake_store_override):
        fake_store_override.put("instagram_app_secret", "ORIGINAL-SECRET")
        resp = admin_client.put(
            "/api/settings/instagram-app",
            json={"app_id": "x", "app_secret": ""},
            headers=_auth_header(),
        )
        assert resp.status_code == 200, resp.text
        assert fake_store_override.get("instagram_app_secret") == "ORIGINAL-SECRET"

    def test_no_fields_400(self, admin_client, fake_store_override):
        resp = admin_client.put(
            "/api/settings/instagram-app", json={}, headers=_auth_header()
        )
        assert resp.status_code == 400


class TestStatusReadOnly:
    def test_status_reflects_db_configured_values(
        self, admin_client, fake_store_override, override_settings
    ):
        # Neutralize the ambient env half of the resolve through the
        # production DI seam (`Depends(get_settings)`), so the assertion
        # below is about the DB store ONLY. Without this the endpoint's
        # legitimate env-fallback reads the developer's real root `.env`
        # and `app_secret_configured` comes back True — the test was
        # green on a clean checkout and RED on a machine with real
        # credentials. Per KB § PATTERNS/di-test-seam.md (Class-A).
        override_settings(instagram_app_id="", instagram_app_secret="")

        fake_store_override.put("instagram_app_id", "db-app-id")
        resp = admin_client.get(
            "/api/settings/instagram-app/status", headers=_auth_header()
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["app_id_configured"] is True
        assert data["app_secret_configured"] is False

    def test_status_reachable_by_non_admin(self, member_client, fake_store_override):
        """The READ status endpoint is not admin-gated — only the write."""
        resp = member_client.get(
            "/api/settings/instagram-app/status", headers=_auth_header()
        )
        assert resp.status_code == 200, resp.text
