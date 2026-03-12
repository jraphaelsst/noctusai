"""
Tests for Entitlements Router.

GET /api/entitlements
GET /api/entitlements/check/{feature}
"""
import pytest
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# GET /api/entitlements
# ---------------------------------------------------------------------------

class TestListEntitlements:
    def test_list_entitlements_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        mock_entitlements = {
            "max_users": 10,
            "max_products": 3,
            "features": {"api_access": True, "sso": False},
        }

        with patch(
            "app.routers.entitlements.get_org_entitlements",
            new_callable=AsyncMock,
            return_value=mock_entitlements,
        ):
            resp = client.get("/api/entitlements")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["max_users"] == 10

    def test_list_entitlements_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/entitlements")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/entitlements/check/{feature}
# ---------------------------------------------------------------------------

class TestCheckFeature:
    def test_check_feature_available(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        with patch(
            "app.routers.entitlements.check_feature",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = client.get("/api/entitlements/check/api_access")
            assert resp.status_code == 200
            data = resp.json()
            assert data["feature"] == "api_access"
            assert data["available"] is True

    def test_check_feature_not_available(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})

        with patch(
            "app.routers.entitlements.check_feature",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = client.get("/api/entitlements/check/advanced_analytics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is False

    def test_check_feature_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/entitlements/check/some_feature")
        assert resp.status_code == 401
