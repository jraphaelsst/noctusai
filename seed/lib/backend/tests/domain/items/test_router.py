"""Router contract: paths, statuses, envelopes, pt-BR codes, authz (staff read / admin write), isolation."""
from __future__ import annotations

import pytest

from .conftest import EAN13

U0 = "11111111-1111-1111-1111-111111111111"
P = "/api/items"

#: (method, path, is_write) -- the whole surface.
ROUTES = [
    ("GET", P, False), ("POST", P, True), ("GET", f"{P}/{U0}", False), ("PATCH", f"{P}/{U0}", True),
    ("POST", f"{P}/{U0}/archive", True), ("POST", f"{P}/{U0}/unarchive", True),
    ("GET", f"{P}/export.csv", False), ("POST", f"{P}/import", True),
    ("GET", f"{P}/categories", False), ("POST", f"{P}/categories", True),
    ("PATCH", f"{P}/categories/{U0}", True), ("DELETE", f"{P}/categories/{U0}", True),
]


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


@pytest.mark.parametrize("method, path, _w", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path, _w):
    assert call(h, method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, _w", [r for r in ROUTES if r[2]])
def test_staff_cannot_write(h, method, path, _w):
    kw = {"files": {"file": ("a.csv", b"sku,name\n", "text/csv")}} if path.endswith("/import") else {"json": {}}
    assert call(h, method, path, h.staff("user"), **kw).status_code == 403


@pytest.mark.parametrize("method, path, _w", [r for r in ROUTES if not r[2]])
def test_staff_can_read(h, method, path, _w):
    assert call(h, method, path, h.staff("user")).status_code in (200, 404)


def create(h, headers=None, **over):
    r = call(h, "POST", P, headers or h.admin, json={"sku": "x-1", "name": "Item", **over})
    return r


def test_admin_crud_roundtrip_and_envelopes(h):
    r = create(h, ncm="7318.15.00", gtin=EAN13, cost_cents=100)
    assert r.status_code == 201, r.text
    item = r.json()["data"]
    assert item["sku"] == "X-1" and item["ncm"] == "73181500"
    got = call(h, "GET", f"{P}/{item['id']}", h.staff("user"))
    assert got.status_code == 200 and got.json()["data"]["id"] == item["id"]
    patched = call(h, "PATCH", f"{P}/{item['id']}", h.admin, json={"name": "Renomeado", "price_cents": 250})
    assert patched.json()["data"]["name"] == "Renomeado" and patched.json()["data"]["price_cents"] == 250
    listed = call(h, "GET", P, h.staff("user"), params={"q": "renomeado"}).json()
    assert [r["id"] for r in listed["data"]] == [item["id"]] and listed["pagination"]["total"] == 1
    arch = call(h, "POST", f"{P}/{item['id']}/archive", h.admin).json()["data"]
    assert arch["is_active"] is False
    assert call(h, "GET", P, h.staff("user"), params={"active": "true"}).json()["data"] == []
    assert call(h, "POST", f"{P}/{item['id']}/unarchive", h.admin).json()["data"]["is_active"] is True


def test_validation_errors_use_the_error_envelope(h):
    r = create(h, gtin="7891000100104")
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "gtin_invalido" and body["details"]["field"] == "gtin"
    assert create(h, ncm="1").json()["error"]["code"] == "ncm_invalido"


def test_duplicate_sku_is_409(h):
    assert create(h).status_code == 201
    r = create(h, sku="X-1")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "sku_duplicado")


def test_extra_fields_are_rejected_not_silently_dropped(h):
    assert create(h, typo_field=1).status_code == 422
    assert call(h, "PATCH", f"{P}/{U0}", h.admin, json={"typo": 1}).status_code == 422


def test_other_orgs_ids_are_404_and_lists_are_scoped(h):
    mine = create(h).json()["data"]
    theirs = create(h, h.admin_b, sku="Y-1").json()["data"]
    assert call(h, "GET", f"{P}/{mine['id']}", h.admin_b).status_code == 404
    assert call(h, "PATCH", f"{P}/{mine['id']}", h.admin_b, json={"name": "x"}).status_code == 404
    assert call(h, "POST", f"{P}/{mine['id']}/archive", h.admin_b).status_code == 404
    assert [r["id"] for r in call(h, "GET", P, h.admin_b).json()["data"]] == [theirs["id"]]
    assert call(h, "GET", f"{P}/export.csv", h.admin_b).text.count("X-1") == 0
    # a foreign category cannot be referenced
    cat_b = call(h, "POST", f"{P}/categories", h.admin_b, json={"name": "B"}).json()["data"]
    r = create(h, sku="Z-1", category_id=cat_b["id"])
    assert (r.status_code, r.json()["error"]["code"]) == (422, "referencia_invalida")
    assert call(h, "DELETE", f"{P}/categories/{cat_b['id']}", h.admin).status_code == 404


def test_category_routes(h):
    root = call(h, "POST", f"{P}/categories", h.admin, json={"name": "Raiz"})
    assert root.status_code == 201
    rid = root.json()["data"]["id"]
    assert call(h, "POST", f"{P}/categories", h.admin, json={"name": "raiz"}).json()["error"]["code"] == "categoria_duplicada"
    assert call(h, "PATCH", f"{P}/categories/{rid}", h.admin, json={"parent_id": rid}).json()["error"]["code"] == "categoria_ciclo"
    assert [c["name"] for c in call(h, "GET", f"{P}/categories", h.staff("user")).json()["data"]] == ["Raiz"]
    assert call(h, "DELETE", f"{P}/categories/{rid}", h.admin).status_code == 204


def test_import_and_export_over_http(h):
    csv_bytes = "sku,name,unit,cost\nA-1,Alfa,KG,\"1.234,56\"\nB-2,Beta,UN,2.50\n".encode()
    r = call(h, "POST", f"{P}/import", h.admin, files={"file": ("itens.csv", csv_bytes, "text/csv")}, data={"dry_run": "true"})
    assert r.json()["data"] == {"created": 2, "updated": 0, "dry_run": True}
    assert call(h, "GET", P, h.admin).json()["pagination"]["total"] == 0
    r = call(h, "POST", f"{P}/import", h.admin, files={"file": ("itens.csv", csv_bytes, "text/csv")})
    assert r.json()["data"] == {"created": 2, "updated": 0, "dry_run": False}
    exp = call(h, "GET", f"{P}/export.csv", h.staff("user"))
    assert exp.headers["content-type"].startswith("text/csv") and "attachment" in exp.headers["content-disposition"]
    assert "A-1,Alfa" in exp.text and "1234.56" in exp.text
