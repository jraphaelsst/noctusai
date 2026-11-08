"""HTTP surface -- both stores. Auth is strictly 401 (never `in (401, 404|422)`); admin-only writes are 403 for a member."""
from __future__ import annotations

import pytest

P = "/api/metas"
ID = "00000000-0000-4000-8000-000000000009"

ROUTES = [
    ("get", "/config"), ("get", "/periods"), ("post", "/periods"), ("post", "/periods/generate"),
    ("get", f"/periods/{ID}"), ("patch", f"/periods/{ID}"), ("delete", f"/periods/{ID}"),
    ("get", "/teams"), ("post", "/teams"), ("get", f"/teams/{ID}"), ("patch", f"/teams/{ID}"), ("delete", f"/teams/{ID}"),
    ("get", f"/teams/{ID}/members"), ("post", f"/teams/{ID}/members"), ("patch", f"/teams/{ID}/members/{ID}"), ("delete", f"/teams/{ID}/members/{ID}"),
    ("get", "/goals"), ("post", "/goals"), ("get", "/goals/summary"), ("get", f"/goals/{ID}"), ("patch", f"/goals/{ID}"),
    ("delete", f"/goals/{ID}"), ("post", f"/goals/{ID}/contributions"),
    ("get", "/rules"), ("put", "/rules"), ("post", "/rules/defaults"), ("delete", f"/rules/{ID}"),
    ("get", "/settings"), ("put", "/settings"),
    ("get", "/events"), ("post", "/events"), ("patch", f"/events/{ID}"), ("delete", f"/events/{ID}"),
    ("get", "/rankings"), ("get", "/closings"), ("post", "/closings/close"),
]
ADMIN_ONLY = [
    ("post", "/periods", {"name": "x", "kind": "monthly", "starts_on": "2026-01-01", "ends_on": "2026-01-31"}),
    ("post", "/periods/generate", {"kind": "monthly", "starts_on": "2026-01-01", "ends_on": "2026-02-01"}),
    ("post", "/teams", {"name": "x"}),
    ("put", "/rules", {"event_type": "venda", "points": 1}),
    ("post", "/rules/defaults", None),
    ("put", "/settings", {"weight_points": 2}),
    ("post", "/closings/close", {"period_id": ID}),
    ("delete", f"/events/{ID}", None),
]


@pytest.mark.parametrize("method, path", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path):
    kw = {"json": {}} if method in ("post", "patch", "put") else {}
    assert getattr(h.client, method)(P + path, **kw).status_code == 401


@pytest.mark.parametrize("method, path, body", ADMIN_ONLY)
def test_member_writes_to_structure_are_403(h, method, path, body):
    kw = {"json": body} if body is not None else {}
    assert getattr(h.client, method)(P + path, headers=h.as_("bia"), **kw).status_code == 403


def test_config_exposes_event_types_modalities_and_categories_as_data(h):
    data = h.client.get(f"{P}/config", headers=h.as_("bia")).json()["data"]
    assert [e["slug"] for e in data["event_types"]] == ["captacao", "venda", "visita"]
    assert {c["slug"]: c["source"] for c in data["categories"]}["vendas"] == "count:venda"


def test_full_flow_over_http(h):
    admin, bia = h.as_("admin"), h.as_("bia")
    c = h.client
    period = c.post(f"{P}/periods", json={"name": "Jan", "kind": "monthly", "starts_on": "2026-01-01", "ends_on": "2026-01-31"}, headers=admin)
    assert period.status_code == 201
    pid = period.json()["data"]["id"]
    assert c.post(f"{P}/rules/defaults", headers=admin).status_code == 201
    team = c.post(f"{P}/teams", json={"name": "Norte"}, headers=admin).json()["data"]
    mem = c.post(f"{P}/teams/{team['id']}/members", json={"user_id": "00000000-0000-4000-8000-0000000000b2"}, headers=admin)
    assert mem.status_code == 201
    first = c.post(f"{P}/events", json={"event_type": "venda", "occurred_on": "2026-01-05", "value": 100000, "dedupe_key": "k1"}, headers=bia)
    assert first.status_code == 201 and first.json()["data"]["points"] == 50
    replay = c.post(f"{P}/events", json={"event_type": "venda", "occurred_on": "2026-01-05", "value": 100000, "dedupe_key": "k1"}, headers=bia)
    assert replay.status_code == 200 and replay.json()["data"]["id"] == first.json()["data"]["id"]
    goal = c.post(f"{P}/goals", json={"scope": "individual", "category": "vgv", "target": 50000, "period_id": pid}, headers=bia)
    assert goal.status_code == 201 and goal.json()["data"]["realized"] == 100000
    rank = c.get(f"{P}/rankings", params={"period_id": pid}, headers=bia).json()["data"]
    assert [e["rank"] for e in rank["entries"]] == [1]
    closed = c.post(f"{P}/closings/close", json={"period_id": pid}, headers=admin)
    assert closed.status_code == 201 and len(closed.json()["data"]["snapshots"]) == 1
    assert c.post(f"{P}/closings/close", json={"period_id": pid}, headers=admin).status_code == 200
    assert len(c.get(f"{P}/closings", params={"period_id": pid}, headers=bia).json()["data"]) == 1
    assert c.delete(f"{P}/periods/{pid}", headers=admin).status_code == 409


def test_unknown_field_is_a_422_not_silently_dropped(h):
    r = h.client.post(f"{P}/teams", json={"name": "x", "colour": "red"}, headers=h.as_("admin"))
    assert r.status_code == 422


def test_error_envelope_and_foreign_org_is_404(h):
    r = h.client.post(f"{P}/periods", json={"name": "x", "kind": "bogus", "starts_on": "2026-01-01", "ends_on": "2026-01-31"}, headers=h.as_("admin"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "periodo_invalido"
    pid = h.client.post(f"{P}/periods", json={"name": "Jan", "kind": "monthly", "starts_on": "2026-01-01", "ends_on": "2026-01-31"}, headers=h.as_("admin")).json()["data"]["id"]
    assert h.client.get(f"{P}/periods/{pid}", headers=h.as_("admin", org="b")).status_code == 404
    assert h.client.get(f"{P}/periods", headers=h.as_("admin", org="b")).json()["data"] == []
