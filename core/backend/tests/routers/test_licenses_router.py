"""
Tests for Licenses Router.

GET    /api/licenses
POST   /api/licenses               (admin only)
DELETE /api/licenses/{id}           (admin only)
GET    /api/licenses/check/{slug}
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/licenses
# ---------------------------------------------------------------------------

class TestListLicenses:
    def test_list_licenses_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {
            "org_id": "org-1",
        })
        mock_sb.set_table_data("licenses", [
            {"id": "lic-1", "org_id": "org-1", "product_id": "prod-1", "status": "active"},
        ])

        resp = client.get("/api/licenses")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_list_licenses_profile_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", None)

        resp = client.get("/api/licenses")
        assert resp.status_code == 404

    def test_list_licenses_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("licenses", [])

        resp = client.get("/api/licenses")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_licenses_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/licenses")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/licenses (admin only)
# ---------------------------------------------------------------------------

class TestGrantLicense:
    def test_grant_license_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        # First execute() → active check returns empty; second → insert returns new license
        mock_sb.set_table_responses("licenses", [
            [],
            [{"id": "lic-new", "org_id": "org-1", "product_id": "prod-1", "status": "active"}],
        ])

        resp = admin_client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"

    def test_grant_license_duplicate_active_returns_409(self, admin_client):
        mock_sb = admin_client.mock_supabase
        # Active check returns an existing active license → 409
        mock_sb.set_table_data("licenses", [
            {"id": "lic-1", "org_id": "org-1", "product_id": "prod-1", "status": "active"},
        ])

        resp = admin_client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
        })
        assert resp.status_code == 409

    def test_grant_license_after_revoke_creates_new_record(self, admin_client):
        """Re-granting after revocation creates a new license (not an update)."""
        mock_sb = admin_client.mock_supabase
        # Active check returns empty (revoked license is NOT active);
        # insert returns the new license
        mock_sb.set_table_responses("licenses", [
            [],
            [{"id": "lic-new", "org_id": "org-1", "product_id": "prod-1", "status": "active"}],
        ])

        resp = admin_client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "lic-new"
        assert data["status"] == "active"

    def test_grant_license_forbidden_for_non_admin(self, client):
        resp = client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
        })
        assert resp.status_code == 403

    def test_grant_license_missing_fields(self, admin_client):
        resp = admin_client.post("/api/licenses", json={
            "org_id": "org-1",
        })
        assert resp.status_code == 422

    def test_grant_license_with_expiry_date(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("licenses", [
            [],
            [{"id": "lic-new", "org_id": "org-1", "product_id": "prod-1", "status": "active", "fim": "2026-06-01T00:00:00"}],
        ])

        resp = admin_client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
            "fim": "2026-06-01T00:00:00",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["fim"] == "2026-06-01T00:00:00"

    def test_grant_license_without_expiry_date(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_responses("licenses", [
            [],
            [{"id": "lic-new", "org_id": "org-1", "product_id": "prod-1", "status": "active"}],
        ])

        resp = admin_client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "fim" not in data or data.get("fim") is None

    def test_grant_license_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/licenses", json={
            "org_id": "org-1",
            "product_id": "prod-1",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/licenses/{id} (admin only)
# ---------------------------------------------------------------------------

class TestRevokeLicense:
    def test_revoke_license_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("licenses", [
            {"id": "lic-1", "org_id": "org-1", "product_id": "prod-1", "status": "revoked"},
        ])

        resp = admin_client.delete("/api/licenses/lic-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "revoked"

    def test_revoke_license_forbidden_for_non_admin(self, client):
        resp = client.delete("/api/licenses/lic-1")
        assert resp.status_code == 403

    def test_revoke_license_not_found(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("licenses", [])

        resp = admin_client.delete("/api/licenses/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/licenses/check/{slug}
# ---------------------------------------------------------------------------

class TestCheckAccess:
    def test_check_access_has_license(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("products", {"id": "prod-1"})
        mock_sb.set_table_data("licenses", [
            {"id": "lic-1", "status": "active"},
        ])

        resp = client.get("/api/licenses/check/erp-imobiliario")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_access"] is True

    def test_check_access_no_license(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("products", {"id": "prod-1"})
        mock_sb.set_table_data("licenses", [])

        resp = client.get("/api/licenses/check/erp-imobiliario")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_access"] is False

    def test_check_access_product_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("products", None)

        resp = client.get("/api/licenses/check/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_access"] is False

    def test_check_access_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/licenses/check/erp")
        assert resp.status_code == 401
