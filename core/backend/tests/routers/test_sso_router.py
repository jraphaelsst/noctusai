"""
Tests for SSO Router.

POST  /api/sso/token           — Generate SSO token
POST  /api/sso/validate        — Validate SSO token
GET   /api/sso/launch/{slug}   — Redirect to product with SSO token
"""
import pytest
from unittest.mock import patch


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
        mock_sb.set_table_data("licenses", [{"id": "lic-1", "status": "active"}])

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
            "org_id": "org-1",
            "role": "user",
        })
        mock_sb.set_table_data("products", {
            "id": "prod-1",
            "slug": "erp",
            "url_base": "http://localhost:8080",
        })
        mock_sb.set_table_data("licenses", [{"id": "lic-1"}])

        with patch("app.routers.sso.create_sso_token", return_value="redirect-token"):
            resp = client.get("/api/sso/launch/erp", follow_redirects=False)
            assert resp.status_code == 302
            assert "token=redirect-token" in resp.headers["location"]

    def test_launch_product_no_license(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1", "role": "user"})
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
