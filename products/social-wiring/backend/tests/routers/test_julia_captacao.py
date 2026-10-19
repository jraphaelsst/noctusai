"""Julia wave 8 -- Captacao (contract section 10): the `captacao` handler COMPOSES the wave-3 policy, the feed
(filters, page sizes, A7), registrar (prefilled imovel via the migration-226 flow) / descartar, strict `== 401`.
Seams: mock DB through the router's `get_captacao_client`, real auth chain over a mocked session."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import JuliaAction, TurnResult
from app.services import julia_acoes_service as acoes
from app.services import julia_captacao_service as svc
from app.services import julia_envio_service as envio

from tests.support.julia_world import ADMIN_ID, CONNECTION_ID, CORRETOR_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
BASE = "/api/julia/captacoes"
SEM = "00000000-0000-4000-8000-0000000000ff"


class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(url, headers=headers, **kw)

    def contato(self, n, *, responsavel=None, org=ORG_ID):
        row = {"id": f"00000000-0000-4000-8000-0000000c{n:04d}", "org_id": org, "connection_id": CONNECTION_ID,
               "chat_id": f"551190000{n:04d}@c.us", "telefone_e164": f"+551190000{n:04d}", "nome": f"Pessoa {n}",
               "operacao": "venda", "slots": {}, "gen": 0, "status_envio": "nao_pronto", "canal": "whatsapp",
               "responsavel_user_id": responsavel, "created_at": "2026-10-01T12:00:00+00:00"}
        return self.w.sw.table("julia_contatos").insert(row).execute().data[0]

    def captacao(self, contato, n=1, **over):
        row = {"id": str(uuid4()), "org_id": contato["org_id"], "contato_id": contato["id"], "descricao": "Casa de 3 quartos",
               "endereco": "Rua das Flores, 10", "operacao": "venda", "status": "nova", "imovel_id": None, "imovel_codigo": None,
               "created_at": f"2026-10-{n:02d}T12:00:00+00:00", "updated_at": f"2026-10-{n:02d}T12:00:00+00:00"}
        row.update(over)
        return self.w.sw.table("julia_captacoes").insert(row).execute().data[0]


def _scene(role):
    world = World()
    for t in (svc.T_CAPTACOES, envio.T_REGRAS, envio.T_POLITICAS, envio.T_ENTREGAS, "leads", "lead_sources",
              "lead_source_aliases", "cliente_notas", "clientes", "cliente_touches", "atendimentos",
              "imovel_registry", "imovel_captacao", "imovel_dados", "imoveis", "imovel_campo_conflitos"):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"}, {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"}, {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.julia_captacao_router import get_captacao_client

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_captacao_client] = lambda: world.sw
        yield Scene(TestClient(app), world)
        app.dependency_overrides.pop(get_captacao_client, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


class TestAuth:
    @pytest.mark.parametrize("method,url", [("get", BASE), ("post", f"{BASE}/{SEM}/registrar"), ("post", f"{BASE}/{SEM}/descartar")])
    def test_no_token_is_exactly_401(self, admin, method, url):
        assert admin.call(method, url, headers={}).status_code == 401


class TestHandler:
    def _aplicar(self, scene, contato, payload):
        res = TurnResult(conversation_id=str(uuid4()), partes=(), status="respondido", actions=(JuliaAction("captacao", 1, payload),))
        return asyncio.run(acoes.aplicar(scene.w.sw, org_id=ORG_ID, contato=contato, result=res, lote_hash="l1"))

    def test_registered_handler_is_ours_and_composes_the_wave3_policy(self, admin):
        assert acoes.HANDLERS["captacao"] is svc._h_captacao
        c = admin.contato(1)
        (r,) = self._aplicar(admin, c, {"descricao": "Quer vender o apto", "endereco": "Av. Brasil 5", "operacao": "compra"})
        assert r["estado"] == "aplicada"
        (row,) = admin.w.rows("julia_captacoes")
        assert row["status"] == "nova" and row["operacao"] == "venda" and row["contato_id"] == c["id"]
        assert [e["tipo"] for e in admin.w.rows("julia_eventos")] == ["captacao"]  # the wave-3 policy leg ran

    def test_policy_enviar_still_sends_to_the_sw(self, admin):
        admin.w.sw.set_table_data(envio.T_POLITICAS, [{"org_id": ORG_ID, "frios": {"ativo": False}, "captacoes": "enviar",
                                                       "whatsapp_invalido": False, "pesquisa": False}])
        c = admin.contato(2)
        self._aplicar(admin, c, {"descricao": "x"})
        assert admin.w.rows(envio.T_ENTREGAS) and admin.w.rows(envio.T_ENTREGAS)[0]["gatilho"] == "captacao"
        assert len(admin.w.rows("julia_captacoes")) == 1


class TestListar:
    def test_shape_filters_and_paging(self, admin):
        c = admin.contato(1)
        for n in range(1, 8):
            admin.captacao(c, n, status="descartada" if n == 7 else "nova")
        d = admin.call("get", f"{BASE}?page_size=5").json()["data"]
        assert d["total"] == 7 and len(d["items"]) == 5
        assert d["items"][0]["created_at"].startswith("2026-10-07")
        it = d["items"][0]
        assert it["imovel_codigo"] is None and it["contato"]["nome"] == "Pessoa 1" and it["operacao"] == "venda"
        assert len(admin.call("get", f"{BASE}?page_size=5&page=2").json()["data"]["items"]) == 2
        assert admin.call("get", f"{BASE}?status=descartada").json()["data"]["total"] == 1
        assert admin.call("get", f"{BASE}?de=2026-10-03&ate=2026-10-04").json()["data"]["total"] == 2

    @pytest.mark.parametrize("q", ["page_size=7", "status=zzz", "de=2026-10-05&ate=2026-10-01"])
    def test_invalid_params_are_422(self, admin, q):
        assert admin.call("get", f"{BASE}?{q}").status_code == 422

    def test_other_org_rows_are_not_listed(self, admin):
        o = admin.contato(9, org=OTHER_ORG_ID)
        admin.captacao(o)
        assert admin.call("get", BASE).json()["data"]["total"] == 0


class TestA7:
    def test_member_sees_only_own_contatos_and_admin_all(self, member):
        mine, other = member.contato(1, responsavel=TEST_USER_ID), member.contato(2, responsavel=MEMBER_ID)
        a, b = member.captacao(mine), member.captacao(other)
        ids = [i["id"] for i in member.call("get", BASE).json()["data"]["items"]]
        assert ids == [a["id"]]
        assert member.call("post", f"{BASE}/{b['id']}/descartar").status_code == 403
        assert member.call("post", f"{BASE}/{b['id']}/registrar").status_code == 403
        assert member.call("post", f"{BASE}/{a['id']}/descartar").status_code == 204

    def test_admin_sees_all(self, admin):
        admin.captacao(admin.contato(1, responsavel=MEMBER_ID))
        admin.captacao(admin.contato(2, responsavel=OWNER_ID))
        assert admin.call("get", BASE).json()["data"]["total"] == 2

    def test_unknown_and_other_org_ids_are_404(self, admin):
        assert admin.call("post", f"{BASE}/{SEM}/descartar").status_code == 404
        o = admin.captacao(admin.contato(9, org=OTHER_ORG_ID))
        assert admin.call("post", f"{BASE}/{o['id']}/registrar").status_code == 404


class TestAcoes:
    def test_registrar_creates_a_prefilled_imovel_and_links_it(self, admin):
        c = admin.contato(1, responsavel=TEST_USER_ID)
        cap = admin.captacao(c)
        r = admin.call("post", f"{BASE}/{cap['id']}/registrar")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["imovel_id"] and d["imovel_codigo"].startswith("SW-")
        (reg,) = admin.w.rows("imovel_registry")
        assert reg["codigo_canonical"] == d["imovel_id"] and reg["origem_descoberta"] == "manual"
        (ic,) = admin.w.rows("imovel_captacao")
        assert ic["titulo"] == "Rua das Flores, 10" and ic["finalidades"] == ["venda"] and ic["observacoes"] == "Casa de 3 quartos"
        row = admin.w.rows("julia_captacoes")[0]
        assert row["status"] == "registrada" and row["imovel_id"] == d["imovel_id"] and row["imovel_codigo"] == d["imovel_codigo"]
        item = admin.call("get", f"{BASE}?status=registrada").json()["data"]["items"][0]
        assert item["imovel_codigo"] == d["imovel_codigo"]

    def test_registrar_body_overrides_the_prefill(self, admin):
        cap = admin.captacao(admin.contato(1))
        end = {"logradouro": "Alameda X", "numero": "1", "bairro": "B", "cidade": "Cotia", "uf": "SP"}
        assert admin.call("post", f"{BASE}/{cap['id']}/registrar", {"titulo": "Casa Boa", "endereco": end}).status_code == 200
        assert admin.w.rows("imovel_captacao")[0]["titulo"] == "Casa Boa"
        assert admin.call("post", f"{BASE}/{admin.captacao(admin.contato(2))['id']}/registrar", {"x": 1}).status_code == 422

    def test_registrar_twice_is_409_and_creates_no_second_imovel(self, admin):
        cap = admin.captacao(admin.contato(1))
        assert admin.call("post", f"{BASE}/{cap['id']}/registrar").status_code == 200
        r = admin.call("post", f"{BASE}/{cap['id']}/registrar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "captacao_ja_tratada"
        assert len(admin.w.rows("imovel_registry")) == 1
        assert admin.call("post", f"{BASE}/{cap['id']}/descartar").status_code == 409

    def test_descartar_then_registrar_refused_and_descartar_is_idempotent(self, admin):
        cap = admin.captacao(admin.contato(1))
        assert admin.call("post", f"{BASE}/{cap['id']}/descartar").status_code == 204
        assert admin.w.rows("julia_captacoes")[0]["status"] == "descartada"
        assert admin.call("post", f"{BASE}/{cap['id']}/descartar").status_code == 204
        assert admin.call("post", f"{BASE}/{cap['id']}/registrar").status_code == 409
        assert admin.w.rows("imovel_registry") == []
