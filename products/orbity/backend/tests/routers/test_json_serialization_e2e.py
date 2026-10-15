"""
Router -> REAL service -> MockSupabase regression: UUID / date fields must
reach the PostgREST client JSON-serializable.

History: ``payload.model_dump(exclude_none=True)`` left ``UUID`` objects in
the row and supabase-py raised ``TypeError: Object of type UUID is not JSON
serializable`` (POST /api/crm/leads -> 502 in prod). Router tests mocked the
services and service tests received pre-stringified dicts, so nothing caught
it. These tests drive the whole stack; ``MockSupabaseClient`` validates
JSON-serializability on insert/update/upsert (``_validate_json_serializable``).
"""
from uuid import uuid4


def _assert_ok(resp, expected=201):
    # The mock echoes a non-UUID row id, so the response_model may answer 422
    # AFTER the write succeeded. What matters here is that the write reached
    # the client (a serialization failure surfaces as 502 from the router).
    assert resp.status_code != 502, resp.text
    assert resp.status_code in (expected, 422), resp.text


class TestUuidPayloadsSerialize:
    def test_create_lead_with_stage_and_client_id(self, client):
        stage, cl = str(uuid4()), str(uuid4())
        resp = client.post(
            "/api/crm/leads",
            json={"name": "Lead", "stage_id": stage, "client_id": cl, "owner_id": str(uuid4())},
        )
        _assert_ok(resp)

    def test_update_lead_with_stage_id(self, client):
        resp = client.patch(f"/api/crm/leads/{uuid4()}", json={"stage_id": str(uuid4())})
        assert resp.status_code != 502 or "UUID" not in resp.text, resp.text
        assert resp.status_code in (200, 404), resp.text

    def test_create_contract_with_client_id(self, client):
        resp = client.post(
            "/api/financial/contracts",
            json={"client_id": str(uuid4()), "title": "C", "monthly_value": 100,
                  "start_date": "2026-01-01"},
        )
        _assert_ok(resp)

    def test_create_revenue_with_client_and_contract_id(self, client):
        resp = client.post(
            "/api/financial/revenues",
            json={"client_id": str(uuid4()), "contract_id": str(uuid4()),
                  "reference_month": "2026-01-01", "amount": 100, "due_date": "2026-01-10"},
        )
        _assert_ok(resp)

    def test_create_task_with_client_id(self, client):
        resp = client.post(
            "/api/tasks",
            json={"title": "T", "client_id": str(uuid4()),
                  "assignee_user_id": str(uuid4()), "due_date": "2026-02-01"},
        )
        _assert_ok(resp)

    def test_create_agenda_event_with_client_id(self, client):
        resp = client.post(
            "/api/agenda/events",
            json={"title": "E", "client_id": str(uuid4()),
                  "starts_at": "2026-02-01T10:00:00+00:00",
                  "ends_at": "2026-02-01T11:00:00+00:00",
                  "assignee_user_id": str(uuid4())},
        )
        _assert_ok(resp)

    def test_create_campaign_with_ad_account_id(self, client):
        resp = client.post(
            "/api/meta-ads/campaigns",
            json={"ad_account_id": str(uuid4()), "client_id": str(uuid4()),
                  "external_campaign_id": "x1", "name": "Camp"},
        )
        _assert_ok(resp)

    def test_create_scoring_rule(self, client):
        resp = client.post(
            "/api/crm/scoring-rules",
            json={"form_id": "f", "question": "q", "answer": "a", "score": 3},
        )
        _assert_ok(resp)
