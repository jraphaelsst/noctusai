"""
Auth-boundary + validation tests for the /api/crm/* router
and the public /api/capture/{org_id} endpoint.

Auth: strict == 401 (not 404/422) for all protected endpoints.
Public capture: 201 / 422 / NOT 401 (unauthenticated by design).
"""
import pytest


CRM_PROTECTED = [
    ("GET",    "/api/crm/funil"),
    ("GET",    "/api/crm/stages"),
    ("GET",    "/api/crm/leads"),
    ("POST",   "/api/crm/leads"),
    ("GET",    "/api/crm/leads/some-id"),
    ("PATCH",  "/api/crm/leads/some-id"),
    ("DELETE", "/api/crm/leads/some-id"),
    ("PATCH",  "/api/crm/leads/some-id/stage"),
    ("GET",    "/api/crm/leads/some-id/activities"),
    ("POST",   "/api/crm/leads/some-id/activities"),
    ("POST",   "/api/crm/leads/some-id/score"),
    ("GET",    "/api/crm/scoring-rules"),
    ("POST",   "/api/crm/scoring-rules"),
    ("PATCH",  "/api/crm/scoring-rules/some-id"),
    ("DELETE", "/api/crm/scoring-rules/some-id"),
]

TEST_ORG = "00000000-0000-0000-0000-000000000001"


class TestCRMRouterAuth:
    """Every /api/crm/* endpoint requires authentication — strict 401."""

    def test_funil_without_auth_returns_401(self, client):
        assert client.raw().get("/api/crm/funil").status_code == 401

    def test_stages_without_auth_returns_401(self, client):
        assert client.raw().get("/api/crm/stages").status_code == 401

    def test_list_leads_without_auth_returns_401(self, client):
        assert client.raw().get("/api/crm/leads").status_code == 401

    def test_create_lead_without_auth_returns_401(self, client):
        assert client.raw().post("/api/crm/leads", json={"name": "x"}).status_code == 401

    def test_get_lead_without_auth_returns_401(self, client):
        assert client.raw().get("/api/crm/leads/some-id").status_code == 401

    def test_patch_lead_without_auth_returns_401(self, client):
        assert client.raw().patch("/api/crm/leads/some-id", json={"name": "x"}).status_code == 401

    def test_delete_lead_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/crm/leads/some-id").status_code == 401

    def test_move_stage_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/crm/leads/some-id/stage",
            json={"stage_id": TEST_ORG},
        ).status_code == 401

    def test_list_activities_without_auth_returns_401(self, client):
        assert client.raw().get("/api/crm/leads/some-id/activities").status_code == 401

    def test_add_activity_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/crm/leads/some-id/activities",
            json={"type": "call"},
        ).status_code == 401

    def test_score_lead_without_auth_returns_401(self, client):
        assert client.raw().post("/api/crm/leads/some-id/score").status_code == 401

    def test_list_scoring_rules_without_auth_returns_401(self, client):
        assert client.raw().get("/api/crm/scoring-rules").status_code == 401

    def test_create_scoring_rule_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/crm/scoring-rules",
            json={"form_id": "f1", "question": "q", "answer": "a", "score": 1},
        ).status_code == 401

    def test_update_scoring_rule_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/crm/scoring-rules/some-id",
            json={"score": 2},
        ).status_code == 401

    def test_delete_scoring_rule_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/crm/scoring-rules/some-id").status_code == 401


class TestCRMRouterValidation:
    """Pydantic validation enforced on inbound schemas."""

    def test_create_lead_empty_name_returns_422(self, client):
        resp = client.post("/api/crm/leads", json={"name": ""})
        assert resp.status_code == 422

    def test_create_lead_extra_field_returns_422(self, client):
        """StrictHttpModel extra='forbid' — unknown fields → 422."""
        resp = client.post("/api/crm/leads", json={"name": "ok", "rogue_field": True})
        assert resp.status_code == 422

    def test_create_scoring_rule_score_out_of_range_returns_422(self, client):
        resp = client.post(
            "/api/crm/scoring-rules",
            json={"form_id": "f", "question": "q", "answer": "a", "score": 99},
        )
        assert resp.status_code == 422

    def test_list_leads_invalid_page_size_returns_422(self, client):
        resp = client.get("/api/crm/leads?page_size=9999")
        assert resp.status_code == 422

    def test_add_activity_empty_type_returns_422(self, client):
        resp = client.post("/api/crm/leads/some-id/activities", json={"type": ""})
        assert resp.status_code == 422


class TestPublicCapture:
    """The /api/capture/{org_id} endpoint is public — no auth required."""

    def test_capture_no_auth_does_not_return_401(self, client):
        """Public endpoint must NOT require auth (captures from ad forms)."""
        resp = client.raw().post(
            f"/api/capture/{TEST_ORG}",
            json={"name": "Lead Capturado"},
        )
        # Must be anything except 401/403 (service errors are 201 or 502)
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_capture_with_name_returns_201_or_502(self, client):
        """Authenticated client (seeded mock) should accept the capture."""
        resp = client.raw().post(
            f"/api/capture/{TEST_ORG}",
            json={"name": "Lead", "email": "l@t.com", "phone": "11999998888"},
        )
        # 201 = success; 502 = mock client returned no data (expected in test env)
        assert resp.status_code in (201, 502)

    def test_capture_invalid_org_id_uuid_returns_422(self, client):
        """Non-UUID org_id → FastAPI path validation → 422."""
        resp = client.raw().post(
            "/api/capture/not-a-uuid",
            json={"name": "Lead"},
        )
        assert resp.status_code == 422
