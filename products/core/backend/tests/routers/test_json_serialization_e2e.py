"""
Router -> REAL write path -> MockSupabase: write payloads must be JSON-mode.

History (fleet sweep 2026-10-15): ``body.model_dump(exclude_none=True)``
left ``UUID``/``date``/``Decimal`` objects in the row and supabase-py raised
``TypeError: Object of type UUID is not JSON serializable`` -> live 502
(orbity POST /api/crm/leads). Core's write bodies are str-typed today, so the
bug is latent here; every router write dump now uses ``mode="json"`` so the
first UUID/date field added to a body cannot reintroduce it. These tests pin
that the payload that reaches the client survives the stdlib JSON encoder
(``MockSupabaseClient`` refuses non-serializable insert/update/upsert).
"""
import json


def test_create_subscription_payload_is_json(admin_client):
    mock_sb = admin_client.mock_supabase
    mock_sb.set_table_data("organizations", {"id": "org-1"})
    mock_sb.set_table_data("plans", {"id": "plan-1"})
    mock_sb.set_table_data("subscriptions", [
        {"id": "sub-new", "org_id": "org-1", "plan_id": "plan-1", "status": "active"},
    ])
    resp = admin_client.post("/api/subscriptions", json={
        "org_id": "org-1", "plan_id": "plan-1", "metadata": {"origem": "teste"},
    })
    assert resp.status_code == 200, resp.text
    inserted = mock_sb.table("subscriptions").inserted_payloads
    assert inserted, "the create never reached the client"
    assert json.loads(json.dumps(inserted[-1]))["metadata"] == {"origem": "teste"}


def test_update_plan_payload_is_json(admin_client):
    mock_sb = admin_client.mock_supabase
    mock_sb.set_table_data("plans", [{"id": "plan-1", "nome": "Old"}])
    resp = admin_client.patch("/api/plans/plan-1", json={"nome": "Novo", "price_monthly": 99.9})
    assert resp.status_code == 200, resp.text
    updated = mock_sb.table("plans").updated_payloads
    assert updated, "the update never reached the client"
    json.dumps(updated[-1])
