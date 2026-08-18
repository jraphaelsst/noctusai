"""Tests for the clientes-inactivity threshold tab —
GET/PUT /api/settings/clientes-inactivity (D16, roadmap
lead-card-hub-2026-08). Mirrors `test_settings_meta_app.py`'s shape
(admin-gate + read/write split), NOT that file's `app_config_store` DI
seam — this endpoint persists per-org rows in
`social_wiring.clientes_inactivity_config` (migration `058`) via
`get_scoped_admin_client("social_wiring")`, so both the admin/member
fixtures below patch `get_admin_client` the SAME way
`test_clientes_router.py`'s fixtures do, and every scenario re-uses the
SAME underlying `MockSupabaseClient` for its PUT-then-GET round-trips
(the `get_scoped_admin_client` cache keyed by admin-client object makes
that safe — see `app/dependencies.py`).

**Strict `== 401`, never `in (401, 403)`.** Unlike this file's neighbour
`test_settings_router.py::TestKeysStatusAuth` (pre-existing, permissive —
flagged as `drift-found:` in this dispatch's delivery note, not fixed
here), every auth-boundary assertion in THIS file is the exact code per
`KB § PATTERNS/compliance/auth-boundary-false-green.md`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import SocialWiringSettings

# Bind to the SETTING, never a literal. These assertions exist to prove the
# endpoint reports whatever the platform default IS — not to pin a
# particular number. When the default moved 180 -> 365 on 2026-08-18 the
# literals here went red for no reason other than being literals, which is
# a test failing at its own maintenance rather than at a defect.
PLATFORM_DEFAULT = SocialWiringSettings.model_fields[
    "clientes_inactivity_threshold_days_default"
].default
from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse, bind_consent_module_to_mock

_URL = "/api/settings/clientes-inactivity"


def _mock_client(*, org_role: str | None = None) -> MockSupabaseClient:
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id="test-org-123", org_role=org_role))
    )
    return mock_sb


@pytest.fixture
def admin_client():
    mock_sb = _mock_client(org_role="owner")
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
    mock_sb = _mock_client(org_role=None)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def anon_client():
    """No Authorization header sent — see `test_clientes_router.py`'s
    identical fixture for why the `client`/`admin_client`/`member_client`
    fixtures (which DO send a bearer token) can never produce a strict
    401."""
    mock_sb = _mock_client(org_role="owner")
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        yield TestClient(app)


def _auth_header() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestAuthBoundary:
    def test_get_unauthenticated_is_strictly_401(self, anon_client):
        resp = anon_client.get(_URL)
        assert resp.status_code == 401, resp.text

    def test_put_unauthenticated_is_strictly_401(self, anon_client):
        resp = anon_client.put(_URL, json={"threshold_days": 90})
        assert resp.status_code == 401, resp.text


class TestAdminGate:
    def test_member_role_403_on_write(self, member_client):
        resp = member_client.put(_URL, json={"threshold_days": 90}, headers=_auth_header())
        assert resp.status_code == 403, resp.text

    def test_owner_role_allowed_to_write(self, admin_client):
        resp = admin_client.put(_URL, json={"threshold_days": 90}, headers=_auth_header())
        assert resp.status_code == 200, resp.text

    def test_read_is_not_admin_gated(self, member_client):
        """A member can SEE the org's threshold — only the write is
        admin-gated (mirrors the Meta App tab's read/write split)."""
        resp = member_client.get(_URL, headers=_auth_header())
        assert resp.status_code == 200, resp.text


class TestDefaultAndOverride:
    def test_no_row_reports_the_platform_default(self, admin_client):
        resp = admin_client.get(_URL, headers=_auth_header())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["configured"] is False
        assert body["threshold_days"] == PLATFORM_DEFAULT
        assert body["default_threshold_days"] == PLATFORM_DEFAULT

    def test_a_put_then_a_get_round_trips_the_configured_value(self, admin_client):
        put_resp = admin_client.put(_URL, json={"threshold_days": 45}, headers=_auth_header())
        assert put_resp.status_code == 200, put_resp.text
        assert put_resp.json() == {
            "threshold_days": 45, "configured": True,
            "default_threshold_days": PLATFORM_DEFAULT,
        }

        get_resp = admin_client.get(_URL, headers=_auth_header())
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["threshold_days"] == 45
        assert body["configured"] is True

    def test_zero_is_accepted_and_reported_as_configured(self, admin_client):
        """0 explicitly disables the sweep for this org — a valid write,
        not an error, and distinguishable from 'never configured'
        (which reports `configured: false`, not `threshold_days: 0`)."""
        resp = admin_client.put(_URL, json={"threshold_days": 0}, headers=_auth_header())
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "threshold_days": 0, "configured": True,
            "default_threshold_days": PLATFORM_DEFAULT,
        }

    def test_negative_threshold_is_rejected_at_the_boundary(self, admin_client):
        resp = admin_client.put(_URL, json={"threshold_days": -1}, headers=_auth_header())
        assert resp.status_code == 422, resp.text

    def test_extra_field_rejected(self, admin_client):
        resp = admin_client.put(
            _URL, json={"threshold_days": 30, "sneaky": "x"}, headers=_auth_header()
        )
        assert resp.status_code == 422, resp.text

    def test_re_putting_updates_rather_than_duplicating(self, admin_client):
        admin_client.put(_URL, json={"threshold_days": 30}, headers=_auth_header())
        admin_client.put(_URL, json={"threshold_days": 60}, headers=_auth_header())
        resp = admin_client.get(_URL, headers=_auth_header())
        assert resp.json()["threshold_days"] == 60
