"""`/api/lais/reengajamento/*` (lais-build-contract 6): auth boundary (strict `== 401`), the member-read /
admin-write split, org isolation, strict bodies, and the three 409 codes. The DB is the schema-scoped mock
injected through the router's own `get_reengajamento_db` seam; auth is the REAL chain over a mocked session."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from tests.support.lais_world import ADMIN_ID, CORRETOR_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

BASE = "/api/lais/reengajamento"
H = {"Authorization": "Bearer test-token"}
OTHER_REGUA = "00000000-0000-4000-8000-0000000000ee"
SEM_REGUA = "00000000-0000-4000-8000-0000000000ff"


class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(f"{BASE}{url}", headers=headers, **kw)

    def regua(self, **over):
        body = {"nome": "Régua padrão", "compra": True, "aluguel": False, **over}
        r = self.call("post", "/reguas", body)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    def tentativa(self, regua_id, **over):
        body = {"espera_valor": 1, "espera_unidade": "dias", "texto": "Oi, tudo bem?", **over}
        return self.call("post", f"/reguas/{regua_id}/tentativas", body)


def _scene(role):
    world = World()
    for t in ("lais_reengajamento_config", "lais_reguas", "lais_regua_tentativas"):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.lais_reengajamento_router import get_reengajamento_db

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_reengajamento_db] = lambda: world.sw
        yield Scene(TestClient(app), world)
        app.dependency_overrides.pop(get_reengajamento_db, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


ROTAS = [
    ("get", "/config", None), ("put", "/config", {"horas_ativo": True}),
    ("get", "/reguas", None), ("post", "/reguas", {"nome": "x"}),
    ("get", f"/reguas/{SEM_REGUA}", None), ("patch", f"/reguas/{SEM_REGUA}", {"nome": "y"}),
    ("delete", f"/reguas/{SEM_REGUA}", None),
    ("post", f"/reguas/{SEM_REGUA}/ativar", None), ("post", f"/reguas/{SEM_REGUA}/desativar", None),
    ("post", f"/reguas/{SEM_REGUA}/tentativas", {"espera_valor": 1, "texto": "x"}),
    ("patch", f"/reguas/{SEM_REGUA}/tentativas/{OTHER_REGUA}", {"ativa": False}),
    ("delete", f"/reguas/{SEM_REGUA}/tentativas/{OTHER_REGUA}", None),
]
ESCRITAS = [r for r in ROTAS if r[0] != "get"]


class TestAuth:
    @pytest.mark.parametrize("method,url,body", ROTAS)
    def test_no_token_is_exactly_401(self, admin, method, url, body):
        r = admin.call(method, url, body, headers={})
        assert r.status_code == 401

    def test_a_member_can_read(self, member):
        assert member.call("get", "/config").status_code == 200
        assert member.call("get", "/reguas").status_code == 200

    @pytest.mark.parametrize("method,url,body", ESCRITAS)
    def test_a_member_cannot_write_403(self, member, method, url, body):
        assert member.call(method, url, body).status_code == 403


class TestConfig:
    def test_defaults_then_partial_put(self, admin):
        assert admin.call("get", "/config").json()["data"] == {
            "minutos_ativo": False, "minutos_intervalo": 5, "horas_ativo": False, "horas_intervalo": 1}
        r = admin.call("put", "/config", {"minutos_ativo": True, "minutos_intervalo": 25})
        assert r.status_code == 200 and r.json()["data"]["minutos_intervalo"] == 25
        assert admin.call("put", "/config", {"horas_ativo": True, "horas_intervalo": 11}).json()["data"] == {
            "minutos_ativo": True, "minutos_intervalo": 25, "horas_ativo": True, "horas_intervalo": 11}

    @pytest.mark.parametrize("body", [
        {"minutos_intervalo": 7}, {"minutos_intervalo": 0}, {"minutos_intervalo": 65}, {"horas_intervalo": 0},
        {"horas_intervalo": 12}, {"minutos_ativo": "talvez"}, {"org_id": ORG_ID}, {"unknown": 1},
    ])
    def test_invalid_or_unknown_fields_are_422(self, admin, body):
        assert admin.call("put", "/config", body).status_code == 422

    def test_one_org_never_sees_anothers_config(self, admin):
        admin.call("put", "/config", {"horas_ativo": True})
        admin.w.sw.table("lais_reengajamento_config").insert({
            "org_id": OTHER_ORG_ID, "minutos_ativo": True, "minutos_intervalo": 60, "horas_ativo": False, "horas_intervalo": 1}).execute()
        assert admin.call("get", "/config").json()["data"]["minutos_intervalo"] == 5


class TestReguas:
    def test_crud_roundtrip(self, admin):
        r = admin.regua(nome="  Compradores  ")
        assert r["nome"] == "Compradores" and r["ativa"] is False and r["tentativas"] == []
        assert admin.call("get", f"/reguas/{r['id']}").json()["data"]["id"] == r["id"]
        assert admin.call("patch", f"/reguas/{r['id']}", {"aluguel": True, "nome": "Renomeada"}).json()["data"]["aluguel"] is True
        assert [x["nome"] for x in admin.call("get", "/reguas").json()["data"]] == ["Renomeada"]
        assert admin.call("delete", f"/reguas/{r['id']}").status_code == 204
        assert admin.call("get", f"/reguas/{r['id']}").status_code == 404

    @pytest.mark.parametrize("body", [{}, {"nome": ""}, {"nome": "x" * 81}, {"nome": "x", "ativa": True}, {"nome": "x", "extra": 1}])
    def test_create_is_strict_422(self, admin, body):
        assert admin.call("post", "/reguas", body).status_code == 422

    def test_activate_without_an_attempt_is_409_regua_sem_tentativa(self, admin):
        r = admin.regua()
        res = admin.call("post", f"/reguas/{r['id']}/ativar")
        assert res.status_code == 409 and res.json()["error"]["code"] == "regua_sem_tentativa"
        assert admin.call("get", f"/reguas/{r['id']}").json()["data"]["ativa"] is False

    def test_activate_then_deactivate(self, admin):
        r = admin.regua()
        assert admin.tentativa(r["id"]).status_code == 201
        assert admin.call("post", f"/reguas/{r['id']}/ativar").json()["data"]["ativa"] is True
        assert admin.call("post", f"/reguas/{r['id']}/desativar").json()["data"]["ativa"] is False

    def test_another_orgs_regua_is_404_for_every_verb(self, admin):
        admin.w.sw.table("lais_reguas").insert({
            "id": OTHER_REGUA, "org_id": OTHER_ORG_ID, "nome": "Alheia", "ativa": False, "compra": True, "aluguel": False}).execute()
        for method, url, body in [
            ("get", f"/reguas/{OTHER_REGUA}", None), ("patch", f"/reguas/{OTHER_REGUA}", {"nome": "x"}),
            ("delete", f"/reguas/{OTHER_REGUA}", None), ("post", f"/reguas/{OTHER_REGUA}/ativar", None),
            ("post", f"/reguas/{OTHER_REGUA}/tentativas", {"espera_valor": 1, "texto": "x"}),
        ]:
            assert admin.call(method, url, body).status_code == 404, (method, url)
        assert admin.call("get", "/reguas").json()["data"] == []


class TestTentativas:
    def test_the_fourth_is_409_limite_tentativas(self, admin):
        r = admin.regua()
        for _ in range(3):
            assert admin.tentativa(r["id"]).status_code == 201
        res = admin.tentativa(r["id"])
        assert res.status_code == 409 and res.json()["error"]["code"] == "limite_tentativas"
        got = admin.call("get", f"/reguas/{r['id']}").json()["data"]["tentativas"]
        assert [t["ordem"] for t in got] == [1, 2, 3]

    def test_the_last_active_attempt_of_an_active_regua_is_409(self, admin):
        r = admin.regua()
        t = admin.tentativa(r["id"]).json()["data"]
        admin.call("post", f"/reguas/{r['id']}/ativar")
        for res in (admin.call("patch", f"/reguas/{r['id']}/tentativas/{t['id']}", {"ativa": False}),
                    admin.call("delete", f"/reguas/{r['id']}/tentativas/{t['id']}")):
            assert res.status_code == 409 and res.json()["error"]["code"] == "ultima_tentativa_ativa"
        admin.call("post", f"/reguas/{r['id']}/desativar")
        assert admin.call("delete", f"/reguas/{r['id']}/tentativas/{t['id']}").status_code == 204

    def test_patch_changes_wait_and_swaps_text_for_template(self, admin):
        r = admin.regua()
        t = admin.tentativa(r["id"]).json()["data"]
        res = admin.call("patch", f"/reguas/{r['id']}/tentativas/{t['id']}", {"espera_valor": 3, "espera_unidade": "horas"})
        assert res.json()["data"]["espera_valor"] == 3 and res.json()["data"]["espera_unidade"] == "horas"
        res = admin.call("patch", f"/reguas/{r['id']}/tentativas/{t['id']}", {"template_id": OTHER_REGUA})
        assert res.json()["data"]["template_id"] == OTHER_REGUA and res.json()["data"]["texto"] is None

    @pytest.mark.parametrize("body", [
        {"espera_valor": 1},                                              # neither texto nor template
        {"espera_valor": 1, "texto": "x", "template_id": OTHER_REGUA},    # both
        {"espera_valor": 0, "texto": "x"}, {"espera_valor": 1000, "texto": "x"},
        {"espera_valor": 1, "texto": "   "}, {"espera_valor": 1, "texto": "x" * 1025},
        {"espera_valor": 1, "texto": "x", "espera_unidade": "semanas"},
        {"espera_valor": 1, "texto": "x", "ordem": 4}, {"espera_valor": 1, "texto": "x", "ordem": 0},
        {"texto": "x"}, {"espera_valor": 1, "texto": "x", "regua_id": OTHER_REGUA},
    ])
    def test_create_is_strict_422(self, admin, body):
        r = admin.regua()
        assert admin.call("post", f"/reguas/{r['id']}/tentativas", body).status_code == 422

    def test_an_attempt_of_another_regua_is_404(self, admin):
        a, b = admin.regua(), admin.regua(nome="Outra")
        t = admin.tentativa(a["id"]).json()["data"]
        assert admin.call("patch", f"/reguas/{b['id']}/tentativas/{t['id']}", {"ativa": False}).status_code == 404
        assert admin.call("delete", f"/reguas/{b['id']}/tentativas/{t['id']}").status_code == 404

    def test_a_text_of_exactly_1024_chars_is_accepted(self, admin):
        r = admin.regua()
        assert admin.tentativa(r["id"], texto="x" * 1024).status_code == 201
