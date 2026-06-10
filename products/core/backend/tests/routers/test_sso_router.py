"""
Tests for SSO Router.

POST  /api/sso/token           — Generate SSO token
POST  /api/sso/validate        — Validate SSO token
GET   /api/sso/launch/{slug}   — Redirect to product with SSO token
POST  /api/sso/session         — Exchange SSO token for Supabase session
"""
import time

import jwt
import pytest
from unittest.mock import MagicMock, patch

from app.config import settings
from noctusai_lib.api.auth import SSO_AUDIENCE, SSO_ISSUER


# ---------------------------------------------------------------------------
# POST /api/sso/token
# ---------------------------------------------------------------------------

class TestGenerateSSOToken:
    def test_generate_sso_token_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "role": "user",
            "email": "test@example.com",
        })
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp-imobiliario"})
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active",
            "org_id": "org-1", "product_id": "prod-1",
        }])

        with patch("app.routers.sso.create_sso_token", return_value="mocked-sso-token"):
            resp = client.post("/api/sso/token", json={
                "product_slug": "erp-imobiliario",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["sso_token"] == "mocked-sso-token"
            assert data["product_slug"] == "erp-imobiliario"

    def test_generate_sso_token_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.post("/api/sso/token", json={
            "product_slug": "erp-imobiliario",
        })
        assert resp.status_code == 404

    def test_generate_sso_token_product_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "role": "user",
        })
        mock_sb.set_table_data("products", None)

        resp = client.post("/api/sso/token", json={
            "product_slug": "nonexistent",
        })
        assert resp.status_code == 404

    def test_generate_sso_token_no_license(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "role": "user",
        })
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp"})
        mock_sb.set_table_data("licenses", [])

        resp = client.post("/api/sso/token", json={
            "product_slug": "erp",
        })
        assert resp.status_code == 403

    def test_generate_sso_token_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/sso/token", json={
            "product_slug": "erp",
        })
        assert resp.status_code == 401

    def test_generate_sso_token_missing_slug(self, client):
        resp = client.post("/api/sso/token", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/sso/validate
# ---------------------------------------------------------------------------

class TestValidateSSOToken:
    def test_validate_sso_token_success(self, client):
        mock_payload = {
            "sub": "user-123",
            "org_id": "org-1",
            "product": "erp",
            "email": "test@example.com",
            "role": "user",
            "type": "sso",
        }

        with patch("app.routers.sso.verify_sso_token", return_value=mock_payload):
            resp = client.post("/api/sso/validate", json={
                "token": "valid-sso-token",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True
            assert data["user_id"] == "user-123"
            assert data["org_id"] == "org-1"
            assert data["product"] == "erp"

    def test_validate_sso_token_expired(self, client):
        from fastapi import HTTPException

        def _mock_verify(token):
            raise HTTPException(status_code=401, detail="Token SSO expirado")

        with patch("app.routers.sso.verify_sso_token", side_effect=_mock_verify):
            resp = client.post("/api/sso/validate", json={
                "token": "expired-token",
            })
            assert resp.status_code == 401

    def test_validate_sso_token_invalid(self, client):
        from fastapi import HTTPException

        def _mock_verify(token):
            raise HTTPException(status_code=401, detail="Token SSO invalido")

        with patch("app.routers.sso.verify_sso_token", side_effect=_mock_verify):
            resp = client.post("/api/sso/validate", json={
                "token": "bad-token",
            })
            assert resp.status_code == 401

    def test_validate_sso_token_missing_token(self, client):
        resp = client.post("/api/sso/validate", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/sso/launch/{product_slug}
# ---------------------------------------------------------------------------

class TestLaunchProduct:
    def test_launch_product_redirects(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "role": "user",
        })
        mock_sb.set_table_data("products", {
            "id": "prod-1",
            "slug": "erp",
            "url_base": "http://localhost:8080",
        })
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active",
            "org_id": "org-1", "product_id": "prod-1",
        }])

        with patch("app.routers.sso.create_sso_token", return_value="redirect-token"):
            resp = client.get("/api/sso/launch/erp", follow_redirects=False)
            assert resp.status_code == 302
            assert "token=redirect-token" in resp.headers["location"]

    def test_launch_product_no_license(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"id": "test-user-123", "org_id": "org-1", "role": "user"})
        mock_sb.set_table_data("products", {
            "id": "prod-1",
            "slug": "erp",
            "url_base": "http://localhost:8080",
        })
        mock_sb.set_table_data("licenses", [])

        resp = client.get("/api/sso/launch/erp")
        assert resp.status_code == 403

    def test_launch_product_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1", "role": "user"})
        mock_sb.set_table_data("products", None)

        resp = client.get("/api/sso/launch/nonexistent")
        assert resp.status_code == 404

    def test_launch_product_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/sso/launch/erp")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/sso/session — Exchange SSO token for Supabase session
# ---------------------------------------------------------------------------

def _make_sso_token(
    email="user@test.com", org_id="org-123", expired=False, token_type="sso",
    role="user", org_role="member", product="therapy-platform",
):
    """Create a valid SSO JWT token for testing.

    Mirrors the canonical `create_sso_token` contract in
    `noctusai_lib.api.auth`: the hardened `verify_sso_token` REQUIRES
    `iss`/`aud`/`iat`/`exp`/`type` and validates issuer/audience, so a token
    missing those claims is rejected with 401. Sign with the dedicated SSO
    secret when configured, else `jwt_secret` (mirrors `_sso_secret`).
    """
    now = int(time.time())
    payload = {
        "sub": "user-uid-123",
        "email": email,
        "org_id": org_id,
        "role": role,
        "org_role": org_role,
        "product": product,
        "type": token_type,
        "iss": SSO_ISSUER,
        "aud": SSO_AUDIENCE,
        "iat": now,
        "exp": (now - 600) if expired else (now + 300),
    }
    secret = (getattr(settings, "sso_jwt_secret", "") or "").strip() or settings.jwt_secret
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def _mock_generate_link(email_otp="123456"):
    """Create a mock response for supabase_admin.auth.admin.generate_link."""
    resp = MagicMock()
    resp.properties.email_otp = email_otp
    return resp


def _mock_verify_otp(user_id="user-uid-123", email="user@test.com"):
    """Create a mock response for supabase_admin.auth.verify_otp."""
    resp = MagicMock()
    resp.session.access_token = "sb-access-token"
    resp.session.refresh_token = "sb-refresh-token"
    resp.user.id = user_id
    return resp


def _get_error_message(resp):
    """Extract error message from standardized error response."""
    data = resp.json()
    if "error" in data:
        return data["error"]["message"]
    return data.get("detail", "")


@pytest.fixture
def sso_session_client(client):
    """Client with mocked supabase_admin auth methods for SSO session tests."""
    mock_sb = client.mock_supabase
    mock_sb.auth.admin.generate_link.return_value = _mock_generate_link()
    mock_sb.auth.verify_otp.return_value = _mock_verify_otp()

    from app.routers.sso import _session_cache
    _session_cache.clear()

    yield client, mock_sb

    _session_cache.clear()


class TestSSOSessionSuccess:
    def test_successful_sso_session_flow(self, sso_session_client):
        client, mock_admin = sso_session_client
        token = _make_sso_token()

        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "sb-access-token"
        assert data["refresh_token"] == "sb-refresh-token"
        assert data["user_id"] == "user-uid-123"
        assert data["email"] == "user@test.com"

    def test_generate_link_called_with_correct_email(self, sso_session_client):
        client, mock_admin = sso_session_client
        token = _make_sso_token(email="specific@example.com")

        client.post("/api/sso/session", json={"token": token})

        mock_admin.auth.admin.generate_link.assert_called_once_with({
            "type": "magiclink",
            "email": "specific@example.com",
        })


class TestSSOSessionCache:
    def test_second_call_uses_cache(self, sso_session_client):
        """Second call within 55s should NOT call generate_link again."""
        client, mock_admin = sso_session_client
        token = _make_sso_token()

        resp1 = client.post("/api/sso/session", json={"token": token})
        assert resp1.status_code == 200

        resp2 = client.post("/api/sso/session", json={"token": token})
        assert resp2.status_code == 200
        assert resp2.json() == resp1.json()

        assert mock_admin.auth.admin.generate_link.call_count == 1

    def test_cache_expires_after_ttl(self, sso_session_client):
        """After cache TTL, a new Supabase call is made."""
        client, mock_admin = sso_session_client
        token = _make_sso_token()

        client.post("/api/sso/session", json={"token": token})
        assert mock_admin.auth.admin.generate_link.call_count == 1

        from app.routers.sso import _session_cache
        _session_cache._store.clear()

        client.post("/api/sso/session", json={"token": token})
        assert mock_admin.auth.admin.generate_link.call_count == 2

    def test_different_emails_cached_separately(self, sso_session_client):
        """Cache is per-email — different emails get separate entries."""
        client, mock_admin = sso_session_client

        token_a = _make_sso_token(email="a@test.com")
        token_b = _make_sso_token(email="b@test.com")

        client.post("/api/sso/session", json={"token": token_a})
        client.post("/api/sso/session", json={"token": token_b})

        assert mock_admin.auth.admin.generate_link.call_count == 2


class TestSSOSessionTokenValidation:
    def test_expired_token(self, sso_session_client):
        client, _ = sso_session_client
        token = _make_sso_token(expired=True)

        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 401
        assert "expirado" in _get_error_message(resp).lower()

    def test_invalid_token(self, sso_session_client):
        client, _ = sso_session_client

        resp = client.post("/api/sso/session", json={"token": "not-a-jwt"})

        assert resp.status_code == 401
        msg = _get_error_message(resp).lower()
        assert "inválido" in msg or "invalido" in msg

    def test_non_sso_token_type(self, sso_session_client):
        client, _ = sso_session_client
        token = _make_sso_token(token_type="access")

        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 401
        assert "sso" in _get_error_message(resp).lower()

    def test_token_without_email(self, sso_session_client):
        client, _ = sso_session_client
        # Otherwise-valid SSO token (passes verify_sso_token) but missing email,
        # so the router reaches its 400 "sem email" branch rather than 401.
        payload = {
            "sub": "uid", "type": "sso", "iss": SSO_ISSUER, "aud": SSO_AUDIENCE,
            "iat": int(time.time()), "exp": int(time.time()) + 300,
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 400
        assert "email" in _get_error_message(resp).lower()

    def test_missing_token_body(self, sso_session_client):
        client, _ = sso_session_client

        resp = client.post("/api/sso/session", json={})

        assert resp.status_code == 422


class TestSSORateLimitDetection:
    def test_rate_limit_returns_429_with_retry_after(self, sso_session_client):
        """When Supabase rate limits, return 429 with Retry-After header."""
        client, mock_admin = sso_session_client
        mock_admin.auth.admin.generate_link.side_effect = Exception(
            "For security purposes, you can only request this once every 60 seconds"
        )

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "60"
        assert "rate limit" in resp.json()["detail"].lower()

    def test_rate_limit_with_cached_session_returns_cached(self, sso_session_client):
        """If rate limited but cache exists, return cached session."""
        client, mock_admin = sso_session_client
        token = _make_sso_token()

        resp1 = client.post("/api/sso/session", json={"token": token})
        assert resp1.status_code == 200

        resp2 = client.post("/api/sso/session", json={"token": token})
        assert resp2.status_code == 200
        assert resp2.json() == resp1.json()

    def test_rate_limit_429_in_error_message(self, sso_session_client):
        """Error messages containing '429' should trigger rate limit handling."""
        client, mock_admin = sso_session_client
        mock_admin.auth.admin.generate_link.side_effect = Exception("AuthApiError: 429 Too Many Requests")

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 429

    def test_user_not_allowed_treated_as_rate_limit(self, sso_session_client):
        """Supabase returns 'User not allowed' on rapid magiclink calls for same email."""
        client, mock_admin = sso_session_client
        mock_admin.auth.admin.generate_link.side_effect = Exception("AuthApiError: User not allowed")

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 429


class TestSSOSessionSupabaseAdminNull:
    def test_returns_500_when_supabase_admin_is_none(self, client):
        """When supabase_admin is None, return 500."""
        from app.routers.sso import _session_cache
        _session_cache.clear()

        with patch("app.routers.sso.supabase_admin", None):
            token = _make_sso_token()
            resp = client.post("/api/sso/session", json={"token": token})

            assert resp.status_code == 500
            assert "incompleta" in _get_error_message(resp).lower()


class TestSSOSessionErrors:
    def test_generate_link_no_otp(self, sso_session_client):
        """When generate_link doesn't return email_otp, return 500."""
        client, mock_admin = sso_session_client
        mock_resp = MagicMock()
        mock_resp.properties.email_otp = None
        mock_admin.auth.admin.generate_link.return_value = mock_resp

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 500

    def test_verify_otp_no_session(self, sso_session_client):
        """When verify_otp doesn't return a session, return 500."""
        client, mock_admin = sso_session_client
        mock_resp = MagicMock()
        mock_resp.session = None
        mock_admin.auth.verify_otp.return_value = mock_resp

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 500

    def test_unexpected_exception_returns_500(self, sso_session_client):
        """Unexpected errors return 500 with exception type."""
        client, mock_admin = sso_session_client
        mock_admin.auth.admin.generate_link.side_effect = ConnectionError("Connection refused")

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 500
        msg = _get_error_message(resp)
        assert "ConnectionError" in msg


# ---------------------------------------------------------------------------
# SSO token includes org_role
# ---------------------------------------------------------------------------


class TestSSOTokenOrgRole:
    """Verify that the SSO token generation includes org_role from noctus_users."""

    def test_token_includes_org_role(self, client):
        """Token payload should contain org_role from user profile."""
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "role": "user",
            "org_role": "owner",
            "email": "test@example.com",
        })
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp"})
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active", "fim": None,
            "org_id": "org-1", "product_id": "prod-1",
        }])

        resp = client.post("/api/sso/token", json={"product_slug": "erp"})
        assert resp.status_code == 200

        sso_token = resp.json()["sso_token"]
        payload = jwt.decode(
            sso_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            audience=SSO_AUDIENCE, issuer=SSO_ISSUER,
        )
        assert payload["org_role"] == "owner"
        assert payload["role"] == "user"

    def test_token_defaults_org_role_to_member(self, client):
        """When org_role is missing from profile, default to 'member'."""
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123",
            "org_id": "org-1",
            "role": "user",
            # org_role intentionally missing
        })
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp"})
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active", "fim": None,
            "org_id": "org-1", "product_id": "prod-1",
        }])

        resp = client.post("/api/sso/token", json={"product_slug": "erp"})
        assert resp.status_code == 200

        sso_token = resp.json()["sso_token"]
        payload = jwt.decode(
            sso_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            audience=SSO_AUDIENCE, issuer=SSO_ISSUER,
        )
        assert payload["org_role"] == "member"


class TestSSOSessionMetadataSync:
    """Verify that /api/sso/session syncs noctus_role and org_role into user_metadata."""

    def test_syncs_metadata_on_session(self, sso_session_client):
        """Session creation should update user_metadata with role info."""
        client, mock_admin = sso_session_client
        token = _make_sso_token(role="admin", org_role="owner")

        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        # Verify update_user_by_id was called with the right metadata
        mock_admin.auth.admin.update_user_by_id.assert_called_once_with(
            "user-uid-123",
            {"user_metadata": {
                "noctus_role": "admin",
                "org_role": "owner",
                "org_id": "org-123",
            }},
        )

    def test_syncs_member_role(self, sso_session_client):
        """Regular users get their org_role synced too."""
        client, mock_admin = sso_session_client
        token = _make_sso_token(role="user", org_role="member")

        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        mock_admin.auth.admin.update_user_by_id.assert_called_once_with(
            "user-uid-123",
            {"user_metadata": {
                "noctus_role": "user",
                "org_role": "member",
                "org_id": "org-123",
            }},
        )

    def test_metadata_sync_failure_does_not_block_session(self, sso_session_client):
        """If metadata update fails, session should still be created."""
        client, mock_admin = sso_session_client
        mock_admin.auth.admin.update_user_by_id.side_effect = Exception("update failed")

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 200
        assert resp.json()["access_token"] == "sb-access-token"


class TestSSOSessionContextEnrichment:
    """Verify /api/sso/session enriches metadata with org, plan, and license info."""

    def test_enriches_with_org_info(self, sso_session_client):
        """Org name and logo should be synced into metadata."""
        client, mock_admin = sso_session_client
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("organizations", {
            "id": "org-123",
            "nome": "Acme Corp",
            "logo_url": "https://example.com/logo.png",
        })

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        call_args = mock_admin.auth.admin.update_user_by_id.call_args
        metadata = call_args[0][1]["user_metadata"]
        assert metadata["org_name"] == "Acme Corp"
        assert metadata["org_logo_url"] == "https://example.com/logo.png"

    def test_enriches_with_subscription_plan(self, sso_session_client):
        """Subscription status and plan info should be synced."""
        client, mock_admin = sso_session_client
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("subscriptions", [{
            "org_id": "org-123",
            "status": "active",
            "expires_at": None,
            "plans": {"slug": "pro", "max_users": 50, "max_products": 10, "features": {"ai": True}},
        }])

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        call_args = mock_admin.auth.admin.update_user_by_id.call_args
        metadata = call_args[0][1]["user_metadata"]
        assert metadata["plan_slug"] == "pro"
        assert metadata["plan_max_users"] == 50
        assert metadata["subscription_status"] == "active"
        assert metadata["plan_features"] == {"ai": True}

    def test_enriches_with_license_expiry(self, sso_session_client):
        """License expiry for the target product should be synced."""
        client, mock_admin = sso_session_client
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("products", [{"id": "prod-1", "slug": "therapy-platform"}])
        mock_sb.set_table_data("licenses", [{
            "org_id": "org-123", "product_id": "prod-1", "status": "active",
            "fim": "2026-12-31T00:00:00+00:00",
        }])

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        call_args = mock_admin.auth.admin.update_user_by_id.call_args
        metadata = call_args[0][1]["user_metadata"]
        assert metadata["license_expires_at"] == "2026-12-31T00:00:00+00:00"

    def test_graceful_when_no_subscription(self, sso_session_client):
        """Missing subscription should not add plan fields but should not fail."""
        client, mock_admin = sso_session_client
        # No subscription data set → enrichment finds nothing

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        call_args = mock_admin.auth.admin.update_user_by_id.call_args
        metadata = call_args[0][1]["user_metadata"]
        # Base fields always present
        assert metadata["noctus_role"] == "user"
        assert metadata["org_role"] == "member"
        # Plan fields should NOT be present (no subscription found)
        assert "plan_slug" not in metadata

    def test_enrichment_failure_does_not_block_session(self, sso_session_client):
        """Even if enrichment queries fail entirely, session should still work."""
        client, mock_admin = sso_session_client

        token = _make_sso_token()
        resp = client.post("/api/sso/session", json={"token": token})

        assert resp.status_code == 200
        assert resp.json()["access_token"] == "sb-access-token"
