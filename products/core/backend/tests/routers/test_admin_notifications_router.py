"""Notificações admin routes — strict auth matrix + catalog/switch/ledger happy paths.

Wiring is FastAPI's `dependency_overrides` (trusted DB, session user); role checks and the service run for real.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.trusted_auth import get_session_user, get_trusted_db
from noctusai_lib.testing import MockSupabaseClient
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, OWNER_USER, seed_users

USERS = {"admin": ADMIN_USER, "owner": OWNER_USER, "member": MEMBER_USER}

ROUTES = [
    ("get", "/api/admin/notifications", None),
    ("get", "/api/admin/notifications/sends", None),
    ("post", "/api/admin/notifications/skill-scout", {"nome": "n", "resumo": "r"}),
    ("patch", "/api/admin/notifications/social-wiring", {"enabled": False}),
    ("patch", "/api/admin/notifications/social-wiring/lead", {"enabled": False}),
]


def _kind(kind: str, enabled: bool = True) -> dict:
    return {"product": "social-wiring", "kind": kind, "titulo": kind.title(), "descricao": "d", "gatilho": "g",
            "canais": ["whatsapp"], "enabled": enabled, "toggled_at": None, "toggled_by": None,
            "registered_at": None, "last_seen_at": None}


def _db() -> MockSupabaseClient:
    db = MockSupabaseClient()
    seed_users(db)
    now = datetime.now(timezone.utc)
    db.set_table_data("notification_kinds", [_kind("lead"), _kind("imoveis_delistados", enabled=False)])
    db.set_table_data("notification_sends", [
        {"id": 1, "product": "social-wiring", "kind": "lead", "org_id": None, "status": "sent", "recipients": 1,
         "delivered": 1, "reason": None, "created_at": (now - timedelta(hours=3)).isoformat()},
        {"id": 2, "product": "social-wiring", "kind": "lead", "org_id": None, "status": "failed", "recipients": 1,
         "delivered": 0, "reason": "sem_linha", "created_at": (now - timedelta(hours=1)).isoformat()},
        {"id": 3, "product": "social-wiring", "kind": "lead", "org_id": None, "status": "sent", "recipients": 1,
         "delivered": 1, "reason": None, "created_at": (now - timedelta(days=40)).isoformat()},
    ])
    return db


def _call(client, method, url, body):
    return getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)


@pytest.fixture
def env():
    db = _db()
    state = SimpleNamespace(db=db, user="admin")

    async def session_user():
        return SimpleNamespace(id=USERS[state.user])

    app.dependency_overrides[get_trusted_db] = lambda: db
    app.dependency_overrides[get_session_user] = session_user
    state.client = TestClient(app)
    yield state
    app.dependency_overrides.clear()


@pytest.fixture
def anon():
    db = _db()
    app.dependency_overrides[get_trusted_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method,url,body", ROUTES)
def test_no_token_is_401(anon, method, url, body):
    assert _call(anon, method, url, body).status_code == 401


@pytest.mark.parametrize("who", ["owner", "member"])
@pytest.mark.parametrize("method,url,body", ROUTES)
def test_non_platform_admins_are_403(env, who, method, url, body):
    env.user = who
    assert _call(env.client, method, url, body).status_code == 403
    assert all(r["enabled"] for r in env.db.table("notification_kinds").select("*").eq("kind", "lead").execute().data)


def test_catalog_groups_by_product_with_30_day_stats(env):
    resp = env.client.get("/api/admin/notifications")
    assert resp.status_code == 200
    data = resp.json()["data"]
    by_product = {g["product"]: g for g in data["products"]}
    group = by_product["social-wiring"]
    assert by_product["core"]["declared"] is False  # the platform shell is always listed, even before it registers kinds
    assert group["product"] == "social-wiring" and group["total"] == 2 and group["enabled_count"] == 1
    lead = next(k for k in group["kinds"] if k["kind"] == "lead")
    assert lead["counts_30d"]["sent"] == 1 and lead["counts_30d"]["failed"] == 1  # the 40-day-old send is outside
    assert lead["last_dispatch"]["status"] == "failed"
    assert lead["last_sent_at"] is not None


def test_switch_one_kind_off(env):
    resp = env.client.patch("/api/admin/notifications/social-wiring/lead", json={"enabled": False})
    assert resp.status_code == 200
    row = env.db.table("notification_kinds").select("*").eq("kind", "lead").execute().data[0]
    assert row["enabled"] is False and row["toggled_at"]


def test_switch_whole_product_on(env):
    resp = env.client.patch("/api/admin/notifications/social-wiring", json={"enabled": True})
    assert resp.status_code == 200
    rows = env.db.table("notification_kinds").select("*").execute().data
    assert all(r["enabled"] for r in rows)


def test_unknown_kind_is_404_and_bad_slug_422(env):
    assert env.client.patch("/api/admin/notifications/social-wiring/nope", json={"enabled": False}).status_code == 404
    assert env.client.patch("/api/admin/notifications/Bad Slug/lead", json={"enabled": False}).status_code == 422


def test_sends_ledger_filters(env):
    rows = env.client.get("/api/admin/notifications/sends", params={"product": "social-wiring", "kind": "lead"}).json()["data"]
    assert [r["id"] for r in rows][:2] == [2, 1]


def test_skill_scout_notice_is_accepted_and_reports_the_outcome(env):
    resp = env.client.post("/api/admin/notifications/skill-scout", json={"nome": "pdf-forms", "resumo": "Preenche PDFs."})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] in {"sent", "no_recipient", "failed", "suppressed", "partial"}


def test_skill_scout_notice_rejects_unknown_fields(env):
    assert env.client.post("/api/admin/notifications/skill-scout", json={"nome": "n", "resumo": "r", "canal": "email"}).status_code == 422
