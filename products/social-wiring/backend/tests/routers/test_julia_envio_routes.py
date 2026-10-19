"""`/api/julia/envio/*` + `/api/julia/leads/*` (lais-build-contract 5): auth boundary (strict `== 401`), the
member-read / admin-write split, member visibility (A7), org isolation, every live filter, the send routes and the
admin-only CSV export. The DB is the schema-scoped mock injected through the router's own `get_envio_client`
seam; auth is the REAL chain over a mocked session."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import julia_contatos_service as contatos
from app.services import julia_envio_service as envio

from tests.support.julia_world import ADMIN_ID, CONNECTION_ID, CORRETOR_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
SEM = "00000000-0000-4000-8000-0000000000ff"
BASE = [[{"campo": "comportamento", "operador": "=", "valor": "qualificado"}]]


class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def call(self, method, url, body=None, headers=H):
        kw = {"json": body} if body is not None else {}
        return getattr(self.tc, method)(url, headers=headers, **kw)

    def contato(self, n, *, responsavel=None, org=ORG_ID, **over):
        chat = f"551190000{n:04d}@c.us"
        row = {
            "id": f"00000000-0000-4000-8000-0000000c{n:04d}", "org_id": org, "connection_id": CONNECTION_ID, "chat_id": chat, "telefone_e164": f"+551190000{n:04d}",
            "nome": f"Pessoa {n}", "email": None, "operacao": "compra", "slots": {}, "gen": 0, "status_envio": "nao_pronto",
            "canal": "whatsapp", "responsavel_user_id": responsavel, "ultimo_outbound_at": None, "encerrado_at": None,
            "created_at": f"2026-10-{n:02d}T12:00:00+00:00", "campanha_origem": None, "anuncio_origem": None,
        }
        row.update(over)
        return self.w.sw.table("julia_contatos").insert(row).execute().data[0]


def _scene(role):
    world = World()
    for t in (envio.T_REGRAS, envio.T_POLITICAS, envio.T_ENTREGAS, "leads", "lead_sources", "lead_source_aliases",
              "cliente_notas", "clientes", "cliente_touches", "atendimentos"):
        world.sw.set_table_data(t, [])
    world.sw.set_table_data("julia_perguntas_catalogo", [
        {"chave": k, "label": k, "categoria": "lead", "ordem": i, "sensivel": None, "operacao": None}
        for i, k in enumerate(("objetivo", "orcamento", "renda_familiar", "cpf"))])
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
        from app.routers.julia_envio_router import get_envio_client

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_envio_client] = lambda: world.sw
        yield Scene(TestClient(app), world)
        app.dependency_overrides.pop(get_envio_client, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


ROTAS = [
    ("get", "/api/julia/envio/regras", None), ("put", "/api/julia/envio/regras", {"regras": [{"operacao": "ambas", "grupos": BASE}]}),
    ("get", "/api/julia/envio/politicas", None), ("put", "/api/julia/envio/politicas", {"pesquisa": True}),
    ("get", "/api/julia/leads", None), ("get", "/api/julia/leads/canais", None),
    ("post", f"/api/julia/leads/{SEM}/enviar", None), ("post", "/api/julia/leads/enviar-lote", {"ids": [SEM]}),
    ("get", f"/api/julia/leads/{SEM}/resumo", None), ("get", "/api/julia/leads/export.csv", None),
]


class TestAuth:
    @pytest.mark.parametrize("method,url,body", ROTAS)
    def test_no_token_is_exactly_401(self, admin, method, url, body):
        assert admin.call(method, url, body, headers={}).status_code == 401

    def test_a_member_can_read_rules_and_policies(self, member):
        assert member.call("get", "/api/julia/envio/regras").status_code == 200
        assert member.call("get", "/api/julia/envio/politicas").status_code == 200

    @pytest.mark.parametrize("method,url,body", [r for r in ROTAS if r[0] == "put"] + [("get", "/api/julia/leads/export.csv", None)])
    def test_a_member_cannot_write_or_export_403(self, member, method, url, body):
        assert member.call(method, url, body).status_code == 403


class TestRegrasPoliticas:
    def test_regras_roundtrip_without_the_diferenciar_flag(self, admin):
        r = admin.call("put", "/api/julia/envio/regras", {"regras": [{"operacao": "ambas", "grupos": BASE}]})
        assert r.status_code == 200 and r.json()["data"]["regras"][0]["grupos"] == BASE
        two = [{"operacao": "compra", "grupos": BASE}, {"operacao": "aluguel", "grupos": BASE}]
        d = admin.call("put", "/api/julia/envio/regras", {"regras": two}).json()["data"]
        assert d["diferenciar"] is True and sorted(x["operacao"] for x in d["regras"]) == ["aluguel", "compra"]
        assert admin.call("get", "/api/julia/envio/regras").json()["data"] == d

    def test_regras_typed_errors_and_strict_body(self, admin):
        bad = admin.call("put", "/api/julia/envio/regras", {"regras": [{"operacao": "ambas", "grupos": [[{"campo": "orcamento", "operador": "preenchido"}]]}]})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "base_obrigatoria"
        assert admin.call("put", "/api/julia/envio/regras", {"regras": [{"operacao": "ambas", "grupos": BASE}], "x": 1}).status_code == 422
        assert admin.call("put", "/api/julia/envio/regras", {"regras": [{"operacao": "venda", "grupos": BASE}]}).status_code == 422

    def test_politicas_shape_roundtrip_and_validation(self, admin):
        assert admin.call("get", "/api/julia/envio/politicas").json()["data"]["frios"] == {"ativo": False, "modo": "intervalo", "minutos": 60}
        out = admin.call("put", "/api/julia/envio/politicas", {"frios": {"ativo": True, "modo": "manha_seguinte"}, "captacoes": "enviar"}).json()["data"]
        assert out["frios"] == {"ativo": True, "modo": "manha_seguinte", "minutos": 60} and out["captacoes"] == "enviar"
        bad = admin.call("put", "/api/julia/envio/politicas", {"frios": {"minutos": 45}})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "politica_invalida"
        assert admin.call("put", "/api/julia/envio/politicas", {"frios": {"intervalo_minutos": 30}}).status_code == 422  # strict


class TestLeadsList:
    def test_shape_filters_and_pagination(self, admin):
        admin.contato(1, nome="Ana Souza", canal="GrupoZapLais", operacao="compra", slots={"codigo_imovel": "AP0042"})
        admin.contato(2, nome="Bruno", canal="whatsapp", operacao="aluguel", status_envio="erro", ultimo_outbound_at="2026-10-02T13:00:00+00:00",
                      email="b@example.com", campanha_origem="Verão", anuncio_origem="A1")
        admin.contato(3, nome="Carla", canal="whatsapp", operacao="compra", status_envio="enviado_auto", lead_id=None)
        admin.contato(4, nome="Outra org", org=OTHER_ORG_ID)

        def ids(q):
            r = admin.call("get", f"/api/julia/leads?{q}")
            assert r.status_code == 200, r.text
            # sorted: the mock keeps only the LAST `.order()` of a chain; real PostgREST honours created_at desc, id
            return sorted(i["nome"] for i in r.json()["data"]["items"])

        assert ids("") == ["Ana Souza", "Bruno", "Carla"]  # other org never
        assert admin.call("get", "/api/julia/leads").json()["data"]["total"] == 3
        assert ids("nome=ana") == ["Ana Souza"] and ids("email=b@example") == ["Bruno"]
        assert ids("telefone=00002") == ["Bruno"] and ids("imovel=ap004") == ["Ana Souza"]
        assert ids("operacao=aluguel") == ["Bruno"] and sorted(ids("operacao=aluguel&operacao=compra")) == ["Ana Souza", "Bruno", "Carla"]
        assert ids("atendimento=atendido_pela_julia") == ["Bruno"] and ids("atendimento=sem_atendimento") == ["Ana Souza", "Carla"]
        assert ids("atendimento=sem_atendimento&atendimento=atendido_pela_julia") == ["Ana Souza", "Bruno", "Carla"]
        assert ids("status=erro") == ["Bruno"] and ids("status=enviado") == ["Carla"] and ids("status=nao_pronto") == ["Ana Souza"]
        assert sorted(ids("status=erro&status=enviado")) == ["Bruno", "Carla"]
        assert ids("canal=GrupoZapLais") == ["Ana Souza"] and sorted(ids("canal=GrupoZapLais&canal=whatsapp")) == ["Ana Souza", "Bruno", "Carla"]
        assert ids("campanha=ver") == ["Bruno"] and ids("anuncio=a1") == ["Bruno"]
        assert ids("de=2026-10-02&ate=2026-10-02") == ["Bruno"] and ids("de=2026-10-02") == ["Bruno", "Carla"]
        assert ids("link=5511900000001@c.us") == ["Ana Souza"]
        p1 = admin.call("get", "/api/julia/leads?page=1&page_size=2").json()["data"]
        p2 = admin.call("get", "/api/julia/leads?page=2&page_size=2").json()["data"]
        assert (len(p1["items"]), len(p2["items"]), p1["total"], p2["total"]) == (2, 1, 3, 3)
        assert len({i["id"] for i in p1["items"]} | {i["id"] for i in p2["items"]}) == 3

    def test_row_fields_the_page_needs(self, admin):
        c = admin.contato(1)
        admin.call("post", f"/api/julia/leads/{c['id']}/enviar")
        row = admin.call("get", "/api/julia/leads").json()["data"]["items"][0]
        assert row["status"] == "enviado" and row["status_envio"] == "enviado" and row["gatilho"] == "manual"
        assert row["lead_id"] and row["atendido_pela_julia"] is False and row["telefone"] == c["telefone_e164"]
        assert row["connection_id"] and row["chat_id"] and row["enviado_por"] == "manual"

    @pytest.mark.parametrize("q", ["operacao=venda", "status=x", "atendimento=x", "de=2026-10-05&ate=2026-10-01", "page=0", "page_size=101", "de=ontem"])
    def test_bad_filters_are_422(self, admin, q):
        assert admin.call("get", f"/api/julia/leads?{q}").status_code == 422

    def test_a_member_sees_only_the_contatos_they_are_responsavel_for(self, member):
        member.contato(1, nome="Meu", responsavel=TEST_USER_ID)
        member.contato(2, nome="De outro", responsavel=ADMIN_ID)
        member.contato(3, nome="Sem dono")
        assert [i["nome"] for i in member.call("get", "/api/julia/leads").json()["data"]["items"]] == ["Meu"]
        assert member.call("get", "/api/julia/leads").json()["data"]["total"] == 1

    def test_a_member_also_sees_the_contatos_of_a_connection_they_own_when_nobody_is_responsavel(self, member):
        member.w.seed_connection(user_id=TEST_USER_ID)  # CONNECTION_ID is theirs
        member.contato(1, nome="Da minha linha")
        member.contato(2, nome="Com dono", responsavel=ADMIN_ID)
        assert [i["nome"] for i in member.call("get", "/api/julia/leads").json()["data"]["items"]] == ["Da minha linha"]
        assert member.call("get", "/api/julia/leads").json()["data"]["total"] == 1

    def test_an_admin_sees_every_contato_of_the_org(self, admin):
        admin.contato(1, responsavel=ADMIN_ID)
        admin.contato(2, responsavel=MEMBER_ID)
        assert admin.call("get", "/api/julia/leads").json()["data"]["total"] == 2

    def test_canais_is_slug_label_pairs(self, admin):
        out = admin.call("get", "/api/julia/leads/canais").json()["data"]
        assert {"slug": "GrupoZapLais", "label": "Grupo Zap"} in out and all(set(c) == {"slug", "label"} for c in out)


class TestEnviar:
    def test_send_then_409_ja_enviado_returns_the_lead(self, admin):
        c = admin.contato(1)
        r = admin.call("post", f"/api/julia/leads/{c['id']}/enviar")
        assert r.status_code == 200 and r.json()["data"]["status_envio"] == "enviado" and r.json()["data"]["lead_id"]
        again = admin.call("post", f"/api/julia/leads/{c['id']}/enviar")
        assert again.status_code == 409 and again.json()["error"]["code"] == "ja_enviado"
        assert again.json()["error"]["details"]["lead_id"] == r.json()["data"]["lead_id"]
        assert len(admin.w.rows("leads")) == 1

    def test_no_phone_is_422(self, admin):
        c = admin.contato(1, telefone_e164=None, chat_id="x@lid")
        r = admin.call("post", f"/api/julia/leads/{c['id']}/enviar")
        assert r.status_code == 422 and r.json()["error"]["code"] == "contato_sem_telefone"

    def test_unknown_and_other_org_contato_is_404(self, admin):
        other = admin.contato(1, org=OTHER_ORG_ID)
        assert admin.call("post", f"/api/julia/leads/{SEM}/enviar").status_code == 404
        assert admin.call("post", f"/api/julia/leads/{other['id']}/enviar").status_code == 404
        assert admin.call("get", f"/api/julia/leads/{other['id']}/resumo").status_code == 404

    def test_a_member_cannot_send_or_read_someone_elses_contato(self, member):
        c = member.contato(1, responsavel=ADMIN_ID)
        assert member.call("post", f"/api/julia/leads/{c['id']}/enviar").status_code == 403
        assert member.call("get", f"/api/julia/leads/{c['id']}/resumo").status_code == 403
        assert member.w.rows("leads") == []
        assert member.call("post", f"/api/julia/leads/{c['id']}/enviar").json()["error"]["code"] == "sem_acesso"
        mine = member.contato(2, responsavel=TEST_USER_ID)
        assert member.call("post", f"/api/julia/leads/{mine['id']}/enviar").status_code == 200

    def test_lote_reports_ok_and_per_id_errors(self, admin):
        a, b, c = admin.contato(1), admin.contato(2, telefone_e164=None, chat_id="y@lid"), admin.contato(3)
        admin.call("post", f"/api/julia/leads/{c['id']}/enviar")
        out = admin.call("post", "/api/julia/leads/enviar-lote", {"ids": [a["id"], b["id"], c["id"], SEM, a["id"]]}).json()["data"]
        assert out["ok"] == [a["id"]]
        assert sorted((e["id"], e["code"]) for e in out["erro"]) == sorted([
            (b["id"], "contato_sem_telefone"), (c["id"], "ja_enviado"), (SEM, "contato_nao_encontrado")])

    def test_lote_limits_and_strictness(self, admin):
        assert admin.call("post", "/api/julia/leads/enviar-lote", {"ids": []}).status_code == 422
        assert admin.call("post", "/api/julia/leads/enviar-lote", {"ids": [SEM] * 101}).status_code == 422
        assert admin.call("post", "/api/julia/leads/enviar-lote", {"ids": [SEM], "x": 1}).status_code == 422

    def test_lote_for_a_member_skips_what_they_cannot_see(self, member):
        mine, theirs = member.contato(1, responsavel=TEST_USER_ID), member.contato(2, responsavel=ADMIN_ID)
        out = member.call("post", "/api/julia/leads/enviar-lote", {"ids": [mine["id"], theirs["id"]]}).json()["data"]
        assert out == {"ok": [mine["id"]], "erro": [{"id": theirs["id"], "code": "sem_acesso"}]}

    def test_resumo(self, admin):
        c = admin.contato(1, slots={"orcamento": "500000", "cpf": "sha256:abc|final:123"})
        admin.call("post", f"/api/julia/leads/{c['id']}/enviar")
        d = admin.call("get", f"/api/julia/leads/{c['id']}/resumo").json()["data"]
        assert d["slots"] == {"orcamento": "500000"} and d["contato"]["nome"] == "Pessoa 1"
        assert d["entregas"][0]["gatilho"] == "manual" and d["entregas"][0]["status"] == "ok" and d["interacoes"] == []


class TestExport:
    def test_admin_gets_a_csv_with_the_filters_applied(self, admin):
        admin.contato(1, nome="Ana", canal="GrupoZapLais")
        admin.contato(2, nome="=SOMA(A1)", canal="whatsapp")
        r = admin.call("get", "/api/julia/leads/export.csv?canal=whatsapp")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        linhas = r.text.strip().splitlines()
        assert linhas[0].startswith("nome,telefone") and len(linhas) == 2
        assert linhas[1].startswith("'=SOMA(A1)")  # formula injection neutralised

    def test_ids_comma_separated(self, admin):
        a, b = admin.contato(1, nome="Ana"), admin.contato(2, nome="Bia")
        r = admin.call("get", f"/api/julia/leads/export.csv?ids={a['id']},{b['id']}")
        assert len(r.text.strip().splitlines()) == 3
        assert len(admin.call("get", f"/api/julia/leads/export.csv?ids={b['id']}").text.strip().splitlines()) == 2
        assert admin.call("get", "/api/julia/leads/export.csv?ids=nao-e-uuid").status_code == 422
