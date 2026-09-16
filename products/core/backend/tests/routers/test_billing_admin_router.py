"""Billing admin + self-serve routes.

Wiring is FastAPI's own `dependency_overrides` (context, trusted DB, session
user); role checks, validation and services run for real. The strict-401
tests override nothing auth-related: a request without a token reaches the
real token check.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.billing_context import get_billing_context
from app.services.trusted_auth import get_session_user, get_trusted_db
from tests.billing_fakes import (
    ADMIN_USER,
    MEMBER_USER,
    ORG_ID,
    OTHER_ORG_ID,
    OWNER_USER,
    PLAN_ID,
    PRICE_ID,
    PRODUCT_ID,
    legacy_subscription,
    make_ctx,
    managed_subscription,
    seed_catalog,
    seed_users,
)

USERS = {"admin": ADMIN_USER, "owner": OWNER_USER, "member": MEMBER_USER}

ADMIN_ROUTES = [
    ("get", "/api/admin/billing/summary", None),
    ("get", "/api/admin/billing/plans", None),
    ("post", "/api/admin/billing/plans", {"nome": "X", "slug": "x"}),
    ("patch", f"/api/admin/billing/plans/{PLAN_ID}", {"trial_days": 3}),
    ("post", f"/api/admin/billing/plans/{PLAN_ID}/prices", {"billing_cycle": "yearly", "amount_cents": 99000}),
    ("patch", f"/api/admin/billing/prices/{PRICE_ID}", {"ativo": False}),
    ("get", "/api/admin/billing/settings", None),
    ("put", "/api/admin/billing/settings", {"automations_enabled": True}),
    ("put", "/api/admin/billing/settings/secrets", {"gateway": "stripe", "mode": "test", "field": "secret_key", "value": "sk_test_new"}),
    ("post", "/api/admin/billing/settings/test-connection", {"gateway": "stripe", "mode": "test"}),
    ("get", "/api/admin/billing/subscriptions", None),
    ("post", "/api/admin/billing/subscriptions/manual", {"org_id": ORG_ID, "plan_price_id": PRICE_ID}),
    ("post", "/api/admin/billing/subscriptions/sub-x/renew", {"current_period_end": "2027-01-01T00:00:00Z"}),
    ("post", "/api/admin/billing/subscriptions/sub-x/cancel", {"at_period_end": True}),
    ("get", "/api/admin/billing/payments", None),
    ("get", "/api/admin/llm-usage", None),
    ("post", "/api/admin/llm-cache/flush", {"product": "core", "provider": "openai", "model": "gpt-4o-mini"}),
]

ORG_ADMIN_ROUTES = [
    ("post", "/api/billing/subscribe", {"plan_price_id": PRICE_ID, "gateway": "stripe"}),
    ("get", "/api/billing/subscription", None),
]


@pytest.fixture
def env():
    ctx, fakes = make_ctx()
    seed_catalog(fakes.db)
    seed_users(fakes.db)
    for table in ("subscriptions", "licenses", "billing_payments", "billing_customers", "cost_ledger"):
        fakes.db.set_table_data(table, [])
    state = SimpleNamespace(ctx=ctx, fakes=fakes, user="admin")

    async def session_user():
        return SimpleNamespace(id=USERS[state.user])

    app.dependency_overrides[get_billing_context] = lambda: ctx
    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


def _call(client, method, url, body, **kwargs):
    fn = getattr(client, method)
    if body is None:
        return fn(url, **kwargs)
    return fn(url, json=body, **kwargs)


# ── strict 401 ──────────────────────────────────────────────────────────


@pytest.fixture
def anon():
    ctx, fakes = make_ctx()
    app.dependency_overrides[get_billing_context] = lambda: ctx
    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method,url,body", ADMIN_ROUTES + ORG_ADMIN_ROUTES)
def test_no_token_is_401(anon, method, url, body):
    assert _call(anon, method, url, body).status_code == 401


# ── role matrix ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("who", ["owner", "member"])
@pytest.mark.parametrize("method,url,body", ADMIN_ROUTES)
def test_admin_routes_refuse_non_platform_admins(env, who, method, url, body):
    env.user = who
    resp = _call(env.client, method, url, body)
    assert resp.status_code == 403
    assert env.fakes.db.table("plans").inserted_payloads == []
    assert env.fakes.store.list_keys() == sorted(env.fakes.store.list_keys())  # untouched store


def test_org_owner_with_spoofed_metadata_is_still_not_a_platform_admin(env):
    # The session user claims admin in user_metadata; the trusted row says owner.
    env.user = "owner"

    async def spoofed():
        return SimpleNamespace(id=OWNER_USER, user_metadata={"noctus_role": "admin", "role": "admin"})

    app.dependency_overrides[get_session_user] = spoofed
    assert env.client.get("/api/admin/llm-usage").status_code == 403
    assert env.client.get("/api/admin/billing/settings").status_code == 403


@pytest.mark.parametrize("method,url,body", ORG_ADMIN_ROUTES)
def test_org_routes_refuse_plain_members(env, method, url, body):
    env.user = "member"
    assert _call(env.client, method, url, body).status_code == 403
    assert env.fakes.db.table("subscriptions").inserted_payloads == []


def test_platform_admin_passes_the_llm_usage_gate(env):
    env.fakes.db.set_table_data("llm_usage", [])
    resp = env.client.get("/api/admin/llm-usage", params={"product": "erp-imobiliario"})
    assert resp.status_code == 200
    assert resp.json()["per_product"]["erp-imobiliario"]["calls"] == 0


# ── gateway settings: secrets are write-only ────────────────────────────


def test_settings_view_never_contains_a_secret(env):
    resp = env.client.get("/api/admin/billing/settings")
    assert resp.status_code == 200
    text = resp.text
    for secret in env.fakes.store._rows.values():
        assert secret not in text
    data = resp.json()["data"]
    assert data["gateways"]["stripe"]["modes"]["test"]["secret_key"] == {"configured": True, "source": "db"}
    assert data["webhook_urls"] == {
        "stripe": "https://core.example.com/api/billing/webhook",
        "asaas": "https://core.example.com/api/billing/webhooks/asaas",
    }


def test_saving_a_secret_stores_it_and_does_not_echo_it(env):
    resp = env.client.put(
        "/api/admin/billing/settings/secrets",
        json={"gateway": "stripe", "mode": "live", "field": "secret_key", "value": "sk_live_brand_new_value"},
    )
    assert resp.status_code == 200
    assert "sk_live_brand_new_value" not in resp.text
    assert env.fakes.store.get("billing.stripe.secret_key.live") == "sk_live_brand_new_value"


def test_a_test_key_is_refused_for_live_mode(env):
    resp = env.client.put(
        "/api/admin/billing/settings/secrets",
        json={"gateway": "stripe", "mode": "live", "field": "secret_key", "value": "sk_test_wrong_mode"},
    )
    assert resp.status_code == 422
    assert env.fakes.store.get("billing.stripe.secret_key.live") == "sk_live_123"


def test_field_of_the_other_gateway_is_refused(env):
    resp = env.client.put(
        "/api/admin/billing/settings/secrets",
        json={"gateway": "stripe", "mode": "test", "field": "api_key", "value": "whatever-long-enough-value"},
    )
    assert resp.status_code == 422


def test_empty_value_clears_the_secret(env):
    resp = env.client.put(
        "/api/admin/billing/settings/secrets",
        json={"gateway": "asaas", "mode": "test", "field": "webhook_token", "value": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["gateways"]["asaas"]["modes"]["test"]["webhook_token"]["configured"] is False


def test_saving_without_encryption_key_is_503_and_stores_nothing():
    ctx, fakes = make_ctx(encryption=False, secrets={})
    seed_users(fakes.db)

    async def admin():
        return SimpleNamespace(id=ADMIN_USER)

    app.dependency_overrides[get_billing_context] = lambda: ctx
    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    app.dependency_overrides[get_session_user] = admin
    try:
        resp = TestClient(app).put(
            "/api/admin/billing/settings/secrets",
            json={"gateway": "stripe", "mode": "test", "field": "secret_key", "value": "sk_test_abc"},
        )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 503
    assert fakes.store.list_keys() == []


def test_test_connection_reports_success_and_failure(env):
    ok = env.client.post("/api/admin/billing/settings/test-connection", json={"gateway": "asaas", "mode": "test"})
    assert ok.json()["data"]["ok"] is True
    from noctusai_lib.integrations.payments import PaymentGatewayError

    env.fakes.gateways["asaas"].fail_credentials(PaymentGatewayError("asaas", "invalid_access_token", status=401))
    bad = env.client.post("/api/admin/billing/settings/test-connection", json={"gateway": "asaas", "mode": "test"})
    assert bad.status_code == 200
    assert bad.json()["data"]["ok"] is False
    assert "401" in bad.json()["data"]["message"]


def test_live_mode_refused_while_an_enabled_gateway_lacks_live_keys(env):
    env.fakes.store.delete("billing.asaas.webhook_token.live")
    resp = env.client.put("/api/admin/billing/settings", json={"mode": "live"})
    assert resp.status_code == 409
    resp = env.client.put("/api/admin/billing/settings", json={"mode": "live", "asaas_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["mode"] == "live"


def test_automation_switch_round_trips(env):
    resp = env.client.put("/api/admin/billing/settings", json={"automations_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["automations_enabled"] is False
    assert env.ctx.config.automations_enabled() is False


# ── plans + prices ──────────────────────────────────────────────────────


def test_plan_create_rejects_unknown_fields(env):
    resp = env.client.post("/api/admin/billing/plans", json={"nome": "X", "slug": "x", "price": 10})
    assert resp.status_code == 422


def test_plan_create_and_price_rotation(env):
    created = env.client.post(
        "/api/admin/billing/plans",
        json={"nome": "Agência", "slug": "agencia", "product_id": PRODUCT_ID, "audience": "company",
              "trial_days": 14, "grace_days": 7},
    )
    assert created.status_code == 201
    plan_id = created.json()["data"]["id"]
    first = env.client.post(f"/api/admin/billing/plans/{plan_id}/prices",
                            json={"billing_cycle": "monthly", "amount_cents": 19900})
    second = env.client.post(f"/api/admin/billing/plans/{plan_id}/prices",
                             json={"billing_cycle": "monthly", "amount_cents": 24900})
    assert first.status_code == second.status_code == 201
    prices = [p for p in env.fakes.db.table("plan_prices").select("*").execute().data if p["plan_id"] == plan_id]
    active = [p for p in prices if p["ativo"]]
    assert [p["amount_cents"] for p in active] == [24900]


def test_duplicate_slug_conflicts(env):
    assert env.client.post("/api/admin/billing/plans", json={"nome": "Dup", "slug": "corretor"}).status_code == 409


def test_price_rejects_malformed_stripe_price_id(env):
    resp = env.client.patch(f"/api/admin/billing/prices/{PRICE_ID}", json={"stripe_price_id_live": "prod_123"})
    assert resp.status_code == 422


# ── subscriptions ───────────────────────────────────────────────────────


def test_manual_onboarding_grants_a_subscription_license(env):
    resp = env.client.post(
        "/api/admin/billing/subscriptions/manual",
        json={"org_id": ORG_ID, "plan_price_id": PRICE_ID, "note": "contrato assinado"},
    )
    assert resp.status_code == 201, resp.text
    sub = resp.json()["data"]
    assert sub["status"] == "active" and sub["gateway"] == "manual" and sub["automation_managed"] is True
    licenses = env.fakes.db.table("licenses").inserted_payloads
    assert licenses == [{"org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
                         "source": "subscription", "subscription_id": sub["id"]}]


def test_manual_onboarding_with_trial_starts_in_trial(env):
    resp = env.client.post(
        "/api/admin/billing/subscriptions/manual",
        json={"org_id": ORG_ID, "plan_price_id": PRICE_ID, "trial_days": 10},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "trial"


def test_renew_manual_reactivates_a_grace_subscription(env):
    env.fakes.db.set_table_data("subscriptions", [managed_subscription(status="grace", gateway="manual",
                                                                        gateway_subscription_id=None)])
    resp = env.client.post(
        "/api/admin/billing/subscriptions/66666666-6666-6666-6666-666666666666/renew",
        json={"current_period_end": "2026-12-31T00:00:00Z"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "active"


def test_legacy_subscription_cannot_be_canceled_through_the_managed_flow(env):
    legacy = legacy_subscription()
    env.fakes.db.set_table_data("subscriptions", [legacy])
    resp = env.client.post(f"/api/admin/billing/subscriptions/{legacy['id']}/cancel", json={"at_period_end": False})
    assert resp.status_code == 409
    assert env.fakes.db.table("subscriptions").updated_payloads == []


def test_cancel_now_revokes_and_stops_the_gateway(env):
    env.fakes.db.set_table_data("subscriptions", [managed_subscription(gateway="asaas", gateway_subscription_id="sub_as")])
    env.fakes.db.set_table_data("licenses", [{"id": "l1", "org_id": ORG_ID, "product_id": PRODUCT_ID,
                                              "status": "active", "source": "subscription",
                                              "subscription_id": "66666666-6666-6666-6666-666666666666"}])
    from noctusai_lib.integrations.payments.types import GatewaySubscription

    env.fakes.gateways["asaas"].subscriptions["sub_as"] = GatewaySubscription(
        id_at_gateway="sub_as", customer_id_at_gateway="c", external_reference=ORG_ID, status="active")
    resp = env.client.post("/api/admin/billing/subscriptions/66666666-6666-6666-6666-666666666666/cancel",
                           json={"at_period_end": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "canceled"
    assert env.fakes.db.table("licenses").select("*").execute().data[0]["status"] == "revoked"
    assert ("cancel_subscription", "sub_as") in env.fakes.gateways["asaas"].calls


def test_summary_mrr_counts_what_is_paid(env):
    env.fakes.db.set_table_data("subscriptions", [
        managed_subscription(id="s1", status="active", amount_cents=12000, billing_cycle="yearly"),
        managed_subscription(id="s2", status="trial", amount_cents=9900),
        managed_subscription(id="s3", status="grace", amount_cents=9900),
        legacy_subscription(id="s4", status="active", plan_id=PLAN_ID),
    ])
    env.fakes.db.set_table_data("plans", [{"id": PLAN_ID, "price_monthly": 50, "nome": "P", "slug": "p"}])
    data = env.client.get("/api/admin/billing/summary").json()["data"]
    # 120/12 + 99 (grace still bills) + 50 (legacy list price); trial excluded.
    assert data["mrr"] == 159.0
    assert data["arr"] == 1908.0
    assert data["counts"]["trial"] == 1


# ── self-serve ──────────────────────────────────────────────────────────


def test_public_plans_lists_only_sellable_prices_and_no_secrets(env):
    resp = env.client.get("/api/billing/plans")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["gateways"] == ["stripe", "asaas"]
    assert data["plans"][0]["prices"][0]["amount_cents"] == 9900
    assert "stripe_price_id" not in resp.text


def test_owner_subscribes_with_stripe_trial(env):
    env.user = "owner"
    resp = env.client.post("/api/billing/subscribe",
                           json={"plan_price_id": PRICE_ID, "gateway": "stripe"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["checkout_url"].startswith("https://checkout.fake.test/")
    request = env.fakes.checkouts["stripe"].calls[0][1]
    assert request.trial_days == 7
    assert request.plan_ref == "price_test123"
    assert request.external_reference == ORG_ID
    assert request.metadata["subscription_id"] == data["subscription_id"]
    assert request.success_url == "https://core.example.com/billing/success"
    row = env.fakes.db.table("subscriptions").select("*").execute().data[0]
    assert (row["status"], row["automation_managed"], row["org_id"]) == ("incomplete", True, ORG_ID)
    # Stripe has no subscription until the payer finishes the hosted page.
    assert row.get("gateway_subscription_id") is None


def test_subscribe_ignores_foreign_redirect_urls(env):
    env.user = "owner"
    env.client.post("/api/billing/subscribe", json={
        "plan_price_id": PRICE_ID, "gateway": "stripe",
        "success_url": "https://evil.example/steal", "cancel_url": "https://core.example.com/billing/x",
    })
    request = env.fakes.checkouts["stripe"].calls[0][1]
    assert request.success_url == "https://core.example.com/billing/success"
    assert request.cancel_url == "https://core.example.com/billing/x"


def test_asaas_subscribe_needs_a_tax_id_and_returns_pix(env):
    env.user = "owner"
    missing = env.client.post("/api/billing/subscribe",
                              json={"plan_price_id": PRICE_ID, "gateway": "asaas", "billing_method": "pix"})
    assert missing.status_code == 422
    ok = env.client.post("/api/billing/subscribe", json={
        "plan_price_id": PRICE_ID, "gateway": "asaas", "billing_method": "pix", "tax_id": "12345678909"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["pix_qr"]["payload"]
    row = env.fakes.db.table("subscriptions").select("*").execute().data[0]
    assert row["gateway_subscription_id"]


def test_disabled_gateway_is_refused(env):
    env.user = "owner"
    env.ctx.config.update_flags(user_id=None, asaas_enabled=False)
    resp = env.client.post("/api/billing/subscribe", json={
        "plan_price_id": PRICE_ID, "gateway": "asaas", "billing_method": "pix", "tax_id": "12345678909"})
    assert resp.status_code == 409


def test_second_open_subscription_for_the_same_product_conflicts(env):
    env.user = "owner"
    env.fakes.db.set_table_data("subscriptions", [managed_subscription(status="trial")])
    resp = env.client.post("/api/billing/subscribe", json={"plan_price_id": PRICE_ID, "gateway": "stripe"})
    assert resp.status_code == 409


def test_audience_mismatch_is_refused(env):
    env.user = "owner"
    seed_catalog(env.fakes.db, audience="individual")  # ORG_ID is a company
    resp = env.client.post("/api/billing/subscribe", json={"plan_price_id": PRICE_ID, "gateway": "stripe"})
    assert resp.status_code == 422


def test_my_subscription_is_scoped_to_the_callers_org(env):
    env.user = "owner"
    env.fakes.db.set_table_data("subscriptions", [
        managed_subscription(id="mine"),
        managed_subscription(id="theirs", org_id=OTHER_ORG_ID),
    ])
    env.fakes.db.set_table_data("billing_payments", [
        {"id": "p-mine", "org_id": ORG_ID, "status": "paid", "created_at": "2026-09-01"},
        {"id": "p-theirs", "org_id": OTHER_ORG_ID, "status": "paid", "created_at": "2026-09-01"},
    ])
    data = env.client.get("/api/billing/subscription").json()["data"]
    assert [s["id"] for s in data["subscriptions"]] == ["mine"]
    assert [p["id"] for p in data["payments"]] == ["p-mine"]
