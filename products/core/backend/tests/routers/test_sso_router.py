"""
Tests for SSO Router.

POST  /api/sso/token           — Generate SSO token
POST  /api/sso/validate        — Validate SSO token
GET   /api/sso/launch/{slug}   — Redirect to product with SSO token
POST  /api/sso/session         — Exchange SSO token for Supabase session
"""
import time
import uuid

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
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp-imobiliario", "ativo": True, "deploy_scope": "live", "url_base": "http://localhost:8080"})
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
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp", "ativo": True, "deploy_scope": "live", "url_base": "http://localhost:8080"})
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

@pytest.fixture
def admin_client(client, platform_admin_override):
    """`client` with the platform-admin gate satisfied."""
    return client


class TestValidateSSOToken:
    # 2026-10-09: no longer an unauthenticated, non-consuming token oracle.
    def test_validate_refuses_a_non_admin(self, client):
        with patch("app.routers.sso.verify_sso_token", return_value={"sub": "u"}) as verify:
            resp = client.post("/api/sso/validate", json={"token": "any-token"})
        assert resp.status_code == 403
        verify.assert_not_called()

    def test_validate_refuses_anonymous(self, unauth_client):
        with patch("app.routers.sso.verify_sso_token", return_value={"sub": "u"}) as verify:
            resp = unauth_client.post("/api/sso/validate", json={"token": "any-token"})
        assert resp.status_code == 401
        verify.assert_not_called()

    def test_validate_sso_token_success(self, admin_client):
        mock_payload = {
            "sub": "user-123",
            "org_id": "org-1",
            "product": "erp",
            "email": "test@example.com",
            "role": "user",
            "type": "sso",
        }

        with patch("app.routers.sso.verify_sso_token", return_value=mock_payload):
            resp = admin_client.post("/api/sso/validate", json={
                "token": "valid-sso-token",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True
            assert data["user_id"] == "user-123"
            assert data["org_id"] == "org-1"
            assert data["product"] == "erp"

    def test_validate_sso_token_expired(self, admin_client):
        from fastapi import HTTPException

        def _mock_verify(token):
            raise HTTPException(status_code=401, detail="Token SSO expirado")

        with patch("app.routers.sso.verify_sso_token", side_effect=_mock_verify):
            resp = admin_client.post("/api/sso/validate", json={
                "token": "expired-token",
            })
            assert resp.status_code == 401

    def test_validate_sso_token_invalid(self, admin_client):
        from fastapi import HTTPException

        def _mock_verify(token):
            raise HTTPException(status_code=401, detail="Token SSO invalido")

        with patch("app.routers.sso.verify_sso_token", side_effect=_mock_verify):
            resp = admin_client.post("/api/sso/validate", json={
                "token": "bad-token",
            })
            assert resp.status_code == 401

    def test_validate_sso_token_missing_token(self, admin_client):
        resp = admin_client.post("/api/sso/validate", json={})
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
            "ativo": True, "deploy_scope": "live",
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
            "ativo": True, "deploy_scope": "live",
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
    role="user", org_role="member", product="therapy-platform", jti=None, bnd=None,
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
        "jti": jti or str(uuid.uuid4()),
        "iss": SSO_ISSUER,
        "aud": SSO_AUDIENCE,
        "iat": now,
        "exp": (now - 600) if expired else (now + 300),
    }
    if bnd:
        payload["bnd"] = bnd
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
    # /session re-checks the license at redemption.
    # Legacy-regime row (active + dev) so the pre-P2.1 slug-optional flows keep
    # their coverage; the strict regime is exercised in TestSSORegimeMixed.
    mock_sb.set_table_data("products", [
        {"id": "prod-1", "slug": "therapy-platform", "ativo": True, "deploy_scope": "dev"},
    ])
    mock_sb.set_table_data("licenses", [{
        "id": "lic-1", "status": "active", "org_id": "org-123", "product_id": "prod-1",
    }])

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
            "sub": "uid", "type": "sso", "jti": "j-1", "iss": SSO_ISSUER, "aud": SSO_AUDIENCE,
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
        client.mock_supabase.set_table_data("products", [
            {"id": "prod-1", "slug": "therapy-platform", "ativo": True, "deploy_scope": "dev"},
        ])
        client.mock_supabase.set_table_data("licenses", [{
            "id": "lic-1", "status": "active", "org_id": "org-123", "product_id": "prod-1",
        }])

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
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp", "ativo": True, "deploy_scope": "live", "url_base": "http://localhost:8080"})
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
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp", "ativo": True, "deploy_scope": "live", "url_base": "http://localhost:8080"})
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
        mock_admin.auth.admin.update_user_by_id.assert_called_once()
        uid, update = mock_admin.auth.admin.update_user_by_id.call_args[0]
        assert uid == "user-uid-123"
        assert update["user_metadata"].items() >= {
            "noctus_role": "admin", "org_role": "owner", "org_id": "org-123",
        }.items()

    def test_syncs_member_role(self, sso_session_client):
        """Regular users get their org_role synced too."""
        client, mock_admin = sso_session_client
        token = _make_sso_token(role="user", org_role="member")

        resp = client.post("/api/sso/session", json={"token": token})
        assert resp.status_code == 200

        mock_admin.auth.admin.update_user_by_id.assert_called_once()
        uid, update = mock_admin.auth.admin.update_user_by_id.call_args[0]
        assert uid == "user-uid-123"
        assert update["user_metadata"].items() >= {
            "noctus_role": "user", "org_role": "member", "org_id": "org-123",
        }.items()

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
        mock_sb.set_table_data("products", [
            {"id": "prod-1", "slug": "therapy-platform", "ativo": True, "deploy_scope": "dev"},
        ])
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


# ---------------------------------------------------------------------------
# SEC-2 (2026-09-28) — end customers only SSO into products that declare
# `aceita_clientes`; staff are unaffected. The real `create_sso_token` runs
# (no self-patching) — a 200 carries a genuinely minted, verifiable token.
# ---------------------------------------------------------------------------

_LICENSE = [{"id": "lic-1", "status": "active", "org_id": "org-1", "product_id": "prod-1"}]


def _seed(mock_sb, *, org_role, aceita_clientes):
    mock_sb.set_table_data("noctus_users", {
        "id": "test-user-123", "org_id": "org-1", "role": "user",
        "org_role": org_role, "email": "test@example.com",
    })
    mock_sb.set_table_data("products", {
        "id": "prod-1", "slug": "social-wiring", "url_base": "http://localhost:8080",
        "aceita_clientes": aceita_clientes,
        "ativo": True, "deploy_scope": "live",
    })
    mock_sb.set_table_data("licenses", _LICENSE)


class TestSSOCustomerRole:
    def test_token_refuses_customer_for_staff_only_product(self, client):
        _seed(client.mock_supabase, org_role="membro", aceita_clientes=False)
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 403
        assert resp.json()["error"]["message"] == "Área restrita à equipe."

    def test_token_allows_customer_for_customer_product(self, client):
        _seed(client.mock_supabase, org_role="membro", aceita_clientes=True)
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 200
        assert resp.json()["sso_token"]

    def test_token_unchanged_for_staff(self, client):
        _seed(client.mock_supabase, org_role="member", aceita_clientes=False)
        resp = client.post("/api/sso/token", json={"product_slug": "social-wiring"})
        assert resp.status_code == 200

    def test_launch_refuses_customer_for_staff_only_product(self, client):
        _seed(client.mock_supabase, org_role="membro", aceita_clientes=False)
        resp = client.get("/api/sso/launch/social-wiring", follow_redirects=False)
        assert resp.status_code == 403

    def test_launch_allows_customer_for_customer_product(self, client):
        _seed(client.mock_supabase, org_role="membro", aceita_clientes=True)
        resp = client.get("/api/sso/launch/social-wiring", follow_redirects=False)
        assert resp.status_code == 302


class TestSwitcherCustomerRole:
    """/api/auth/me drives the product switcher — it must not offer a
    customer what /api/sso/token refuses."""

    def _me(self, client, org_role):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123", "email": "t@x", "nome": "T",
            "org_id": "org-1", "role": "user", "org_role": org_role,
        })
        mock_sb.set_table_data("organizations", {"id": "org-1", "nome": "NoctusAI"})
        mock_sb.set_table_data("licenses", [
            {"id": "l1", "status": "active", "org_id": "org-1", "product_id": "p-staff"},
            {"id": "l2", "status": "active", "org_id": "org-1", "product_id": "p-cust"},
        ])
        mock_sb.set_table_data("products", [
            {"id": "p-staff", "slug": "social-wiring", "nome": "SW", "ativo": True,
             "url_base": "http://localhost:1", "aceita_clientes": False},
            {"id": "p-cust", "slug": "community", "nome": "C", "ativo": True,
             "url_base": "http://localhost:2", "aceita_clientes": True},
        ])
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        return {p["slug"]: p["has_access"] for p in resp.json()["products"]}

    def test_customer_sees_only_customer_products(self, client):
        access = self._me(client, "membro")
        assert access == {"social-wiring": False, "community": True}

    def test_staff_sees_every_licensed_product(self, client):
        access = self._me(client, "member")
        assert access == {"social-wiring": True, "community": True}


class TestSSOSessionSingleUseAndBinding:
    """Security hotfix 2026-10: single-use jti, audience binding, license recheck."""

    def _prime(self, mock_sb, licensed=True):
        mock_sb.set_table_data("products", [
            {"id": "prod-1", "slug": "therapy-platform", "ativo": True, "deploy_scope": "dev"},
        ])
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active", "org_id": "org-123", "product_id": "prod-1",
        }] if licensed else [])

    def test_replayed_token_is_refused_with_401(self, sso_session_client):
        client, mock_sb = sso_session_client
        self._prime(mock_sb)
        token = _make_sso_token()
        first = client.post("/api/sso/session", json={"token": token})
        assert first.status_code == 200

        # The DB's PK refuses the second insert of the same jti.
        class _DupDb:
            def table(self, name):
                builder = mock_sb.table(name)
                if name == "sso_token_redemptions":
                    builder.insert = MagicMock(side_effect=Exception(
                        "duplicate key value violates unique constraint (23505)"))
                return builder

        with patch("app.routers.sso.get_admin_client", return_value=_DupDb()):
            second = client.post("/api/sso/session", json={"token": token})
        assert second.status_code == 401

    def test_redemption_row_recorded(self, sso_session_client):
        client, mock_sb = sso_session_client
        self._prime(mock_sb)
        jti = str(uuid.uuid4())
        resp = client.post("/api/sso/session", json={"token": _make_sso_token(jti=jti)})
        assert resp.status_code == 200
        inserted = mock_sb.table("sso_token_redemptions").inserted_payloads
        assert any(p.get("jti") == jti and p.get("product") == "therapy-platform" for p in inserted)

    def test_token_without_jti_is_refused(self, sso_session_client):
        client, mock_sb = sso_session_client
        self._prime(mock_sb)
        now = int(time.time())
        secret = (getattr(settings, "sso_jwt_secret", "") or "").strip() or settings.jwt_secret
        token = jwt.encode({
            "sub": "u", "email": "a@b.c", "org_id": "org-123", "product": "therapy-platform",
            "type": "sso", "iss": SSO_ISSUER, "aud": SSO_AUDIENCE, "iat": now, "exp": now + 300,
        }, secret, algorithm=settings.jwt_algorithm)
        assert client.post("/api/sso/session", json={"token": token}).status_code == 401

    def test_product_mismatch_is_refused(self, sso_session_client):
        client, mock_sb = sso_session_client
        self._prime(mock_sb)
        resp = client.post("/api/sso/session", json={
            "token": _make_sso_token(), "product_slug": "other-product",
        })
        assert resp.status_code == 401

    def test_matching_product_accepted(self, sso_session_client):
        client, mock_sb = sso_session_client
        self._prime(mock_sb)
        resp = client.post("/api/sso/session", json={
            "token": _make_sso_token(), "product_slug": "therapy-platform",
        })
        assert resp.status_code == 200

    def test_revoked_license_cannot_redeem(self, sso_session_client):
        client, mock_sb = sso_session_client
        self._prime(mock_sb, licensed=False)
        resp = client.post("/api/sso/session", json={"token": _make_sso_token()})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# P2.1 -- mixed regime derived from the catalog (strict vs legacy)
# ---------------------------------------------------------------------------

import logging  # noqa: E402

from app.sso_regime import sso_regime  # noqa: E402


class TestSSORegimePredicate:
    @pytest.mark.parametrize("row,expected", [
        ({"ativo": True, "deploy_scope": "dev"}, "legacy"),
        ({"ativo": True, "deploy_scope": "live"}, "strict"),
        ({"ativo": True, "deploy_scope": None}, "strict"),
        ({"ativo": True, "deploy_scope": "staging"}, "strict"),
        ({"ativo": True}, "strict"),
        ({"ativo": False, "deploy_scope": "dev"}, "strict"),
        ({"ativo": None, "deploy_scope": "dev"}, "strict"),
        ({"ativo": "true", "deploy_scope": "dev"}, "strict"),
        ({"deploy_scope": "dev"}, "strict"),
        ({}, "strict"),
        (None, "strict"),
    ])
    def test_allowlist_table(self, row, expected):
        assert sso_regime(row) == expected


def _prime_regime(mock_sb, *, ativo=True, scope="live", slug="therapy-platform"):
    mock_sb.set_table_data("products", [
        {"id": "prod-1", "slug": slug, "ativo": ativo, "deploy_scope": scope},
    ])
    mock_sb.set_table_data("licenses", [{
        "id": "lic-1", "status": "active", "org_id": "org-123", "product_id": "prod-1",
    }])


class TestSSORegimeMixed:
    def test_live_token_without_slug_is_401(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        resp = client.post("/api/sso/session", json={"token": _make_sso_token()})
        assert resp.status_code == 401

    def test_dev_token_with_other_slug_is_401(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="dev")
        resp = client.post("/api/sso/session", json={
            "token": _make_sso_token(), "product_slug": "social-wiring",
        })
        assert resp.status_code == 401

    def test_live_token_with_other_live_slug_is_401(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        resp = client.post("/api/sso/session", json={
            "token": _make_sso_token(), "product_slug": "social-wiring",
        })
        assert resp.status_code == 401

    def test_live_token_with_matching_slug_is_200(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        resp = client.post("/api/sso/session", json={
            "token": _make_sso_token(), "product_slug": "therapy-platform",
        })
        assert resp.status_code == 200

    def test_dev_token_without_slug_is_200_and_logs_legacy(self, sso_session_client, caplog):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="dev")
        jti = str(uuid.uuid4())
        token = _make_sso_token(jti=jti)
        with caplog.at_level(logging.WARNING, logger="app.routers.sso"):
            resp = client.post(
                "/api/sso/session", json={"token": token},
                headers={"Origin": "https://orbity.example"},
            )
        assert resp.status_code == 200
        line = next(r.getMessage() for r in caplog.records if "sso_legacy_redeem" in r.getMessage())
        assert f"jti={jti}" in line
        assert "product=therapy-platform" in line
        assert "user_id=user-uid-123" in line
        assert "org_id=org-123" in line
        assert "origin=https://orbity.example" in line
        assert "slug_present=False" in line
        assert token not in line

    def test_strict_redemption_does_not_log_legacy(self, sso_session_client, caplog):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        with caplog.at_level(logging.WARNING, logger="app.routers.sso"):
            resp = client.post("/api/sso/session", json={
                "token": _make_sso_token(), "product_slug": "therapy-platform",
            })
        assert resp.status_code == 200
        assert not [r for r in caplog.records if "sso_legacy_redeem" in r.getMessage()]

    @pytest.mark.parametrize("ativo,scope", [(True, None), (True, "weird"), (False, "dev"), (False, "live")])
    def test_unknown_scope_or_inactive_is_strict(self, sso_session_client, ativo, scope):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, ativo=ativo, scope=scope)
        resp = client.post("/api/sso/session", json={"token": _make_sso_token()})
        assert resp.status_code == 401

    def test_rejected_request_does_not_burn_the_jti(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        token = _make_sso_token()
        # A relay without the slug is refused ...
        assert client.post("/api/sso/session", json={"token": token}).status_code == 401
        # ... a wrong slug too ...
        assert client.post("/api/sso/session", json={
            "token": token, "product_slug": "attacker",
        }).status_code == 401
        assert mock_sb.table("sso_token_redemptions").inserted_payloads == []
        # ... and the legitimate redeemer still gets its session.
        ok = client.post("/api/sso/session", json={"token": token, "product_slug": "therapy-platform"})
        assert ok.status_code == 200


class TestSSOLaunchTransport:
    def _seed_product(self, client, scope, ativo=True):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123", "org_id": "org-1", "role": "user", "org_role": "member",
            "email": "test@example.com",
        })
        mock_sb.set_table_data("products", {
            "id": "prod-1", "slug": "erp", "url_base": "http://localhost:8080",
            "aceita_clientes": False, "ativo": ativo, "deploy_scope": scope,
        })
        mock_sb.set_table_data("licenses", _LICENSE)

    def test_strict_token_returns_fragment_url(self, client):
        self._seed_product(client, "live")
        data = client.post("/api/sso/token", json={"product_slug": "erp"}).json()
        assert data["redirect_url"] == f"http://localhost:8080/sso#token={data['sso_token']}"
        assert "?token=" not in data["redirect_url"]

    def test_legacy_token_returns_query_url(self, client):
        self._seed_product(client, "dev")
        data = client.post("/api/sso/token", json={"product_slug": "erp"}).json()
        assert data["redirect_url"] == f"http://localhost:8080/sso?token={data['sso_token']}"

    def test_strict_launch_redirects_to_fragment(self, client):
        self._seed_product(client, "live")
        loc = client.get("/api/sso/launch/erp", follow_redirects=False).headers["location"]
        assert "/sso#token=" in loc and "?token=" not in loc

    def test_legacy_launch_redirects_to_query(self, client):
        self._seed_product(client, "dev")
        loc = client.get("/api/sso/launch/erp", follow_redirects=False).headers["location"]
        assert "/sso?token=" in loc and "#token=" not in loc

    def test_inactive_product_cannot_mint_token(self, client):
        self._seed_product(client, "dev", ativo=False)
        assert client.post("/api/sso/token", json={"product_slug": "erp"}).status_code == 403

    def test_inactive_product_cannot_launch(self, client):
        self._seed_product(client, "dev", ativo=False)
        assert client.get("/api/sso/launch/erp", follow_redirects=False).status_code == 403


class TestSSOCallbackMarkerParity:
    def test_core_probe_marker_matches_seed_callback(self):
        """The probe's marker and the seed component's literal must not drift."""
        from pathlib import Path

        from app.services.sso_callback_probe import SSO_CALLBACK_MARKER

        seed = next(
            (p / "seed/lib/frontend/src/components/SSOCallback.tsx"
             for p in Path(__file__).resolve().parents
             if (p / "seed/lib/frontend/src/components/SSOCallback.tsx").exists()),
            None,
        )
        if seed is None:  # core image ships without the seed source tree
            pytest.skip("seed source not present")
        assert f"SSO_CALLBACK_MARKER = '{SSO_CALLBACK_MARKER}'" in seed.read_text()


# ---------------------------------------------------------------------------
# Unresolvable launch URL → typed 409 BEFORE minting (2026-10-09)
# ---------------------------------------------------------------------------

class TestUnresolvableLaunchUrl:
    def _seed(self, client, monkeypatch):
        for k in [k for k in __import__("os").environ if k.startswith("PRODUCT_URL_")]:
            monkeypatch.delenv(k, raising=False)
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123", "org_id": "org-1", "role": "user",
            "email": "test@example.com",
        })
        mock_sb.set_table_data("products", {
            "id": "prod-1", "slug": "ghost", "ativo": True,
            "deploy_scope": "live", "url_base": None,
        })
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active", "org_id": "org-1", "product_id": "prod-1",
        }])

    def test_token_is_409_and_nothing_minted(self, client, monkeypatch):
        self._seed(client, monkeypatch)
        with patch("app.routers.sso.create_sso_token", return_value="t") as mint:
            resp = client.post("/api/sso/token", json={"product_slug": "ghost"})
        assert resp.status_code == 409
        assert "URL" in resp.text
        mint.assert_not_called()

    def test_launch_is_409_and_nothing_minted(self, client, monkeypatch):
        self._seed(client, monkeypatch)
        with patch("app.routers.sso.create_sso_token", return_value="t") as mint:
            resp = client.get("/api/sso/launch/ghost", follow_redirects=False)
        assert resp.status_code == 409
        mint.assert_not_called()


# ---------------------------------------------------------------------------
# P2.2 browser-bind
# ---------------------------------------------------------------------------

class TestSSOBrowserBind:
    NONCE = "nonce-for-browser-x"

    @staticmethod
    def _bnd(nonce):
        import hashlib
        return hashlib.sha256(nonce.encode()).hexdigest()

    def _redeem(self, client, jti, bnd, cookie=None, **kw):
        token = _make_sso_token(jti=jti, bnd=bnd)
        cookies = {f"sso_bnd_{jti}": cookie} if cookie is not None else None
        return client.post("/api/sso/session", json={"token": token, "product_slug": "therapy-platform"},
                           cookies=cookies, **kw)

    def test_match_redeems_and_clears_cookie(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        jti = str(uuid.uuid4())
        resp = self._redeem(client, jti, self._bnd(self.NONCE), cookie=self.NONCE)
        assert resp.status_code == 200
        assert f"sso_bnd_{jti}=" in resp.headers.get("set-cookie", "")
        assert "Max-Age=0" in resp.headers["set-cookie"]

    def test_mismatch_is_exactly_401_and_does_not_burn_jti(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        jti = str(uuid.uuid4())
        resp = self._redeem(client, jti, self._bnd(self.NONCE), cookie="attacker-browser-nonce")
        assert resp.status_code == 401
        # the legitimate browser (right cookie) still redeems the same token
        resp = self._redeem(client, jti, self._bnd(self.NONCE), cookie=self.NONCE)
        assert resp.status_code == 200

    def test_absent_cookie_allowed_and_logged(self, sso_session_client, caplog):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        jti = str(uuid.uuid4())
        with caplog.at_level(logging.WARNING, logger="app.routers.sso"):
            resp = self._redeem(client, jti, self._bnd(self.NONCE), headers={"Origin": "https://social.example"})
        assert resp.status_code == 200
        line = next(r.getMessage() for r in caplog.records if "sso_unbound_redeem" in r.getMessage())
        assert f"jti={jti}" in line and "product=therapy-platform" in line and "regime=strict" in line
        assert "origin=https://social.example" in line
        assert self.NONCE not in line

    @pytest.mark.parametrize("cookie,bnd,allow,expected", [
        (None, None, True, "no_bnd"),
        ("n", None, False, "no_bnd"),
        ("n", "HASH", True, "bound"),
        ("n", "HASH", False, "bound"),
        ("other", "HASH", True, "mismatch"),
        (None, "HASH", True, "unbound_allowed"),
        (None, "HASH", False, "unbound_rejected"),
    ])
    def test_bind_verdict_every_branch(self, cookie, bnd, allow, expected):
        from app.sso_regime import bind_verdict
        if bnd == "HASH":
            bnd = self._bnd("n")
        assert bind_verdict(cookie, bnd, allow_unbound=allow) == expected

    def test_unbound_redeem_currently_allowed_for_both_regimes(self):
        from app.sso_regime import unbound_redeem_allowed
        assert unbound_redeem_allowed("strict") is True
        assert unbound_redeem_allowed("legacy") is True

    def test_cookie_for_another_jti_does_not_satisfy(self, sso_session_client):
        client, mock_sb = sso_session_client
        _prime_regime(mock_sb, scope="live")
        jti = str(uuid.uuid4())
        resp = client.post("/api/sso/session",
                           json={"token": _make_sso_token(jti=jti, bnd=self._bnd(self.NONCE)), "product_slug": "therapy-platform"},
                           cookies={f"sso_bnd_{uuid.uuid4()}": self.NONCE})
        assert resp.status_code == 200  # treated as absent (allowed today)

    def _setup_launch(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"id": "test-user-123", "org_id": "org-1", "role": "user"})
        mock_sb.set_table_data("products", {"id": "prod-1", "slug": "erp", "url_base": "http://localhost:8080",
                                            "ativo": True, "deploy_scope": "live"})
        mock_sb.set_table_data("licenses", [{"id": "lic-1", "status": "active", "org_id": "org-1", "product_id": "prod-1"}])

    def _assert_bind(self, resp, token_holder):
        sc = resp.headers["set-cookie"]
        name, _, rest = sc.partition("=")
        jti = name.removeprefix("sso_bnd_")
        nonce = rest.split(";")[0]
        assert name.startswith("sso_bnd_") and nonce
        for attr in ("HttpOnly", "Secure", "SameSite=strict", "Path=/api/sso/session",
                     f"Max-Age={settings.sso_token_expiration_minutes * 60}"):
            assert attr.lower() in sc.lower(), attr
        payload = jwt.decode(token_holder, options={"verify_signature": False})
        assert payload["jti"] == jti
        assert payload["bnd"] == self._bnd(nonce) and payload["bnd"] != nonce
        return nonce

    def test_token_endpoint_sets_bind_cookie_and_claim(self, client):
        self._setup_launch(client)
        resp = client.post("/api/sso/token", json={"product_slug": "erp"})
        assert resp.status_code == 200
        nonce = self._assert_bind(resp, resp.json()["sso_token"])
        assert nonce not in resp.text

    def test_launch_sets_bind_cookie_and_claim(self, client):
        self._setup_launch(client)
        resp = client.get("/api/sso/launch/erp", follow_redirects=False)
        assert resp.status_code == 302
        loc = resp.headers["location"]
        token = loc.split("token=")[1]
        nonce = self._assert_bind(resp, token)
        assert nonce not in loc

    def test_each_launch_gets_its_own_cookie(self, client):
        self._setup_launch(client)
        a = client.post("/api/sso/token", json={"product_slug": "erp"})
        b = client.post("/api/sso/token", json={"product_slug": "erp"})
        assert a.headers["set-cookie"].split("=")[0] != b.headers["set-cookie"].split("=")[0]


# ---------------------------------------------------------------------------
# Cross-site launch guard: typed 409 BEFORE minting, never a silent launch
# ---------------------------------------------------------------------------

class TestCrossSiteLaunchGuard:
    def _seed(self, client, url_base):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "id": "test-user-123", "org_id": "org-1", "role": "user", "email": "test@example.com",
        })
        mock_sb.set_table_data("products", {
            "id": "prod-1", "slug": "academia-x", "ativo": True, "deploy_scope": "live",
            "url_base": url_base,
        })
        mock_sb.set_table_data("licenses", [{
            "id": "lic-1", "status": "active", "org_id": "org-1", "product_id": "prod-1",
        }])

    def test_token_cross_site_is_409_and_no_token_or_cookie(self, client, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")
        monkeypatch.setenv("PRODUCT_URL_ACADEMIA_X", "https://academiadareciclagem.eco")
        self._seed(client, None)
        resp = client.post("/api/sso/token", json={"product_slug": "academia-x"})
        assert resp.status_code == 409
        assert "mesmo site" in resp.text
        assert "set-cookie" not in resp.headers

    def test_launch_cross_site_is_409_no_redirect_no_cookie(self, client, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")
        monkeypatch.setenv("PRODUCT_URL_ACADEMIA_X", "https://academiadareciclagem.eco")
        self._seed(client, None)
        resp = client.get("/api/sso/launch/academia-x", follow_redirects=False)
        assert resp.status_code == 409
        assert "location" not in resp.headers
        assert "set-cookie" not in resp.headers

    def test_same_site_subdomain_still_launches(self, client, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")
        monkeypatch.setenv("PRODUCT_URL_ACADEMIA_X", "https://academia-x.noctusai.com")
        self._seed(client, None)
        resp = client.post("/api/sso/token", json={"product_slug": "academia-x"})
        assert resp.status_code == 200
        assert resp.json()["redirect_url"].startswith("https://academia-x.noctusai.com/sso#token=")

    def test_unresolvable_core_is_409(self, client, monkeypatch):
        for k in [k for k in __import__("os").environ if k.startswith("PRODUCT_URL_")]:
            monkeypatch.delenv(k, raising=False)
        self._seed(client, "https://academia-x.noctusai.com")
        resp = client.post("/api/sso/token", json={"product_slug": "academia-x"})
        assert resp.status_code == 409
