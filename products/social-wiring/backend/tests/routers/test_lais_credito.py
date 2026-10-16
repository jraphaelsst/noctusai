"""Lais wave 13 -- Analise de credito routes (contract 15 / 17): the A7 list `{data:{items,total}}`, admin-only config
and reprocess (needs a STORED consent), the Interacoes `credito` line, strict `== 401`.
Seams: mock DB through the router's `get_credito_client`, real auth chain over a mocked session."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import lais_credito_provider as prov
from app.services import lais_credito_service as svc

from tests.support.lais_world import ADMIN_ID, CONNECTION_ID, CORRETOR_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
BASE = "/api/lais/credito"
SEM = "00000000-0000-4000-8000-0000000000ff"


class Scene:
    def __init__(self, tc, world, fake):
        self.tc, self.w, self.fake = tc, world, fake

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(url, headers=headers, **kw)

    def contato(self, n, *, responsavel=None, org=ORG_ID, operacao="aluguel"):
        row = {"id": f"00000000-0000-4000-8000-0000000c{n:04d}", "org_id": org, "connection_id": CONNECTION_ID,
               "chat_id": f"551190000{n:04d}@c.us", "telefone_e164": f"+551190000{n:04d}", "nome": f"Pessoa {n}",
               "operacao": operacao, "slots": {}, "gen": 0, "status_envio": "nao_pronto", "canal": "whatsapp",
               "responsavel_user_id": responsavel, "arquivado": False, "bloqueado": False,
               "created_at": "2026-10-01T12:00:00+00:00"}
        return self.w.sw.table("lais_contatos").insert(row).execute().data[0]

    def consent(self, contato, aceito=True):
        return self.w.sw.table(svc.T_CONSENT).insert({
            "id": str(uuid4()), "org_id": contato["org_id"], "contato_id": contato["id"], "aceito": aceito,
            "registrado_at": "2026-10-02T12:00:00+00:00", "texto_versao": "v1"}).execute().data[0]

    def analise(self, contato, n=1, status="aprovado", consent=None):
        consent = consent or self.consent(contato)
        return self.w.sw.table(svc.T_ANALISES).insert({
            "id": str(uuid4()), "org_id": contato["org_id"], "contato_id": contato["id"], "consentimento_id": consent["id"],
            "consentimento_aceito": True, "provider": "fake", "status": status, "resumo": "ok",
            "created_at": f"2026-10-{n:02d}T12:00:00+00:00", "updated_at": f"2026-10-{n:02d}T12:30:00+00:00"}).execute().data[0]

    def ativar(self):
        self.w.sw.set_table_data(svc.T_CONFIG, [{"org_id": ORG_ID, "ativo": True, "provider": "fake", "apenas_aluguel": True}])


def _scene(role):
    world = World()
    for t in (svc.T_CONFIG, svc.T_CONSENT, svc.T_ANALISES, "lais_visitas", "lais_etiquetas", "lais_contato_etiquetas"):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"}, {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"}, {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    fake = prov.FakeCreditoProvider()
    svc.registrar_provider_factory(lambda org, cfg: fake)
    svc.registrar_repo(None)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.lais_credito_router import get_credito_client

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_credito_client] = lambda: world.sw
        yield Scene(TestClient(app), world, fake)
        app.dependency_overrides.pop(get_credito_client, None)
        svc.registrar_provider_factory(None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


class TestAuth:
    @pytest.mark.parametrize("method,url", [
        ("get", BASE), ("get", f"{BASE}/config"), ("put", f"{BASE}/config"), ("post", f"{BASE}/{SEM}/reprocessar"),
    ])
    def test_no_token_is_exactly_401(self, admin, method, url):
        assert admin.call(method, url, headers={}).status_code == 401

    def test_member_cannot_touch_config_or_reprocess(self, member):
        assert member.call("get", f"{BASE}/config").status_code == 403
        assert member.call("put", f"{BASE}/config", {"ativo": False}).status_code == 403
        assert member.call("post", f"{BASE}/{SEM}/reprocessar").status_code == 403


class TestListar:
    def test_shape_filters_and_paging(self, admin):
        c = admin.contato(1)
        for n in range(1, 8):
            admin.analise(c, n, status="reprovado" if n == 7 else "aprovado")
        d = admin.call("get", f"{BASE}?page_size=5").json()["data"]
        assert d["total"] == 7 and len(d["items"]) == 5
        it = d["items"][0]
        assert it["created_at"].startswith("2026-10-07") and it["status"] == "reprovado"
        assert set(it) == {"id", "contato_id", "provider", "status", "resumo", "created_at", "updated_at", "contato"}
        assert it["contato"]["nome"] == "Pessoa 1"
        assert len(admin.call("get", f"{BASE}?page_size=5&page=2").json()["data"]["items"]) == 2
        assert admin.call("get", f"{BASE}?status=reprovado").json()["data"]["total"] == 1

    @pytest.mark.parametrize("q", ["page_size=7", "status=zzz"])
    def test_invalid_params_are_422(self, admin, q):
        assert admin.call("get", f"{BASE}?{q}").status_code == 422

    def test_other_org_rows_are_not_listed(self, admin):
        admin.analise(admin.contato(9, org=OTHER_ORG_ID))
        assert admin.call("get", BASE).json()["data"] == {"items": [], "total": 0}

    def test_a7_member_sees_only_own_contatos_and_admin_all(self, member):
        mine, other = member.contato(1, responsavel=TEST_USER_ID), member.contato(2, responsavel=MEMBER_ID)
        a, _b = member.analise(mine), member.analise(other)
        assert [i["id"] for i in member.call("get", BASE).json()["data"]["items"]] == [a["id"]]

    def test_admin_sees_all(self, admin):
        admin.analise(admin.contato(1, responsavel=MEMBER_ID))
        admin.analise(admin.contato(2, responsavel=OWNER_ID))
        assert admin.call("get", BASE).json()["data"]["total"] == 2


class TestConfig:
    def test_default_then_roundtrip(self, admin):
        d = admin.call("get", f"{BASE}/config").json()["data"]
        assert d == {"ativo": False, "provider": None, "apenas_aluguel": True, "providers": list(prov.PROVIDERS_CONHECIDOS)}
        r = admin.call("put", f"{BASE}/config", {"ativo": True, "provider": "credaluga", "apenas_aluguel": False})
        assert r.status_code == 200 and r.json()["data"] == {"ativo": True, "provider": "credaluga", "apenas_aluguel": False}
        assert admin.call("get", f"{BASE}/config").json()["data"]["provider"] == "credaluga"
        assert len(admin.w.rows(svc.T_CONFIG)) == 1

    @pytest.mark.parametrize("body,code", [
        ({"ativo": True}, "provider_obrigatorio"), ({"ativo": False, "provider": "nada"}, "provider_invalido"),
    ])
    def test_validation(self, admin, body, code):
        r = admin.call("put", f"{BASE}/config", body)
        assert r.status_code == 422 and r.json()["error"]["code"] == code

    def test_unknown_field_is_422(self, admin):
        assert admin.call("put", f"{BASE}/config", {"ativo": False, "x": 1}).status_code == 422


class TestReprocessar:
    def test_without_a_stored_consent_it_is_409_and_never_calls_the_provider(self, admin):
        admin.ativar()
        c = admin.contato(1)
        r = admin.call("post", f"{BASE}/{c['id']}/reprocessar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "consentimento_ausente"
        assert admin.fake.chamadas == [] and admin.w.rows(svc.T_ANALISES) == []

    def test_with_a_refused_consent_it_is_409(self, admin):
        admin.ativar()
        c = admin.contato(1)
        admin.consent(c, aceito=False)
        assert admin.call("post", f"{BASE}/{c['id']}/reprocessar").status_code == 409
        assert admin.fake.chamadas == []

    def test_inactive_org_is_409(self, admin):
        c = admin.contato(1)
        admin.consent(c)
        r = admin.call("post", f"{BASE}/{c['id']}/reprocessar")
        assert r.status_code == 409 and r.json()["error"]["code"] == "credito_desativado"

    def test_with_consent_runs_a_new_analysis(self, admin):
        admin.ativar()
        c = admin.contato(1)
        admin.consent(c)
        r = admin.call("post", f"{BASE}/{c['id']}/reprocessar")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["como"] == "executada"  # no worker repo in the test process: inline
        (a,) = admin.w.rows(svc.T_ANALISES)
        assert a["status"] == "aprovado" and len(admin.fake.chamadas) == 1
        assert admin.call("post", f"{BASE}/{c['id']}/reprocessar").status_code == 200
        assert len(admin.w.rows(svc.T_ANALISES)) == 2

    def test_unknown_and_other_org_contato_are_404(self, admin):
        admin.ativar()
        assert admin.call("post", f"{BASE}/{SEM}/reprocessar").status_code == 404
        o = admin.contato(9, org=OTHER_ORG_ID)
        assert admin.call("post", f"{BASE}/{o['id']}/reprocessar").status_code == 404


class TestInteracoesLine:
    def test_conversas_items_carry_the_latest_credito_or_null(self, admin):
        from app.services import lais_acesso, lais_conversas_service

        com, sem = admin.contato(1), admin.contato(2)
        admin.analise(com, 3, status="reprovado")
        admin.analise(com, 5, status="aprovado")
        ctx = lais_acesso.AcessoCtx(org_id=ORG_ID, user_id=OWNER_ID, admin=True)
        itens, total = lais_conversas_service.listar(admin.w.sw, ctx)
        por_id = {i["contato_id"]: i for i in itens}
        assert total == 2
        assert por_id[com["id"]]["credito"] == {"status": "aprovado", "atualizado_at": "2026-10-05T12:30:00+00:00"}
        assert por_id[sem["id"]]["credito"] is None
