"""
Tests for Onboarding Router.

GET   /api/onboarding/status
PATCH /api/onboarding/complete
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/onboarding/status
# ---------------------------------------------------------------------------

class TestGetOnboardingStatus:
    def test_get_status_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Corp",
            "onboarding_completed": False,
            "onboarding_steps": {
                "company_details": True,
                "choose_plan": False,
                "invite_team": False,
                "enable_product": False,
            },
        })

        resp = client.get("/api/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["org_id"] == "org-1"
        assert data["onboarding_completed"] is False
        assert data["progress"]["completed"] == 1
        assert data["progress"]["total"] == 4
        assert data["progress"]["percentage"] == 25

    def test_get_status_all_completed(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("organizations", {
            "id": "org-1",
            "nome": "Test Corp",
            "onboarding_completed": True,
            "onboarding_steps": {
                "company_details": True,
                "choose_plan": True,
                "invite_team": True,
                "enable_product": True,
            },
        })

        resp = client.get("/api/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["onboarding_completed"] is True
        assert data["progress"]["percentage"] == 100

    def test_get_status_org_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("organizations", None)

        resp = client.get("/api/onboarding/status")
        assert resp.status_code == 404

    def test_get_status_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/onboarding/status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/onboarding/complete
# ---------------------------------------------------------------------------

class TestCompleteOnboardingStep:
    def test_complete_step_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("organizations", [
            {
                "id": "org-1",
                "onboarding_completed": False,
                "onboarding_steps": {
                    "company_details": False,
                    "choose_plan": False,
                    "invite_team": False,
                    "enable_product": False,
                },
            }
        ])

        resp = client.patch("/api/onboarding/complete", json={
            "step": "company_details",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["step"] == "company_details"

    def test_complete_step_with_data(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("noctus_users", {"org_id": "org-1"})
        mock_sb.set_table_data("organizations", [
            {
                "id": "org-1",
                "onboarding_completed": False,
                "onboarding_steps": {
                    "company_details": False,
                    "choose_plan": False,
                    "invite_team": False,
                    "enable_product": False,
                },
            }
        ])

        resp = client.patch("/api/onboarding/complete", json={
            "step": "company_details",
            "data": {
                "nome": "Corp Updated",
                "cnpj": "12.345.678/0001-90",
            },
        })
        assert resp.status_code == 200

    def test_complete_step_invalid(self, client):
        resp = client.patch("/api/onboarding/complete", json={
            "step": "invalid_step",
        })
        assert resp.status_code == 400

    def test_complete_step_missing_field(self, client):
        resp = client.patch("/api/onboarding/complete", json={})
        assert resp.status_code == 422

    def test_complete_step_unauthenticated(self, unauth_client):
        resp = unauth_client.patch("/api/onboarding/complete", json={
            "step": "company_details",
        })
        assert resp.status_code == 401
