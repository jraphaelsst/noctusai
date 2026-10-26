"""HTTP surface -- both stores. Auth is strictly 401; every route is org-scoped."""
from __future__ import annotations

import pytest

from .conftest import CFG

ROUTES = [
    ("get", "/api/leads"),
    ("post", "/api/leads"),
    ("get", "/api/leads/board"),
    ("get", "/api/leads/config"),
    ("get", "/api/leads/00000000-0000-4000-8000-000000000009"),
    ("patch", "/api/leads/00000000-0000-4000-8000-000000000009"),
    ("delete", "/api/leads/00000000-0000-4000-8000-000000000009"),
    ("post", "/api/leads/00000000-0000-4000-8000-000000000009/move"),
]


@pytest.mark.parametrize("method, path", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path):
    assert getattr(h.client, method)(path, json={}).status_code == 401 if method in ("post", "patch") else getattr(h.client, method)(path).status_code == 401


def test_config_exposes_stages_and_origins_as_data(h):
    data = h.client.get("/api/leads/config", headers=h.a()).json()["data"]
    assert [s["slug"] for s in data["stages"]] == list(CFG.stage_slugs)
    assert data["stages"][1]["label"] == "Atendimento" and data["origins"][2]["label"] == "Indicação"


def test_crud_roundtrip(h):
    c = h.client.post("/api/leads", json={"name": "Ana", "phone": "(11) 99457-3387"}, headers=h.a())
    assert c.status_code == 201
    lead = c.json()["data"]
    assert lead["phone"] == "+5511994573387" and lead["stage"] == "lead"
    assert h.client.get(f"/api/leads/{lead['id']}", headers=h.a()).json()["data"]["name"] == "Ana"
    p = h.client.patch(f"/api/leads/{lead['id']}", json={"name": "Ana Souza", "phone": ""}, headers=h.a())
    assert p.json()["data"]["name"] == "Ana Souza" and p.json()["data"]["phone"] is None
    assert h.client.delete(f"/api/leads/{lead['id']}", headers=h.a()).status_code == 204
    assert h.client.get(f"/api/leads/{lead['id']}", headers=h.a()).status_code == 404


def test_validation_errors_use_the_error_envelope(h):
    r = h.client.post("/api/leads", json={"name": "x", "origin": "tv"}, headers=h.a())
    assert r.status_code == 422 and r.json()["error"]["code"] == "origem_invalida"
    assert h.client.post("/api/leads", json={}, headers=h.a()).status_code == 422
    assert h.client.post("/api/leads", json={"name": "x", "phone": "12"}, headers=h.a()).json()["error"]["code"] == "telefone_invalido"


def test_other_org_cannot_see_touch_or_move(h):
    lead = h.client.post("/api/leads", json={"name": "Ana"}, headers=h.a()).json()["data"]
    assert h.client.get("/api/leads", headers=h.b()).json()["data"] == []
    for method, path, body in (("get", "", None), ("patch", "", {"name": "x"}), ("delete", "", None), ("post", "/move", {"stage": "fechado", "position": 0})):
        kw = {"json": body} if body is not None else {}
        assert getattr(h.client, method)(f"/api/leads/{lead['id']}{path}", headers=h.b(), **kw).status_code == 404
    assert all(len(col["cards"]) == 0 for col in h.client.get("/api/leads/board", headers=h.b()).json()["data"])


def test_list_filters_and_cursor(h):
    for i in range(5):
        h.client.post("/api/leads", json={"name": f"L{i}", "origin": "instagram" if i % 2 else "whatsapp"}, headers=h.a())
    r = h.client.get("/api/leads", params={"origin": "instagram", "limit": 1}, headers=h.a()).json()
    assert len(r["data"]) == 1 and r["next_cursor"] == "1"
    r2 = h.client.get("/api/leads", params={"origin": "instagram", "limit": 1, "cursor": "1"}, headers=h.a()).json()
    assert len(r2["data"]) == 1 and r2["next_cursor"] is None and r2["data"][0]["id"] != r["data"][0]["id"]
    assert h.client.get("/api/leads", params={"cursor": "abc"}, headers=h.a()).status_code == 422
    assert h.client.get("/api/leads", params={"from": "2030-01-01", "to": "2029-01-01"}, headers=h.a()).status_code == 422


def test_date_range_is_inclusive_of_the_whole_end_day(h):
    h.client.post("/api/leads", json={"name": "Dia", "first_contact_at": "2026-03-10T23:30:00+00:00"}, headers=h.a())
    got = h.client.get("/api/leads", params={"from": "2026-03-10", "to": "2026-03-10"}, headers=h.a()).json()["data"]
    assert [x["name"] for x in got] == ["Dia"]
    assert h.client.get("/api/leads", params={"from": "2026-03-11"}, headers=h.a()).json()["data"] == []


def test_board_and_move_endpoint(h):
    ids = [h.client.post("/api/leads", json={"name": n}, headers=h.a()).json()["data"]["id"] for n in "abc"]
    r = h.client.post(f"/api/leads/{ids[0]}/move", json={"stage": "atendimento", "position": 0}, headers=h.a())
    assert r.status_code == 200 and r.json()["data"]["stage"] == "atendimento"
    board = h.client.get("/api/leads/board", headers=h.a()).json()["data"]
    assert [c["etapa"] for c in board] == list(CFG.stage_slugs)
    assert [x["name"] for x in board[0]["cards"]] == ["c", "b"] and board[1]["cards"][0]["name"] == "a"
    assert h.client.post(f"/api/leads/{ids[0]}/move", json={"stage": "nada", "position": 0}, headers=h.a()).status_code == 422
    assert h.client.post(f"/api/leads/{ids[0]}/move", json={"stage": "lead", "position": -1}, headers=h.a()).status_code == 422
