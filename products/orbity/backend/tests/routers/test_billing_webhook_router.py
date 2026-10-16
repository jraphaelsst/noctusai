"""POST /api/billing/webhook/asaas/{org_id}: fail-closed token auth, durable dedup, release-on-failure."""
import json

import pytest

ORG = "00000000-0000-0000-0000-000000000abc"
URL = f"/api/billing/webhook/asaas/{ORG}"
TOKEN = "s3cret-token"


def _body(event="PAYMENT_OVERDUE", **payment):
    return json.dumps({"id": "evt_1", "event": event, "payment": {"id": "pay_1", "externalReference": "orbity:x", **payment}})


def test_an_org_that_never_configured_the_token_accepts_nothing(client):
    resp = client.raw().post(URL, content=_body(), headers={"asaas-access-token": TOKEN})
    assert resp.status_code == 401


def test_a_wrong_token_is_401(client, monkeypatch):
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", TOKEN)
    resp = client.raw().post(URL, content=_body(), headers={"asaas-access-token": "nope"})
    assert resp.status_code == 401


def test_a_missing_token_header_is_401(client, monkeypatch):
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", TOKEN)
    assert client.raw().post(URL, content=_body()).status_code == 401


def test_the_org_in_the_url_must_be_a_uuid(client):
    assert client.raw().post("/api/billing/webhook/asaas/not-a-uuid", content=_body()).status_code == 422


def test_a_verified_event_that_needs_an_operator_is_acknowledged_as_ignored(client, monkeypatch):
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", TOKEN)
    resp = client.raw().post(URL, content=_body("PAYMENT_OVERDUE"), headers={"asaas-access-token": TOKEN})
    assert resp.status_code == 200 and resp.json() == {"status": "ignored", "kind": "charge_failed"}


def test_the_event_is_claimed_in_the_durable_inbox(client, monkeypatch):
    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", TOKEN)
    client.raw().post(URL, content=_body("PAYMENT_OVERDUE"), headers={"asaas-access-token": TOKEN})
    claimed = client.mock_supabase.table("payment_gateway_events").inserted_payloads
    assert [(c["gateway"], c["event_id"]) for c in claimed] == [("asaas", "evt_1")]
