"""Operação admin routes — strict auth matrix + the happy paths.

Wiring is FastAPI's own `dependency_overrides` (trusted DB, session user,
the LLM / fleet readers); role checks and services run for real. The strict
401 tests override nothing auth-related.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.admin_operations import get_fleet_source, get_llm_source
from app.services.trusted_auth import get_session_user, get_trusted_db
from noctusai_lib.testing import MockSupabaseClient
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, OWNER_USER, seed_users

USERS = {"admin": ADMIN_USER, "owner": OWNER_USER, "member": MEMBER_USER}

ROUTES = [
    ("get", "/api/admin/operations/routines"),
    ("get", "/api/admin/operations/runs"),
    ("get", "/api/admin/operations/models"),
    ("get", "/api/admin/operations/costs"),
    ("get", "/api/admin/operations/briefs"),
    ("post", "/api/admin/operations/briefs"),
]


def _llm(db, start, end):
    return {"source": "test", "per_product": [], "per_org": None, "total_usd": 0.0, "calls": 0}


def _fleet():
    return [{"slug": "core", "state": "running", "health": "healthy", "running": True}]


def _db() -> MockSupabaseClient:
    db = MockSupabaseClient()
    seed_users(db)
    now = datetime.now(timezone.utc)
    for table in ("notifications", "owner_briefs", "cost_ledger", "organizations"):
        db.set_table_data(table, [])
    db.set_table_data("products", [{"slug": "social-wiring", "ativo": True}])
    db.set_table_data("scheduler_jobs", [
        {"product": "social-wiring", "job": "sw_tick", "cron": None, "interval_seconds": 300,
         "timezone": "America/Sao_Paulo", "misfire_grace_time": 30, "last_seen_at": (now - timedelta(days=1)).isoformat()},
    ])
    db.set_table_data("scheduler_runs", [
        {"product": "social-wiring", "job": "sw_tick", "status": "error", "error": "RuntimeError: x",
         "started_at": (now - timedelta(minutes=2)).isoformat(),
         "finished_at": (now - timedelta(minutes=2)).isoformat(), "duration_ms": 10, "alerted": True},
    ])
    return db


@pytest.fixture
def env():
    db = _db()
    state = SimpleNamespace(db=db, user="admin")

    async def session_user():
        return SimpleNamespace(id=USERS[state.user])

    app.dependency_overrides[get_trusted_db] = lambda: db
    app.dependency_overrides[get_session_user] = session_user
    app.dependency_overrides[get_llm_source] = lambda: _llm
    app.dependency_overrides[get_fleet_source] = lambda: _fleet
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


@pytest.fixture
def anon():
    db = _db()
    app.dependency_overrides[get_trusted_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method,url", ROUTES)
def test_no_token_is_401(anon, method, url):
    assert getattr(anon, method)(url).status_code == 401


@pytest.mark.parametrize("who", ["owner", "member"])
@pytest.mark.parametrize("method,url", ROUTES)
def test_non_platform_admins_are_403(env, who, method, url):
    env.user = who
    assert getattr(env.client, method)(url).status_code == 403
    assert env.db.table("owner_briefs").inserted_payloads == []


def test_routines_show_the_failure_and_the_missing_brief(env):
    resp = env.client.get("/api/admin/operations/routines")
    assert resp.status_code == 200
    data = resp.json()["data"]
    [product] = data["products"]
    assert product["product"] == "social-wiring" and product["failing"] == 1
    assert product["jobs"][0]["last_run"]["status"] == "error"
    assert data["brief"]["missing"] is True


def test_runs_are_filterable(env):
    resp = env.client.get("/api/admin/operations/runs", params={"status": "error", "product": "social-wiring"})
    assert resp.status_code == 200
    assert [r["job"] for r in resp.json()["data"]] == ["sw_tick"]
    assert env.client.get("/api/admin/operations/runs", params={"status": "bogus"}).status_code == 422


def test_models_list_the_seed_catalog(env):
    data = env.client.get("/api/admin/operations/models").json()["data"]
    assert any(m["id"] == "gpt-4o-mini" for m in data)


def test_costs_use_the_injected_llm_source(env):
    data = env.client.get("/api/admin/operations/costs").json()["data"]
    assert data["llm_yesterday"] == {"available": True, "error": None, **_llm(None, None, None)}


def test_a_manual_brief_is_stored_and_not_delivered_by_default(env):
    resp = env.client.post("/api/admin/operations/briefs")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["email_status"] == "not_sent" and body["in_app_sent"] == 0
    assert body["trigger"] == "manual" and body["id"] and "Brief diário" in body["text_body"]
    [row] = env.db.table("owner_briefs").inserted_payloads
    assert row["trigger"] == "manual"
    assert env.db.table("notifications").inserted_payloads == []
    history = env.client.get("/api/admin/operations/briefs").json()["data"]
    assert len(history) == 1 and history[0]["trigger"] == "manual"
