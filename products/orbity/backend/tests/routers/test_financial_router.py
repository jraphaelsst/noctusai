"""/api/financial -- the Orbity layer over the seed finance + contracts organs.

Strict ``== 401`` on every route (a ``in (401, 404)`` would pass on a route that does not exist), member -> 403 on the
writes, and the happy paths over ``MockSupabaseClient`` seeded rows. The money model itself (/api/finance, /api/contracts)
is the seed organs' and is covered by their suites + ``tests/test_billing_wiring.py``.
"""
import pytest
from noctusai_lib.testing import TEST_USER_ID

from app.dependencies import coerce_org_uuid

ORG = str(coerce_org_uuid("test-org-123"))
ENTRY = "e1000000-0000-4000-8000-000000000001"
CLIENT = "c1000000-0000-4000-8000-000000000001"

READS = [
    ("GET", "/api/financial/gateway"),
    ("GET", "/api/financial/cash-flow/2026-10-01"),
    ("GET", "/api/financial/charges"),
]
WRITES = [
    ("POST", "/api/financial/charges"),
    ("POST", f"/api/financial/charges/{ENTRY}/generate"),
]


def make_admin(client):
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": "test-org-123", "org_role": "owner", "role": "user"}])


@pytest.mark.parametrize("method,path", READS + WRITES)
def test_every_route_is_strictly_401_without_auth(client, method, path):
    resp = client.raw().request(method, path, json={} if method == "POST" else None)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path", WRITES)
def test_a_plain_member_cannot_write(client, method, path):
    resp = client.post(path, json={"client_id": CLIENT, "description": "x", "amount_cents": 100, "due_date": "2026-10-20"})
    assert resp.status_code == 403


def test_the_removed_crud_surface_is_gone(client):
    # contracts / expenses / revenues CRUD moved to the organs (/api/contracts, /api/finance): the old paths must 404, not linger.
    for path in ("/api/financial/contracts", "/api/financial/expenses", "/api/financial/revenues"):
        assert client.get(path).status_code in (404, 405)


def test_cash_flow_rejects_a_month_that_is_not_a_month(client):
    assert client.get("/api/financial/cash-flow/banana").status_code == 422


def test_cash_flow_answers_the_summary_shape(client):
    client.mock_supabase.set_table_data("fin_entries", [])
    resp = client.get("/api/financial/cash-flow/2026-10-01")
    assert resp.status_code == 200
    assert resp.json() == {"reference_month": "2026-10-01", "paid_revenues": 0.0, "paid_expenses": 0.0, "net": 0.0,
                           "pending_revenues": 0.0, "overdue_revenues": 0.0}


def test_gateway_status_is_honest_when_nothing_is_configured(client):
    resp = client.get("/api/financial/gateway")
    assert resp.status_code == 200 and resp.json() == {"gateway": "asaas", "configured": False}


def test_charges_list_joins_the_entry_the_client_and_the_gateway_state(client):
    db = client.mock_supabase
    db.set_table_data("billing_charges", [{
        "id": "ch-1", "org_id": ORG, "entry_id": ENTRY, "client_id": CLIENT, "contract_id": None, "generation_status": "retrying",
        "generation_attempts": 2, "last_error": "timeout calling /payments", "next_attempt_at": "2026-10-16T13:00:00+00:00",
        "gateway": "asaas", "billing_method": "pix", "external_id": None, "invoice_url": None, "pix_payload": None,
        "preserved_after_deactivation": True, "gateway_cancel_status": None, "gateway_cancel_error": None,
        "created_at": "2026-10-01T00:00:00+00:00"}])
    db.set_table_data("fin_entries", [{"id": ENTRY, "org_id": ORG, "direction": "receivable", "status": "open", "description": "Gestão — 10/2026",
                                       "amount_cents": 150_000, "settled_cents": 0, "due_date": "2020-01-01"}])
    db.set_table_data("clients", [{"id": CLIENT, "org_id": ORG, "name": "Acme", "legal_name": "Acme LTDA"}])
    resp = client.get("/api/financial/charges")
    assert resp.status_code == 200
    (item,) = resp.json()["items"]
    assert item["client_name"] == "Acme LTDA" and item["generation_status"] == "retrying" and item["last_error"].startswith("timeout")
    assert item["overdue"] is True and item["preserved_after_deactivation"] is True and item["amount_cents"] == 150_000


def test_charges_list_filters_validate(client):
    assert client.get("/api/financial/charges?generation_status=banana").status_code == 422
    assert client.get("/api/financial/charges?page_size=999").status_code == 422


def test_an_admin_requeues_nothing_for_an_unknown_charge(client):
    make_admin(client)
    client.mock_supabase.set_table_data("billing_charges", [])
    assert client.post(f"/api/financial/charges/{ENTRY}/generate").status_code == 404


def test_an_admin_cannot_queue_a_charge_without_a_gateway(client):
    make_admin(client)
    client.mock_supabase.set_table_data("billing_charges", [{
        "id": "ch-1", "org_id": ORG, "entry_id": ENTRY, "client_id": CLIENT, "generation_status": "skipped",
        "created_at": "2026-10-01T00:00:00+00:00"}])
    client.mock_supabase.set_table_data("fin_entries", [{"id": ENTRY, "org_id": ORG, "status": "open"}])
    client.mock_supabase.set_table_data("clients", [{"id": CLIENT, "org_id": ORG, "default_billing_type": "boleto", "billing_automation_enabled": True}])
    resp = client.post(f"/api/financial/charges/{ENTRY}/generate")
    assert resp.status_code == 409 and "não configurado" in resp.text


def test_extra_charge_validation(client):
    make_admin(client)
    base = {"client_id": CLIENT, "description": "Setup", "amount_cents": 1000, "due_date": "2026-10-20"}
    assert client.post("/api/financial/charges", json={**base, "amount_cents": 0}).status_code == 422
    assert client.post("/api/financial/charges", json={**base, "description": ""}).status_code == 422
    assert client.post("/api/financial/charges", json={**base, "surprise": 1}).status_code == 422
    client.mock_supabase.set_table_data("clients", [])
    assert client.post("/api/financial/charges", json=base).status_code == 404
