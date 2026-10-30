"""`/api/admin/llm-usage` reads the central `public.ai_usage` ledger (D25).

No product→schema map any more: every product's calls are in one table, rolled
up per org → per product → per feature. Auth runs for real (strict 401 without
a token, 403 for a non-platform-admin); only the trusted DB + session user are
supplied through FastAPI's own `dependency_overrides`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.trusted_auth import get_session_user, get_trusted_db
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, ORG_ID, OTHER_ORG_ID, make_ctx, seed_users

URL = "/api/admin/llm-usage"
WHEN = "2026-10-20T12:00:00+00:00"


def _row(i, org, product, feature, cost, *, status="ok", model="claude-sonnet-5"):
    return {
        "id": i, "created_at": WHEN, "org_id": org, "product": product, "feature": feature,
        "provider": "anthropic", "model": model, "operation": "chat",
        "input_tokens": 100, "output_tokens": 10, "cost_usd": cost, "cost_brl": cost * 5.5,
        "status": status,
    }


ROWS = [
    _row(1, ORG_ID, "social-wiring", "julia.reply", 0.30),
    _row(2, ORG_ID, "social-wiring", "julia.reply", 0.20),
    _row(3, ORG_ID, "social-wiring", "POST /api/docs/{id}/extract", 0.10, status="error"),
    _row(4, ORG_ID, "agents", "studio.generate", 1.00),
    _row(5, OTHER_ORG_ID, "social-wiring", "julia.reply", 0.05, status="partial"),
]


@pytest.fixture
def env():
    _ctx, fakes = make_ctx()
    seed_users(fakes.db)
    fakes.db.set_table_data("ai_usage", [dict(r) for r in ROWS])
    state = SimpleNamespace(fakes=fakes, user=ADMIN_USER)

    async def session_user():
        return SimpleNamespace(id=state.user)

    app.dependency_overrides[get_trusted_db] = lambda: fakes.db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


def test_no_token_is_strictly_401():
    app.dependency_overrides.clear()
    assert TestClient(app).get(URL).status_code == 401


def test_non_platform_admin_is_403(env):
    env.user = MEMBER_USER
    assert env.client.get(URL, params={"from": "2026-10-01", "to": "2026-10-31"}).status_code == 403


def test_rolls_up_per_org_per_product_per_feature(env):
    resp = env.client.get(URL, params={"from": "2026-10-01", "to": "2026-10-31"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["calls"] == 5
    assert body["totals"]["errors"] == 1 and body["totals"]["partial"] == 1
    assert body["totals"]["cost_usd"] == pytest.approx(1.65)
    assert body["totals"]["cost_brl"] == pytest.approx(1.65 * 5.5)

    org = next(o for o in body["per_org"] if o["org_id"] == ORG_ID)
    assert [p["product"] for p in org["per_product"]] == ["agents", "social-wiring"]  # cost desc
    sw = org["per_product"][1]
    assert sw["calls"] == 3 and sw["cost_usd"] == pytest.approx(0.60)
    reply = next(f for f in sw["per_feature"] if f["feature"] == "julia.reply")
    assert reply["calls"] == 2 and reply["cost_usd"] == pytest.approx(0.50)
    assert sw["by_model"][0]["model"] == "claude-sonnet-5"

    assert body["per_product"]["social-wiring"]["calls"] == 4  # summed across orgs
    assert body["per_product"]["agents"]["cost_usd"] == pytest.approx(1.00)


def test_filters_by_org_and_product(env):
    resp = env.client.get(
        URL, params={"from": "2026-10-01", "to": "2026-10-31", "org_id": ORG_ID, "product": "social-wiring"}
    )
    body = resp.json()
    assert body["totals"]["calls"] == 3
    assert [o["org_id"] for o in body["per_org"]] == [ORG_ID]


def test_an_unknown_product_is_an_empty_bucket_not_a_400(env):
    resp = env.client.get(URL, params={"product": "brand-new-product"})
    assert resp.status_code == 200
    assert resp.json()["per_product"]["brand-new-product"]["calls"] == 0


def test_window_outside_rows_is_empty(env):
    body = env.client.get(URL, params={"from": "2025-01-01", "to": "2025-01-31"}).json()
    assert body["totals"]["calls"] == 0 and body["per_org"] == []


def test_inverted_window_is_400(env):
    assert env.client.get(URL, params={"from": "2026-10-31", "to": "2026-10-01"}).status_code == 400
