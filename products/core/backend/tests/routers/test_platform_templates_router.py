"""/api/admin/templates -- auth strictness + the CRUD/version flow over the in-memory repo."""
from __future__ import annotations

import pytest

from app.routers.platform_templates import get_service
from app.services.platform_templates.repository import FakePlatformTemplateRepo
from app.services.platform_templates.service import PlatformTemplateService

AUTH = {"Authorization": "Bearer t"}
UNKNOWN = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def fake_service():
    from app.main import app

    svc = PlatformTemplateService(FakePlatformTemplateRepo())
    app.dependency_overrides[get_service] = lambda: svc
    yield svc
    app.dependency_overrides.pop(get_service, None)


def _body(**over):
    b = {"kind": "message", "key": "boas-vindas", "title": "Boas-vindas", "format": "markdown", "body": "Ola"}
    b.update(over)
    return b


ENDPOINTS = [
    ("get", "/api/admin/templates"), ("get", "/api/admin/templates/meta"), ("get", "/api/admin/templates/sources"),
    ("get", f"/api/admin/templates/{UNKNOWN}"), ("get", f"/api/admin/templates/{UNKNOWN}/history"),
    ("post", "/api/admin/templates"), ("patch", f"/api/admin/templates/{UNKNOWN}"),
    ("post", f"/api/admin/templates/{UNKNOWN}/activate"), ("post", f"/api/admin/templates/{UNKNOWN}/archive"),
]


def _kw(method, url):
    if method == "post" and url.endswith("/templates"):
        return {"json": _body()}
    if method == "patch":
        return {"json": {"title": "x"}}
    return {}


class TestAuth:
    @pytest.mark.parametrize("method,url", ENDPOINTS)
    def test_anonymous_is_401(self, unauth_client, fake_service, method, url):
        assert getattr(unauth_client, method)(url, **_kw(method, url)).status_code == 401

    @pytest.mark.parametrize("method,url", ENDPOINTS)
    def test_non_admin_is_403(self, client, fake_service, method, url):
        assert getattr(client, method)(url, headers=AUTH, **_kw(method, url)).status_code == 403


class TestFlow:
    def test_create_get_list(self, admin_client, fake_service):
        r = admin_client.post("/api/admin/templates", headers=AUTH, json=_body())
        assert r.status_code == 201
        row = r.json()["data"]
        assert row["status"] == "draft" and row["version"] == 1
        assert admin_client.get(f"/api/admin/templates/{row['id']}", headers=AUTH).json()["data"]["body"] == "Ola"
        listing = admin_client.get("/api/admin/templates?kind=message", headers=AUTH).json()["data"]
        assert [x["key"] for x in listing] == ["boas-vindas"]

    def test_activate_then_edit_makes_v2_and_history(self, admin_client, fake_service):
        a = admin_client.post("/api/admin/templates", headers=AUTH, json=_body()).json()["data"]
        act = admin_client.post(f"/api/admin/templates/{a['id']}/activate", headers=AUTH).json()["data"]
        assert act["status"] == "active"
        v2 = admin_client.patch(f"/api/admin/templates/{a['id']}", headers=AUTH, json={"body": "Novo"}).json()["data"]
        assert v2["version"] == 2 and v2["status"] == "draft"
        hist = admin_client.get(f"/api/admin/templates/{a['id']}/history", headers=AUTH).json()["data"]
        assert [h["version"] for h in hist] == [2, 1]
        arch = admin_client.post(f"/api/admin/templates/{v2['id']}/archive", headers=AUTH).json()["data"]
        assert arch["status"] == "archived"

    def test_invalid_json_is_422_with_errors(self, admin_client, fake_service):
        r = admin_client.post("/api/admin/templates", headers=AUTH, json=_body(format="json", body="{bad"))
        assert r.status_code == 422 and "JSON invalido" in r.json()["error"]["message"]

    def test_design_system_rejects_css_injection(self, admin_client, fake_service):
        body = '{"schema": "noctus.brand-tokens/v1", "light": {"primary": "x; y: url(z)"}}'
        r = admin_client.post("/api/admin/templates", headers=AUTH,
                              json=_body(kind="design_system", key="ds", format="json", body=body))
        assert r.status_code == 422

    def test_body_over_cap_is_422(self, admin_client, fake_service):
        r = admin_client.post("/api/admin/templates", headers=AUTH, json=_body(body="x" * 200_001))
        assert r.status_code == 422

    def test_unknown_field_and_bad_slug_are_422(self, admin_client, fake_service):
        assert admin_client.post("/api/admin/templates", headers=AUTH, json=_body(extra=1)).status_code == 422
        assert admin_client.post("/api/admin/templates", headers=AUTH, json=_body(product="Bad Slug")).status_code == 422

    def test_unknown_id_404_and_bad_filters_422(self, admin_client, fake_service):
        assert admin_client.get(f"/api/admin/templates/{UNKNOWN}", headers=AUTH).status_code == 404
        assert admin_client.get("/api/admin/templates?kind=nope", headers=AUTH).status_code == 422

    def test_meta_tree_counts_templates_and_sources(self, admin_client, fake_service):
        admin_client.post("/api/admin/templates", headers=AUTH, json=_body(product="social-wiring"))
        data = admin_client.get("/api/admin/templates/meta", headers=AUTH).json()["data"]
        msg = next(k for k in data["kinds"] if k["key"] == "message")
        sw = next(s for s in msg["scopes"] if s["scope"] == "social-wiring")
        assert sw["templates"] == 1 and sw["sources"] >= 1
        assert [k["key"] for k in data["kinds"]][0] == "design_system"

    def test_sources_are_filterable(self, admin_client, fake_service):
        rows = admin_client.get("/api/admin/templates/sources?kind=agent&product=agents", headers=AUTH).json()["data"]
        assert rows and all(r["kind"] == "agent" and r["product"] == "agents" for r in rows)
        plat = admin_client.get("/api/admin/templates/sources?product=_platform", headers=AUTH).json()["data"]
        assert plat and all(r["product"] is None for r in plat)
