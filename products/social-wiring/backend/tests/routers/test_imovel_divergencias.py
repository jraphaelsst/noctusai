"""`/api/imoveis/{codigo}/divergencias` (+ `/divergencias/config`): the review API of the TRANSITIONAL Vista-vs-ours check.
Org admin only (strict `== 401` without a session, 403 for a member); resolving 'vista' / 'nosso' / 'manual' and what each writes."""
from __future__ import annotations

import pytest

from tests.routers.test_julia_equipe_protecao import admin, member, override_settings_factory  # noqa: F401
from tests.support.julia_world import ORG_ID

COD = "CA0001"
BASE = f"/api/imoveis/{COD}/divergencias"


def _conflito(i, campo, anterior, proposto, origem, **kw):
    return {"id": i, "org_id": ORG_ID, "codigo": COD, "campo": campo, "valor_anterior": anterior, "origem_anterior": origem,
            "valor_proposto": proposto, "origem_proposto": "vista_sync", "status": "pendente", "decidido_por": None,
            "notas": {"nosso": {"conversa": {"proprietario_contato_id": "p1"}}} if origem == "julia_proprietario" else None,
            "created_at": "2026-11-04T00:00:00+00:00", **kw}


def _cena(scene):
    from app.main import app
    from app.modules.imovel_hub.deps import get_imovel_hub_client
    from app.routers.imovel_divergencias_router import get_divergencias_core

    sw = scene.w.sw
    sw.set_table_data("imovel_campo_conflitos", [
        _conflito("c-cap", "valor_venda", 777.0, 900.0, "captacao_manual"),
        _conflito("c-end", "logradouro", "Rua Nossa", "Rua Deles", "imovel_dados_manual"),
        _conflito("c-emp", "empreendimento", "Cond Nosso", "Cond Deles", "imovel_dados_manual"),
        _conflito("c-prc", "valor_venda", 850.0, 900.0, "julia_proprietario"),
        _conflito("c-dis", "disponibilidade", "indisponivel", "disponivel", "julia_proprietario"),
        _conflito("c-hist", "vagas", 1, 2, "captacao_manual", status="aceito", decidido_por="u"),
        {**_conflito("c-ext", "matricula", "1", "2", "matricula"), "origem_proposto": "matricula"},
    ])
    sw.set_table_data("imovel_captacao", [{"org_id": ORG_ID, "codigo_canonical": COD, "valor_venda": 777.0}])
    sw.set_table_data("imovel_dados", [{"org_id": ORG_ID, "codigo": COD, "endereco_manual_logradouro": "Rua Nossa", "empreendimento_manual": "Cond Nosso",
                                        "empreendimento_manual_confirmado_por": "u", "empreendimento_manual_confirmado_em": "2026-10-01T00:00:00+00:00"}])
    sw.set_table_data("julia_proprietarios_contatos", [{"id": "p1", "org_id": ORG_ID, "imovel_codigo": COD, "preco_confirmado": 850.0,
                                                         "preco_tipo_confirmado": "venda", "status_confirmado": "vendido", "confirmado_at": "2026-11-03T00:00:00+00:00"}])
    sw.set_table_data("vista_divergencias_config", [])
    ov = {get_imovel_hub_client: lambda: sw, get_divergencias_core: lambda: scene.w.root}
    app.dependency_overrides.update(ov)
    yield scene
    for k in ov:
        app.dependency_overrides.pop(k, None)


@pytest.fixture
def cena(admin):  # noqa: F811
    yield from _cena(admin)


@pytest.fixture
def cena_membro(member):  # noqa: F811
    yield from _cena(member)


def _row(scene, i):
    return next(r for r in scene.w.sw.table("imovel_campo_conflitos").select("*").execute().data if r["id"] == i)


class TestAuth:
    @pytest.mark.parametrize("method,url", [("get", BASE), ("post", f"{BASE}/c-cap/resolver"), ("get", "/api/imoveis/divergencias/config"),
                                            ("put", "/api/imoveis/divergencias/config")])
    def test_no_session_is_strictly_401(self, cena, method, url):
        assert getattr(cena.tc, method)(url).status_code == 401

    @pytest.mark.parametrize("method,url,corpo", [("post", f"{BASE}/c-cap/resolver", {"escolha": "nosso"}),
                                                  ("get", "/api/imoveis/divergencias/config", None), ("put", "/api/imoveis/divergencias/config", {"ativa": False})])
    def test_a_member_cannot_resolve_or_configure(self, cena_membro, method, url, corpo):
        assert cena_membro.req(method, url, corpo).status_code == 403
        assert _row(cena_membro, "c-cap")["status"] == "pendente"

    def test_a_member_can_read(self, cena_membro):
        assert cena_membro.req("get", BASE).status_code == 200


class TestListar:
    def test_pending_and_history_only_vista_sync_rows_with_the_notes(self, cena):
        itens = cena.req("get", BASE).json()["items"]
        assert [i["id"] for i in itens][-1] == "c-hist" and {i["id"] for i in itens} == {"c-cap", "c-end", "c-emp", "c-prc", "c-dis", "c-hist"}
        assert {i["status"] for i in itens if i["id"] != "c-hist"} == {"pendente"} and next(i for i in itens if i["id"] == "c-hist")["status"] == "resolvido"
        cap = next(i for i in itens if i["id"] == "c-cap")
        assert (cap["campo"], cap["valor_vista"], cap["valor_nosso"], cap["origem"]) == ("valor_venda", 900.0, 777.0, {"tipo": "captacao"})


class TestResolver:
    def test_nosso_keeps_ours_and_records_the_decision(self, cena):
        r = cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "nosso"})
        assert r.status_code == 200 and r.json()["status"] == "resolvido" and r.json()["resolucao"]["escolha"] == "nosso"
        assert _row(cena, "c-cap")["status"] == "rejeitado" and _row(cena, "c-cap")["motivo_resolucao"] == "nosso"
        assert _row(cena, "c-cap")["decidido_por"]
        assert cena.w.sw.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 777.0  # untouched

    def test_vista_on_a_captacao_value_writes_vistas_value_into_our_record(self, cena):
        r = cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "vista"})
        assert r.status_code == 200 and r.json()["status"] == "resolvido" and r.json()["resolucao"]["escolha"] == "vista"
        assert _row(cena, "c-cap")["status"] == "aceito"
        assert cena.w.sw.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 900.0

    def test_vista_on_a_manual_override_clears_the_override(self, cena):
        assert cena.req("post", f"{BASE}/c-end/resolver", {"escolha": "vista"}).status_code == 200
        assert cena.req("post", f"{BASE}/c-emp/resolver", {"escolha": "vista"}).status_code == 200
        d = cena.w.sw.table("imovel_dados").select("*").execute().data[0]
        assert d["endereco_manual_logradouro"] is None and d["empreendimento_manual"] is None
        assert d["empreendimento_manual_confirmado_por"] is None and d["empreendimento_manual_confirmado_em"] is None

    def test_vista_on_the_owners_confirmation_clears_that_confirmation_only(self, cena):
        assert cena.req("post", f"{BASE}/c-prc/resolver", {"escolha": "vista"}).status_code == 200
        p = cena.w.sw.table("julia_proprietarios_contatos").select("*").execute().data[0]
        assert p["preco_confirmado"] is None and p["preco_tipo_confirmado"] is None and p["status_confirmado"] == "vendido"
        assert cena.req("post", f"{BASE}/c-dis/resolver", {"escolha": "vista"}).status_code == 200
        assert cena.w.sw.table("julia_proprietarios_contatos").select("*").execute().data[0]["status_confirmado"] is None

    def test_manual_types_a_third_value(self, cena):
        assert cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "manual", "valor": "abc"}).status_code == 422  # not a number
        r = cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "manual", "valor": "815.000,50"})  # BR-formatted, as a human types it
        assert r.status_code == 200 and r.json()["resolucao"]["escolha"] == "manual" and r.json()["resolucao"]["valor"] == "815000.5"
        assert cena.w.sw.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 815000.5
        assert _row(cena, "c-cap")["status"] == "aceito"

    @pytest.mark.parametrize("corpo", [{"escolha": "manual"}, {"escolha": "manual", "valor": ""}, {"escolha": "manual", "valor": -3}])
    def test_manual_needs_a_valid_value(self, cena, corpo):
        assert cena.req("post", f"{BASE}/c-cap/resolver", corpo).status_code == 422
        assert _row(cena, "c-cap")["status"] == "pendente"

    def test_availability_manual_value_must_be_disponivel_or_indisponivel(self, cena):
        assert cena.req("post", f"{BASE}/c-dis/resolver", {"escolha": "manual", "valor": "talvez"}).status_code == 422
        assert cena.req("post", f"{BASE}/c-dis/resolver", {"escolha": "manual", "valor": "disponivel"}).status_code == 200

    def test_first_decision_wins_and_unknown_or_foreign_rows_are_404(self, cena):
        assert cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "nosso"}).status_code == 200
        assert cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "vista"}).status_code == 409
        assert cena.req("post", f"{BASE}/nada/resolver", {"escolha": "nosso"}).status_code == 404
        assert cena.req("post", f"{BASE}/c-ext/resolver", {"escolha": "nosso"}).status_code == 404  # not a Vista divergence

    @pytest.mark.parametrize("corpo", [{"escolha": "talvez"}, {}, {"escolha": "nosso", "extra": 1}])
    def test_the_body_is_validated(self, cena, corpo):
        assert cena.req("post", f"{BASE}/c-cap/resolver", corpo).status_code == 422


class TestConfig:
    def test_read_toggle_and_destination(self, cena):
        assert cena.req("get", "/api/imoveis/divergencias/config").json()["data"] == {"ativa": False, "destino_user_id": None}
        r = cena.req("put", "/api/imoveis/divergencias/config", {"ativa": True, "destino_user_id": "00000000-0000-4000-8000-0000000000d1"})
        assert r.status_code == 200 and r.json()["data"] == {"ativa": True, "destino_user_id": "00000000-0000-4000-8000-0000000000d1"}
        r = cena.req("put", "/api/imoveis/divergencias/config", {"ativa": False})
        assert r.json()["data"]["ativa"] is False and r.json()["data"]["destino_user_id"] == "00000000-0000-4000-8000-0000000000d1"
        assert cena.req("put", "/api/imoveis/divergencias/config", {"destino_user_id": None}).json()["data"]["destino_user_id"] is None
        assert cena.req("put", "/api/imoveis/divergencias/config", {"x": 1}).status_code == 422
