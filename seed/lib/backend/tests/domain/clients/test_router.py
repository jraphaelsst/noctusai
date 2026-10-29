"""HTTP surface -- both stores. Auth is strictly 401; [admin] routes 403 for members; every route is org-scoped."""
from __future__ import annotations

import pytest

from .conftest import ACCOUNT, CFG, VALID_CPF

X = "00000000-0000-4000-8000-000000000009"

ROUTES = [
    ("get", "/api/clients/config"),
    ("get", "/api/clients"),
    ("get", "/api/clients/tags"),
    ("post", "/api/clients"),
    ("get", "/api/clients/sessions?from=2026-11-01&to=2026-11-07"),
    ("patch", f"/api/clients/sessions/{X}"),
    ("delete", f"/api/clients/sessions/{X}"),
    ("patch", f"/api/clients/schedules/{X}"),
    ("delete", f"/api/clients/schedules/{X}"),
    ("get", f"/api/clients/{X}"),
    ("patch", f"/api/clients/{X}"),
    ("delete", f"/api/clients/{X}"),
    ("get", f"/api/clients/{X}/sessions"),
    ("post", f"/api/clients/{X}/sessions"),
    ("get", f"/api/clients/{X}/schedules"),
    ("post", f"/api/clients/{X}/schedules"),
    ("get", f"/api/clients/{X}/finance"),
    ("post", f"/api/clients/{X}/payments"),
]


@pytest.mark.parametrize("method, path", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path):
    kw = {"json": {}} if method in ("post", "patch") else {}
    assert getattr(h.client, method)(path, **kw).status_code == 401


def test_config_payload(h):
    data = h.client.get("/api/clients/config", headers=h.a()).json()["data"]
    assert data == CFG.as_dict()
    assert data["noun_plural"] == "Pacientes" and data["timezone"] == "America/Sao_Paulo"
    assert [s["slug"] for s in data["session_statuses"] if s["billable"]] == ["realizada", "falta"]


def test_admin_routes_refuse_members(h):
    cid = h.client.post("/api/clients", json={"name": "Ana"}, headers=h.a()).json()["data"]["id"]
    assert h.client.delete(f"/api/clients/{cid}", headers=h.a()).status_code == 403
    body = {"amount_cents": 1, "paid_on": "2026-11-02", "account_id": ACCOUNT, "method": "pix"}
    assert h.client.post(f"/api/clients/{cid}/payments", json=body, headers=h.a()).status_code == 403
    assert h.client.delete(f"/api/clients/{cid}", headers=h.a(admin=True)).status_code == 204


def test_crud_roundtrip_and_masking(h):
    r = h.client.post("/api/clients", json={"name": "Ana", "phone": "(11) 99457-3387", "doc": VALID_CPF, "tags": ["x"]}, headers=h.a())
    assert r.status_code == 201
    c = r.json()["data"]
    assert c["phone"] == "+5511994573387" and c["doc"] == "***.982.247-**" and set(c["summary"]) == {
        "next_session_at", "last_session_at", "sessions_done", "open_cents", "overdue_cents", "paid_cents"}
    assert h.client.get(f"/api/clients/{c['id']}", headers=h.a(admin=True)).json()["data"]["doc"] == VALID_CPF
    p = h.client.patch(f"/api/clients/{c['id']}", json={"email": "ana@x.com", "phone": ""}, headers=h.a())
    assert p.json()["data"]["email"] == "ana@x.com" and p.json()["data"]["phone"] is None
    lst = h.client.get("/api/clients", params={"limit": 1}, headers=h.a()).json()
    assert len(lst["data"]) == 1 and lst["next_cursor"] is None
    assert h.client.get("/api/clients/tags", headers=h.a()).json()["data"] == ["x"]
    assert h.client.get("/api/clients", params={"lead_id": "nope"}, headers=h.a()).status_code == 422
    assert h.client.get("/api/clients", params={"cursor": "x"}, headers=h.a()).json()["error"]["code"] == "filtro_invalido"


def test_strict_bodies_reject_unknown_keys(h):
    assert h.client.post("/api/clients", json={"name": "Ana", "nickname": "A"}, headers=h.a()).status_code == 422
    assert h.client.post("/api/clients", json={}, headers=h.a()).status_code == 422


def test_sessions_schedules_finance_flow(h):
    cid = h.client.post("/api/clients", json={"name": "Ana", "default_price_cents": 10000}, headers=h.a()).json()["data"]["id"]
    s = h.client.post(f"/api/clients/{cid}/sessions", json={"starts_at": "2026-10-28T10:00:00-03:00", "status": "realizada"}, headers=h.a())
    assert s.status_code == 201 and s.json()["data"]["entry_id"] and s.json()["data"]["client_name"] == "Ana"
    sid = s.json()["data"]["id"]
    sch = h.client.post(f"/api/clients/{cid}/schedules", json={"weekday": 1, "time": "09:30"}, headers=h.a())
    assert sch.status_code == 201 and sch.json()["data"]["time"] == "09:30"
    assert len(h.client.get(f"/api/clients/{cid}/schedules", headers=h.a()).json()["data"]) == 1
    agenda = h.client.get("/api/clients/sessions", params={"from": "2026-11-02", "to": "2026-11-08"}, headers=h.a()).json()["data"]
    assert [a["starts_at"][:16] for a in agenda] == ["2026-11-03T09:30"]
    assert h.client.get("/api/clients/sessions", params={"from": "2026-11-02"}, headers=h.a()).status_code == 422
    fin = h.client.get(f"/api/clients/{cid}/finance", headers=h.a()).json()["data"]
    assert fin["open_cents"] == 10000 and fin["entries"][0]["session_id"] == sid
    pay = h.client.post(
        f"/api/clients/{cid}/payments",
        json={"amount_cents": 10000, "paid_on": "2026-11-02", "account_id": ACCOUNT, "method": "pix", "notes": "ok"},
        headers=h.a(admin=True),
    )
    assert pay.status_code == 200 and len(pay.json()["data"]["settlement_ids"]) == 1
    assert pay.json()["data"]["finance"]["paid_cents"] == 10000
    r = h.client.delete(f"/api/clients/sessions/{sid}", headers=h.a())
    assert r.status_code == 409 and r.json()["error"]["code"] == "SESSAO_COM_PAGAMENTO"
    d = h.client.delete(f"/api/clients/{cid}", headers=h.a(admin=True))
    assert d.status_code == 409 and d.json()["error"]["code"] == "CLIENTE_COM_FINANCEIRO"
    over = h.client.post(
        f"/api/clients/{cid}/payments",
        json={"amount_cents": 1, "paid_on": "2026-11-02", "account_id": ACCOUNT, "method": "pix"}, headers=h.a(admin=True),
    )
    assert over.status_code == 422 and over.json()["error"]["code"] == "VALOR_EXCEDE_ABERTO"
    hist = h.client.get(f"/api/clients/{cid}/sessions", headers=h.a()).json()["data"]
    assert hist[0]["starts_at"] > hist[-1]["starts_at"]  # newest first
    patched = h.client.patch(f"/api/clients/schedules/{sch.json()['data']['id']}", json={"active": False}, headers=h.a())
    assert patched.json()["data"]["active"] is False
    assert h.client.delete(f"/api/clients/schedules/{sch.json()['data']['id']}", headers=h.a()).status_code == 204


def test_other_org_gets_404_everywhere(h):
    cid = h.client.post("/api/clients", json={"name": "Ana"}, headers=h.a()).json()["data"]["id"]
    sid = h.client.post(f"/api/clients/{cid}/sessions", json={"starts_at": "2026-11-03T10:00:00-03:00"}, headers=h.a()).json()["data"]["id"]
    scid = h.client.post(f"/api/clients/{cid}/schedules", json={"weekday": 0, "time": "10:00"}, headers=h.a()).json()["data"]["id"]
    assert h.client.get("/api/clients", headers=h.b()).json()["data"] == []
    for method, path, body in (
        ("get", f"/api/clients/{cid}", None),
        ("patch", f"/api/clients/{cid}", {"name": "x"}),
        ("delete", f"/api/clients/{cid}", None),
        ("get", f"/api/clients/{cid}/sessions", None),
        ("post", f"/api/clients/{cid}/sessions", {"starts_at": "2026-11-03T10:00:00-03:00"}),
        ("get", f"/api/clients/{cid}/schedules", None),
        ("get", f"/api/clients/{cid}/finance", None),
        ("patch", f"/api/clients/sessions/{sid}", {"notes": "x"}),
        ("delete", f"/api/clients/sessions/{sid}", None),
        ("patch", f"/api/clients/schedules/{scid}", {"active": False}),
        ("delete", f"/api/clients/schedules/{scid}", None),
    ):
        kw = {"json": body} if body is not None else {}
        assert getattr(h.client, method)(path, headers=h.b(admin=True), **kw).status_code == 404, (method, path)
