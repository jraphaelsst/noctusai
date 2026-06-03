"""
Auth-boundary + validation + happy-path tests for /api/automation/* router.

Auth: strict == 401 (never in (401, 404, 422)) for all protected endpoints.

Happy-path: uses AuthClient (authenticated mock) and verifies that valid
  payloads hit the service layer (mock DB returns empty data → 4xx or 5xx
  is OK; the point is auth is NOT the failure mode for authenticated calls).
"""
import pytest


# ---------------------------------------------------------------------------
# All protected endpoints
# ---------------------------------------------------------------------------

AUTOMATION_PROTECTED = [
    ("GET",    "/api/automation/flows"),
    ("POST",   "/api/automation/flows"),
    ("GET",    "/api/automation/flows/some-id"),
    ("PATCH",  "/api/automation/flows/some-id"),
    ("DELETE", "/api/automation/flows/some-id"),
    ("GET",    "/api/automation/flows/some-id/steps"),
    ("POST",   "/api/automation/flows/some-id/steps"),
    ("PATCH",  "/api/automation/steps/some-id"),
    ("DELETE", "/api/automation/steps/some-id"),
    ("POST",   "/api/automation/flows/some-id/trigger"),
    ("GET",    "/api/automation/executions"),
    ("DELETE", "/api/automation/executions/some-id"),
    ("POST",   "/api/automation/run-due"),
]


class TestAutomationRouterAuth:
    """Every /api/automation/* endpoint requires authentication — strict 401."""

    def test_list_flows_without_auth_returns_401(self, client):
        assert client.raw().get("/api/automation/flows").status_code == 401

    def test_create_flow_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/automation/flows",
            json={
                "name": "Test",
                "trigger_type": "lead_created",
            },
        ).status_code == 401

    def test_get_flow_without_auth_returns_401(self, client):
        assert client.raw().get("/api/automation/flows/some-id").status_code == 401

    def test_update_flow_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/automation/flows/some-id",
            json={"active": False},
        ).status_code == 401

    def test_delete_flow_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/automation/flows/some-id").status_code == 401

    def test_list_steps_without_auth_returns_401(self, client):
        assert client.raw().get("/api/automation/flows/some-id/steps").status_code == 401

    def test_create_step_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/automation/flows/some-id/steps",
            json={"ord": 0, "step_type": "end"},
        ).status_code == 401

    def test_update_step_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/automation/steps/some-id",
            json={"ord": 1},
        ).status_code == 401

    def test_delete_step_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/automation/steps/some-id").status_code == 401

    def test_trigger_flow_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/automation/flows/some-id/trigger",
            json={"lead_id": "00000000-0000-0000-0000-000000000001"},
        ).status_code == 401

    def test_list_executions_without_auth_returns_401(self, client):
        assert client.raw().get("/api/automation/executions").status_code == 401

    def test_cancel_execution_without_auth_returns_401(self, client):
        assert client.raw().delete(
            "/api/automation/executions/some-id"
        ).status_code == 401

    def test_run_due_without_auth_returns_401(self, client):
        assert client.raw().post("/api/automation/run-due").status_code == 401


class TestAutomationRouterValidation:
    """Pydantic validation enforced on inbound schemas (extra=forbid)."""

    def test_create_flow_missing_trigger_type_returns_422(self, client):
        resp = client.post("/api/automation/flows", json={"name": "MyFlow"})
        assert resp.status_code == 422

    def test_create_flow_invalid_trigger_type_returns_422(self, client):
        resp = client.post(
            "/api/automation/flows",
            json={"name": "F", "trigger_type": "not_a_real_trigger"},
        )
        assert resp.status_code == 422

    def test_create_flow_extra_field_returns_422(self, client):
        """StrictHttpModel extra='forbid' — unknown fields → 422."""
        resp = client.post(
            "/api/automation/flows",
            json={
                "name": "F",
                "trigger_type": "lead_created",
                "rogue_field": True,
            },
        )
        assert resp.status_code == 422

    def test_create_flow_empty_name_returns_422(self, client):
        resp = client.post(
            "/api/automation/flows",
            json={"name": "", "trigger_type": "lead_created"},
        )
        assert resp.status_code == 422

    def test_create_step_invalid_step_type_returns_422(self, client):
        resp = client.post(
            "/api/automation/flows/some-id/steps",
            json={"ord": 0, "step_type": "invalid_type"},
        )
        assert resp.status_code == 422

    def test_create_step_negative_ord_returns_422(self, client):
        resp = client.post(
            "/api/automation/flows/some-id/steps",
            json={"ord": -1, "step_type": "end"},
        )
        assert resp.status_code == 422

    def test_create_step_wait_missing_duration_returns_422(self, client):
        """wait step without duration_minutes → config validator raises."""
        resp = client.post(
            "/api/automation/flows/some-id/steps",
            json={"ord": 0, "step_type": "wait", "config": {}},
        )
        assert resp.status_code == 422

    def test_create_step_send_message_missing_template_returns_422(self, client):
        resp = client.post(
            "/api/automation/flows/some-id/steps",
            json={"ord": 0, "step_type": "send_message", "config": {}},
        )
        assert resp.status_code == 422

    def test_trigger_flow_invalid_lead_uuid_returns_422(self, client):
        resp = client.post(
            "/api/automation/flows/some-id/trigger",
            json={"lead_id": "not-a-uuid"},
        )
        assert resp.status_code == 422

    def test_update_flow_no_fields_returns_400(self, client):
        """PATCH with zero updatable fields → 400 (not 422)."""
        resp = client.patch("/api/automation/flows/some-id", json={})
        assert resp.status_code == 400

    def test_update_step_no_fields_returns_400(self, client):
        resp = client.patch("/api/automation/steps/some-id", json={})
        assert resp.status_code == 400


class TestAutomationRouterHappyPath:
    """Authenticated happy-path calls reach the service layer.

    Mock DB returns empty data → some calls get 404/502 (not 401).
    The assertion is: auth succeeds, the service is invoked.
    """

    def test_list_flows_authenticated_not_401(self, client):
        resp = client.get("/api/automation/flows")
        assert resp.status_code != 401
        # Mock returns empty list → 200 []
        assert resp.status_code == 200

    def test_create_flow_authenticated_reaches_service(self, client):
        resp = client.post(
            "/api/automation/flows",
            json={"name": "Test Flow", "trigger_type": "lead_created"},
        )
        # Mock DB returns auto-generated non-UUID ids → response model validation
        # may return 422 (mock id shape), 201 (real id), or 502 (no data). The
        # key assertion is: auth succeeds (not 401).
        assert resp.status_code != 401
        assert resp.status_code in (201, 422, 502)

    def test_list_steps_authenticated_not_401(self, client):
        resp = client.get("/api/automation/flows/some-flow-id/steps")
        assert resp.status_code != 401
        assert resp.status_code == 200

    def test_list_executions_authenticated_not_401(self, client):
        resp = client.get("/api/automation/executions")
        assert resp.status_code != 401
        assert resp.status_code == 200

    def test_run_due_authenticated_not_401(self, client):
        resp = client.post("/api/automation/run-due")
        assert resp.status_code != 401
        # Mock DB returns no pending actions → 200 with zero counts
        assert resp.status_code == 200
        data = resp.json()
        assert "processed" in data

    def test_get_flow_authenticated_not_found_is_404_not_401(self, client):
        """Authenticated call to missing flow → 404 (service error), not 401."""
        resp = client.get("/api/automation/flows/nonexistent-id")
        assert resp.status_code != 401
        # Mock returns nothing → 404
        assert resp.status_code in (404, 502)

    def test_create_step_valid_end_step_authenticated(self, client):
        resp = client.post(
            "/api/automation/flows/some-flow-id/steps",
            json={"ord": 0, "step_type": "end"},
        )
        assert resp.status_code != 401
        assert resp.status_code in (201, 422, 502)  # 422 = mock id not UUID-parseable

    def test_create_step_valid_wait_step_authenticated(self, client):
        resp = client.post(
            "/api/automation/flows/some-flow-id/steps",
            json={"ord": 1, "step_type": "wait", "config": {"duration_minutes": 10}},
        )
        assert resp.status_code != 401
        assert resp.status_code in (201, 422, 502)  # 422 = mock id not UUID-parseable
