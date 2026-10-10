"""/api/campanhas CRUD (CONTRACT §1.1): auth boundary + HTTP behaviour."""
from __future__ import annotations

import pytest

from app.dependencies import coerce_org_uuid, get_admin_client
from tests.support.campanhas_fake import FakeCampanhasClient

ROUTES = [
    ("get", "/api/campanhas"),
    ("post", "/api/campanhas"),
    ("patch", "/api/campanhas/00000000-0000-0000-0000-000000000001"),
    ("delete", "/api/campanhas/00000000-0000-0000-0000-000000000001"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_unauthenticated_is_strictly_401(anon_client, method, path):
    kw = {"json": {}} if method in ("post", "patch") else {}
    resp = getattr(anon_client, method)(path, **kw)
    assert resp.status_code == 401, resp.text


@pytest.fixture
def api(client):
    from app.main import app

    fake = FakeCampanhasClient()
    app.dependency_overrides[get_admin_client] = lambda: fake
    org = coerce_org_uuid("test-org-123")
    fake.add_imovel(org, "ONE1", "Casa Um")
    yield client, fake
    app.dependency_overrides.pop(get_admin_client, None)


def _body(nome="Camp", codigos=("ONE1",), veics=(("ad", "111"),)):
    return {
        "nome": nome, "imovel_codigos": list(codigos),
        "veiculacoes": [{"canal": "meta_ads", "nivel": n, "ref_codigo": r} for n, r in veics],
    }


def test_crud_happy_path(api):
    client, _ = api
    r = client.post("/api/campanhas", json=_body())
    assert r.status_code == 201, r.text
    camp = r.json()["data"]
    assert camp["imoveis"] == [{"codigo": "ONE1", "titulo": "Casa Um"}]
    assert camp["veiculacoes"][0]["nivel"] == "ad" and camp["created_at"]

    assert [c["id"] for c in client.get("/api/campanhas").json()["data"]] == [camp["id"]]

    p = client.patch(f"/api/campanhas/{camp['id']}", json={"nome": "Novo"})
    assert p.status_code == 200 and p.json()["data"]["nome"] == "Novo"

    assert client.delete(f"/api/campanhas/{camp['id']}").status_code == 204
    assert client.get("/api/campanhas").json() == {"data": []}


def test_unknown_codigo_is_400_listing_them(api):
    client, _ = api
    r = client.post("/api/campanhas", json=_body(codigos=("ONE1", "XX9")))
    assert r.status_code == 400
    assert r.json()["codigos"] == ["XX9"]


def test_duplicate_ref_is_409_veiculacao_em_uso(api):
    client, _ = api
    assert client.post("/api/campanhas", json=_body(nome="Primeira")).status_code == 201
    r = client.post("/api/campanhas", json=_body(nome="Segunda"))
    assert r.status_code == 409
    body = r.json()
    assert set(body) == {"detail", "code"} and body["code"] == "veiculacao_em_uso"
    # The FE pins the error to the row by finding the ref_codigo in `detail`.
    assert "111" in body["detail"] and '"Primeira"' in body["detail"]


@pytest.mark.parametrize("veic", [
    {"canal": "meta_ads", "nivel": "pixel", "ref_codigo": "1"},
    {"canal": "email", "nivel": "ad", "ref_codigo": "1"},
])
def test_wrong_nivel_or_canal_is_rejected(api, veic):
    client, _ = api
    body = _body(veics=())
    body["veiculacoes"] = [veic]
    r = client.post("/api/campanhas", json=body)
    assert r.status_code == 400 and r.json()["code"] == "valor_invalido", r.text


def test_wrong_value_on_patch_and_extra_field_is_400(api):
    client, _ = api
    cid = client.post("/api/campanhas", json=_body()).json()["data"]["id"]
    bad = {"veiculacoes": [{"canal": "meta_ads", "nivel": "pixel", "ref_codigo": "1"}]}
    r = client.patch(f"/api/campanhas/{cid}", json=bad)
    assert r.status_code == 400 and r.json()["code"] == "valor_invalido"
    r = client.post("/api/campanhas", json={**_body(), "surpresa": 1})
    assert r.status_code == 400 and r.json()["code"] == "valor_invalido"


def test_other_org_or_unknown_is_404(api):
    client, fake = api
    fake.tables["campanhas"] = [{
        "id": "00000000-0000-0000-0000-0000000000aa", "org_id": "other-org",
        "nome": "Alheia", "deleted_at": None, "created_at": "x",
    }]
    for method in ("patch", "delete"):
        kw = {"json": {"nome": "x"}} if method == "patch" else {}
        r = getattr(client, method)("/api/campanhas/00000000-0000-0000-0000-0000000000aa", **kw)
        assert r.status_code == 404, r.text


def test_delete_frees_ref_for_reuse(api):
    client, _ = api
    cid = client.post("/api/campanhas", json=_body()).json()["data"]["id"]
    client.delete(f"/api/campanhas/{cid}")
    assert client.post("/api/campanhas", json=_body(nome="Outra")).status_code == 201
