"""Quem recebe os avisos do dono — /api/admin/notifications/recipients + /owner-line.

Auth matrix is strict (401 without a token, 403 for non-platform-admins); the service runs for real against the
mock client (the event trigger is DB-side: covered by the migration shape test + the PGlite replay).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.trusted_auth import get_session_user, get_trusted_db
from noctusai_lib.testing import MockSupabaseClient
from tests.billing_fakes import ADMIN_USER, MEMBER_USER, OWNER_USER, seed_users

USERS = {"admin": ADMIN_USER, "owner": OWNER_USER, "member": MEMBER_USER}
BASE = "/api/admin/notifications"
SOME_ID = "11111111-1111-1111-1111-111111111111"

ROUTES = [
    ("get", f"{BASE}/recipients", None),
    ("post", f"{BASE}/recipients", {"numero": "+5511999999999"}),
    ("patch", f"{BASE}/recipients/{SOME_ID}", {"ativo": False}),
    ("delete", f"{BASE}/recipients/{SOME_ID}", None),
    ("get", f"{BASE}/owner-line", None),
]


def _call(client, method, url, body):
    return getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)


@pytest.fixture
def env():
    db = MockSupabaseClient()
    seed_users(db)
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
    app.dependency_overrides[get_trusted_db] = lambda: MockSupabaseClient()
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
    assert env.db.table("notification_owner_recipients").select("*").execute().data in ([], None)


def test_add_normalizes_and_lists(env):
    r = env.client.post(f"{BASE}/recipients", json={"numero": "(11) 99999-9999", "nome": " Dono "})
    assert r.status_code == 201
    item = r.json()["data"]
    assert item["numero"] == "+5511999999999" and item["nome"] == "Dono" and item["ativo"] is True
    assert set(item) == {"id", "numero", "nome", "ativo", "created_at"}
    stored = env.db.table("notification_owner_recipients").select("*").execute().data[0]
    assert stored["alterado_por"] == ADMIN_USER
    listing = env.client.get(f"{BASE}/recipients")
    assert listing.status_code == 200
    assert [i["numero"] for i in listing.json()["data"]["items"]] == ["+5511999999999"]


@pytest.mark.parametrize("bad", ["abc", "123", "+0000"])
def test_invalid_number_is_422(env, bad):
    r = env.client.post(f"{BASE}/recipients", json={"numero": bad})
    assert r.status_code == 422
    assert r.json()["code"] == "numero_invalido"


def test_duplicate_number_is_409_even_in_another_spelling(env):
    assert env.client.post(f"{BASE}/recipients", json={"numero": "+5511999999999"}).status_code == 201
    r = env.client.post(f"{BASE}/recipients", json={"numero": "11 99999-9999"})
    assert r.status_code == 409
    assert r.json()["code"] == "numero_duplicado"


def test_patch_toggles_and_renames(env):
    rid = env.client.post(f"{BASE}/recipients", json={"numero": "+5511999999999"}).json()["data"]["id"]
    r = env.client.patch(f"{BASE}/recipients/{rid}", json={"ativo": False})
    assert r.status_code == 200 and r.json()["data"]["ativo"] is False
    r = env.client.patch(f"{BASE}/recipients/{rid}", json={"nome": "Sócio"})
    assert r.json()["data"]["nome"] == "Sócio" and r.json()["data"]["ativo"] is False


def test_patch_unknown_is_404(env):
    r = env.client.patch(f"{BASE}/recipients/{SOME_ID}", json={"ativo": True})
    assert r.status_code == 404
    assert r.json()["code"] == "destinatario_nao_encontrado"


def test_patch_rejects_unknown_fields(env):
    rid = env.client.post(f"{BASE}/recipients", json={"numero": "+5511999999999"}).json()["data"]["id"]
    assert env.client.patch(f"{BASE}/recipients/{rid}", json={"numero": "+5511888888888"}).status_code == 422


def test_delete_is_204_then_404(env):
    rid = env.client.post(f"{BASE}/recipients", json={"numero": "+5511999999999"}).json()["data"]["id"]
    assert env.client.delete(f"{BASE}/recipients/{rid}").status_code == 204
    assert env.client.get(f"{BASE}/recipients").json() == {"data": {"items": []}}
    again = env.client.delete(f"{BASE}/recipients/{rid}")
    assert again.status_code == 404
    assert again.json()["code"] == "destinatario_nao_encontrado"


def test_owner_line_unconfigured(env, monkeypatch):
    monkeypatch.delenv("NOC_OWNER_LINE_WAHA_URL", raising=False)
    r = env.client.get(f"{BASE}/owner-line")
    assert r.status_code == 200 and r.json() == {"data": {"configurada": False, "instancia": None}}


def test_owner_line_configured_shows_host_only(env, monkeypatch):
    monkeypatch.setenv("NOC_OWNER_LINE_WAHA_URL", "http://waha-noc:3000/some/path")
    assert env.client.get(f"{BASE}/owner-line").json() == {"data": {"configurada": True, "instancia": "waha-noc:3000"}}


def test_existing_switch_routes_still_resolve(env):
    # `recipients` / `owner-line` must not be swallowed by `/{product}` (and vice versa).
    assert env.client.get(f"{BASE}").status_code == 200
