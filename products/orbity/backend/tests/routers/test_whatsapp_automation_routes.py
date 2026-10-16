"""WhatsApp connections organ + webhook + automation emitters at the HTTP edge."""
from __future__ import annotations

import uuid

import pytest

from app.services import automation_triggers


class TestAuthBoundary:
    """Strict == 401 (never 404/422): the routes exist and auth runs first."""

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/whatsapp/connections"),
        ("post", "/api/whatsapp/connections"),
        ("delete", f"/api/whatsapp/connections/{uuid.uuid4()}"),
        ("get", f"/api/whatsapp/connections/{uuid.uuid4()}/status"),
    ])
    def test_connections_require_auth(self, client, method, path):
        kwargs = {"json": {"label": "x", "api_key": "y"}} if method == "post" else {}
        assert getattr(client.raw(), method)(path, **kwargs).status_code == 401


class TestWebhook:
    def test_unknown_token_is_404_not_500(self, client):
        # Public by nature; no encryption key in test env => generic 404, no leak.
        r = client.raw().post("/api/whatsapp/webhook/not-a-token", json={"event": "message"})
        assert r.status_code == 404


class TestEmittersAtTheRouterEdge:
    """A successful write starts the org's matching ACTIVE flow (observed in the
    automation_executions table — no patching of our own code)."""

    TEST_ORG = "test-org-123"

    def _arm(self, client, trigger_type):
        from app.dependencies import coerce_org_uuid

        org = str(coerce_org_uuid(self.TEST_ORG))
        flow_id = str(uuid.uuid4())
        mock = client.mock_supabase
        mock.set_table_data("automation_flows", [{
            "id": flow_id, "org_id": org, "name": "F", "trigger_type": trigger_type,
            "trigger_config": {}, "active": True, "schedule_window": {}, "stop_rules": {}}])
        mock.set_table_data("automation_steps", [{
            "id": str(uuid.uuid4()), "org_id": org, "flow_id": flow_id, "ord": 0,
            "step_type": "end", "config": {}}])
        mock.set_table_data("automation_executions", [])
        mock.set_table_data("automation_pending_actions", [])
        return flow_id

    def _executions(self, client):
        return client.mock_supabase.table("automation_executions").select("*").execute().data

    def test_task_created_starts_flow_with_task_subject(self, client):
        flow_id = self._arm(client, "task_created")
        r = client.post("/api/tasks", json={"title": "Ligar"})
        assert r.status_code == 201, r.text
        ex = self._executions(client)
        assert len(ex) == 1 and ex[0]["flow_id"] == flow_id
        assert ex[0]["subject_type"] == "task" and ex[0]["lead_id"] is None

    def test_client_created_starts_flow(self, client):
        self._arm(client, "client_created")
        # The mock's generated row id is not a UUID, so ClientOut re-validation answers 422 AFTER
        # the write + emit already happened; the observable under test is the execution row.
        client.post("/api/clients", json={"legal_name": "ACME"})
        assert self._executions(client)[0]["subject_type"] == "client"

    def test_lead_created_starts_flow(self, client):
        self._arm(client, "lead_created")
        client.post("/api/crm/leads", json={"name": "Maria"})  # see note above on mock ids
        ex = self._executions(client)
        assert len(ex) == 1 and ex[0]["subject_type"] == "lead" and ex[0]["lead_id"]

    def test_write_still_succeeds_when_automation_is_broken(self, client):
        client.mock_supabase.set_table_data("automation_flows", None)
        r = client.post("/api/tasks", json={"title": "x"})
        assert r.status_code == 201, r.text


def test_router_emitters_are_the_live_triggers():
    assert {"lead_created", "task_created", "client_created", "meeting_created",
            "task_completed", "pipeline_stage_entered"} <= automation_triggers.LIVE_TRIGGERS
