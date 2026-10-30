"""AI credit routes — org (`/api/credits/*`) + platform admin (`/api/admin/credits/*`).

Wiring is `dependency_overrides` only (context, trusted DB, session user); role
checks, validation and services run for real. Strict 401: nothing auth-related
is overridden, so the request reaches the real token check.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.billing_context import get_billing_context
from app.services.trusted_auth import get_session_user, get_trusted_db
from tests.billing_fakes import ASAAS_TOKEN_TEST, MEMBER_USER, asaas_event
from tests.credits_fakes import ADMIN_USER, ORG_ID, OTHER_ORG_ID, OWNER_USER, credits_ctx, usage_row, wallet_row

USERS = {"admin": ADMIN_USER, "owner": OWNER_USER, "member": MEMBER_USER}
UNKNOWN_ORG = "99999999-9999-9999-9999-999999999999"

ORG_ROUTES = [
    ("get", "/api/credits/wallet", None),
    ("get", "/api/credits/usage", None),
    ("post", "/api/credits/purchase", {"amount_brl": "100", "gateway": "asaas", "billing_method": "pix",
                                        "tax_id": "12345678909"}),
]
ADMIN_ROUTES = [
    ("get", "/api/admin/credits/wallets", None),
    ("get", "/api/admin/credits/pricing", None),
    ("post", "/api/admin/credits/pricing", {"credit_unit_brl": "0.01", "margin": "1.2", "iof_rate": "0.035",
                                            "simples_rate": "0.06", "gateway_fee_rate": "0.0399"}),
    ("get", "/api/admin/credits/margin", None),
    ("get", f"/api/admin/credits/{ORG_ID}", None),
    ("get", f"/api/admin/credits/{ORG_ID}/grant", None),
    ("post", f"/api/admin/credits/{ORG_ID}/grant", {"credits": "1000", "reason": "teste"}),
    ("post", f"/api/admin/credits/{ORG_ID}/adjustments", {"credits": "-5", "reason": "correção"}),
    ("put", f"/api/admin/credits/{ORG_ID}/wallet", {"mode": "postpaid_trusted"}),
]


@pytest.fixture
def env():
    ctx, fakes = credits_ctx()
    state = SimpleNamespace(ctx=ctx, fakes=fakes, user="admin")

    async def session_user():
        return SimpleNamespace(id=USERS[state.user])

    app.dependency_overrides[get_billing_context] = lambda: ctx
    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


def _call(client, method, url, body):
    fn = getattr(client, method)
    return fn(url) if body is None else fn(url, json=body)


@pytest.mark.parametrize("method,url,body", ORG_ROUTES + ADMIN_ROUTES)
def test_no_token_is_strictly_401(method, url, body):
    app.dependency_overrides.clear()
    assert _call(TestClient(app), method, url, body).status_code == 401


@pytest.mark.parametrize("method,url,body", ADMIN_ROUTES)
def test_admin_routes_refuse_an_org_owner(env, method, url, body):
    env.user = "owner"
    assert _call(env.client, method, url, body).status_code == 403


@pytest.mark.parametrize("method,url,body", ORG_ROUTES)
def test_org_routes_refuse_a_plain_member(env, method, url, body):
    env.user = "member"
    assert _call(env.client, method, url, body).status_code == 403


@pytest.mark.parametrize("method,url,body", [r for r in ADMIN_ROUTES if ORG_ID in r[1]])
def test_admin_unknown_org_is_404(env, method, url, body):
    assert _call(env.client, method, url.replace(ORG_ID, UNKNOWN_ORG), body).status_code == 404
    assert env.fakes.db.table("credit_wallets").select("*").execute().data == []


def test_org_sees_only_its_own_wallet_and_usage(env):
    db = env.fakes.db
    db.set_table_data("credit_wallets", [wallet_row(balance_credits=500), wallet_row(OTHER_ORG_ID, balance_credits=9999)])
    db.set_table_data("ai_usage", [usage_row(1), usage_row(2, org_id=OTHER_ORG_ID, product="segredo")])
    env.user = "owner"
    wallet = env.client.get("/api/credits/wallet").json()["data"]
    assert wallet["wallet"]["balance_credits"] == 500
    usage = env.client.get("/api/credits/usage", params={"from": "2026-09-01T00:00:00Z"}).json()["data"]
    assert usage["products"] == ["erp-imobiliario"]
    assert "segredo" not in json.dumps(usage)


def test_admin_grant_then_org_sees_the_balance(env):
    resp = env.client.post(f"/api/admin/credits/{ORG_ID}/grant", json={"usd": "100", "reason": "US$100 teste"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["credits"] == 50000.0
    env.user = "owner"
    wallet = env.client.get("/api/credits/wallet").json()["data"]
    assert wallet["wallet"]["balance_credits"] == 50000
    assert wallet["entries"][0]["kind"] == "grant"


def test_grant_needs_exactly_one_amount(env):
    resp = env.client.post(f"/api/admin/credits/{ORG_ID}/grant",
                           json={"usd": "1", "credits": "1", "reason": "x x"})
    assert resp.status_code == 422


def test_wallet_mode_and_pricing_versions(env):
    resp = env.client.put(f"/api/admin/credits/{ORG_ID}/wallet", json={"mode": "byok"})
    assert resp.status_code == 200 and resp.json()["data"]["mode"] == "byok"
    resp = env.client.post("/api/admin/credits/pricing", json={
        "credit_unit_brl": "0.01", "margin": "1.5", "iof_rate": "0.035", "simples_rate": "0.06",
        "gateway_fee_rate": "0.0399"})
    assert resp.status_code == 200
    assert [v["version"] for v in resp.json()["data"]][:2] == [2, 1]


def test_purchase_then_paid_asaas_webhook_credits_the_wallet(env):
    env.user = "owner"
    resp = env.client.post("/api/credits/purchase", json={
        "amount_brl": "50", "gateway": "asaas", "billing_method": "pix", "tax_id": "12345678909"})
    assert resp.status_code == 200, resp.text
    purchase_id = resp.json()["data"]["purchase_id"]
    env.fakes.db.set_table_data("payment_events", [])
    body = asaas_event("evt_cred_1", "PAYMENT_RECEIVED", payment={
        "id": "pay_cred_1", "externalReference": f"credits:{purchase_id}", "value": 50.0,
        "billingType": "PIX", "paymentDate": "2026-09-16"})
    hook = env.client.post("/api/billing/webhooks/asaas", content=body,
                           headers={"asaas-access-token": ASAAS_TOKEN_TEST, "content-type": "application/json"})
    assert hook.status_code == 200, hook.text
    assert hook.json()["status"] == "processed"
    wallet = env.client.get("/api/credits/wallet").json()["data"]["wallet"]
    assert wallet["balance_credits"] == 5000
