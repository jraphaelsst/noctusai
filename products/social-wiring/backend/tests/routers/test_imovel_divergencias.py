"""`/api/imoveis/{codigo}/divergencias` (+ `/divergencias/config`, `/historico`): the approvals + switches + history API of the
Vista sync. Org admin only for writes (strict `== 401` without a session, 403 for a member); resolving `aprovar` / `recusar` (and the
legacy 'vista' / 'nosso' / 'manual' of the first version) and what each writes.

DECISION REVERSED 2026-11-04: the config is `{ativa, vista_escrita_ativa, vista_escrita_disponivel}` -- the WhatsApp destination
(`destino_user_id`) is gone with the digest."""
from __future__ import annotations

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaConfigError

from tests.routers.test_julia_equipe_protecao import admin, member, override_settings_factory  # noqa: F401
from tests.support.julia_world import ORG_ID

COD = "CA0001"
BASE = f"/api/imoveis/{COD}/divergencias"


def _conflito(i, campo, anterior, proposto, origem, **kw):
    return {"id": i, "org_id": ORG_ID, "codigo": COD, "campo": campo, "valor_anterior": anterior, "origem_anterior": origem,
            "valor_proposto": proposto, "origem_proposto": "vista_sync", "status": "pendente", "decidido_por": None,
            "notas": {"nosso": {"conversa": {"proprietario_contato_id": "p1"}}} if origem == "julia_proprietario" else None,
            "created_at": "2026-11-04T00:00:00+00:00", **kw}


@pytest.fixture(autouse=True)
def _sem_cache_de_permissao():
    from app.services import vista_divergencias

    vista_divergencias._PERMISSAO.clear()
    yield
    vista_divergencias._PERMISSAO.clear()


def _cena(scene):
    from app.main import app
    from app.modules.imovel_hub.deps import get_imovel_hub_client
    from app.routers.imovel_divergencias_router import get_divergencias_core, get_vista_adapter_provider

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
    for t in ("imovel_historico", "imovel_preco_historico", "imovel_notas"):
        sw.set_table_data(t, [])
    sw.set_table_data("imovel_registry", [{"org_id": ORG_ID, "codigo_canonical": COD, "codigo_display": COD}])
    scene.vista = FakeVistaAdapter(imoveis={COD: Imovel(codigo=COD)})
    ov = {get_imovel_hub_client: lambda: sw, get_divergencias_core: lambda: scene.w.root,
          get_vista_adapter_provider: lambda: (lambda _org: scene.vista)}
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


class TestAprovacao:
    def _liga(self, cena, ativa=True):
        cena.w.sw.set_table_data("vista_divergencias_config", [{"org_id": ORG_ID, "ativa": True, "vista_escrita_ativa": ativa}])

    def test_aprovar_with_the_switch_off_records_a_manual_update_and_keeps_the_link(self, cena):
        r = cena.req("post", f"{BASE}/c-prc/resolver", {"escolha": "aprovar"})
        assert r.status_code == 200 and r.json()["status"] == "resolvido" and r.json()["resolucao"]["escolha"] == "aprovar"
        assert _row(cena, "c-prc")["status"] == "aceito" and cena.vista.atualizacoes == []
        [h] = [x for x in cena.w.sw.table("imovel_historico").select("*").execute().data if x["acao"] == "aprovacao_decidida"]
        assert "atualizar manualmente no Vista" in h["detalhe"] and h["conflito_id"] == "c-prc" and h["origem"] == "usuario" and h["ator_user_id"]

    def test_aprovar_with_the_switch_on_and_the_put_permitted_pushes_our_value(self, cena):
        self._liga(cena)
        r = cena.req("post", f"{BASE}/c-prc/resolver", {"escolha": "aprovar"})
        assert r.status_code == 200
        [(cod, campos)] = cena.vista.atualizacoes
        assert cod == COD and campos["ValorVenda"] == "850"
        nota = campos["ObsVenda"]
        assert "aprovação de um usuário" in nota and "(NoctusAI)" in nota and "\n" not in nota  # the reason + author label, one line
        [env] = [x for x in cena.w.sw.table("imovel_historico").select("*").execute().data if x["acao"] == "enviado_ao_vista"]
        assert env["detalhe"] == nota  # mirrored into the history
        acoes = sorted(x["acao"] for x in cena.w.sw.table("imovel_historico").select("*").execute().data)
        assert acoes == ["aprovacao_decidida", "enviado_ao_vista"]

    def test_aprovar_when_the_key_may_not_write_falls_back_to_manual(self, cena):
        self._liga(cena)
        cena.vista.permitir_escrita(False)
        assert cena.req("post", f"{BASE}/c-prc/resolver", {"escolha": "aprovar"}).status_code == 200
        assert cena.vista.atualizacoes == [] and _row(cena, "c-prc")["status"] == "aceito"

    def test_aprovar_a_field_that_is_not_pushable_is_manual_even_with_the_switch_on(self, cena):
        self._liga(cena)
        assert cena.req("post", f"{BASE}/c-dis/resolver", {"escolha": "aprovar"}).status_code == 200
        assert cena.vista.atualizacoes == []

    def test_a_failed_push_still_records_the_approval_and_the_failure(self, cena):
        from noctusai_lib.integrations.vista import VistaUpstreamError

        self._liga(cena)
        cena.vista.permitir_escrita(True, VistaUpstreamError(500, "boom", "/imoveis/detalhes"))
        assert cena.req("post", f"{BASE}/c-prc/resolver", {"escolha": "aprovar"}).status_code == 200
        acoes = sorted(x["acao"] for x in cena.w.sw.table("imovel_historico").select("*").execute().data)
        assert acoes == ["aprovacao_decidida", "envio_vista_falhou"]

    def test_recusar_keeps_vista_and_records_it(self, cena):
        r = cena.req("post", f"{BASE}/c-prc/resolver", {"escolha": "recusar"})
        assert r.status_code == 200 and r.json()["resolucao"]["escolha"] == "recusar" and _row(cena, "c-prc")["status"] == "rejeitado"
        assert cena.vista.atualizacoes == []
        assert [x["acao"] for x in cena.w.sw.table("imovel_historico").select("*").execute().data] == ["aprovacao_decidida"]

    def test_recusar_on_a_legacy_overlay_row_writes_vistas_value_into_our_layer(self, cena):
        assert cena.req("post", f"{BASE}/c-cap/resolver", {"escolha": "recusar"}).status_code == 200
        assert cena.w.sw.table("imovel_captacao").select("*").execute().data[0]["valor_venda"] == 900.0

    def test_aprovar_and_recusar_need_an_admin(self, cena_membro):
        for escolha in ("aprovar", "recusar"):
            assert cena_membro.req("post", f"{BASE}/c-prc/resolver", {"escolha": escolha}).status_code == 403
        assert cena_membro.w.sw.table("imovel_historico").select("*").execute().data == []


class TestConfig:
    def test_read_and_toggle_the_two_switches(self, cena):
        assert cena.req("get", "/api/imoveis/divergencias/config").json()["data"] == {
            "ativa": False, "vista_escrita_ativa": False, "destino_user_id": None, "vista_escrita_disponivel": True}
        r = cena.req("put", "/api/imoveis/divergencias/config", {"ativa": True, "vista_escrita_ativa": True})
        assert r.status_code == 200 and r.json()["data"] == {"ativa": True, "vista_escrita_ativa": True, "destino_user_id": None, "vista_escrita_disponivel": True}
        r = cena.req("put", "/api/imoveis/divergencias/config", {"vista_escrita_ativa": False})
        assert r.json()["data"]["ativa"] is True and r.json()["data"]["vista_escrita_ativa"] is False  # partial update keeps the other
        assert cena.req("put", "/api/imoveis/divergencias/config", {"x": 1}).status_code == 422
        r = cena.req("put", "/api/imoveis/divergencias/config", {"destino_user_id": "00000000-0000-4000-8000-0000000000d1"})
        assert r.status_code == 200 and r.json()["data"]["destino_user_id"] == "00000000-0000-4000-8000-0000000000d1"  # the digest destination is kept
        r = cena.req("put", "/api/imoveis/divergencias/config", {"ativa": False})  # omitted = untouched
        assert r.json()["data"]["destino_user_id"] == "00000000-0000-4000-8000-0000000000d1"
        assert cena.req("put", "/api/imoveis/divergencias/config", {"destino_user_id": None}).json()["data"]["destino_user_id"] is None

    def test_the_switch_defaults_off_when_the_org_has_no_row(self, cena):
        assert cena.req("put", "/api/imoveis/divergencias/config", {"ativa": True}).json()["data"]["vista_escrita_ativa"] is False

    def test_availability_comes_from_the_cached_probe(self, cena):
        cena.vista.permitir_escrita(False)
        assert cena.req("get", "/api/imoveis/divergencias/config").json()["data"]["vista_escrita_disponivel"] is False
        cena.vista.permitir_escrita(True)  # cached: the verdict is not re-probed on every read
        assert cena.req("get", "/api/imoveis/divergencias/config").json()["data"]["vista_escrita_disponivel"] is False

    def test_availability_is_null_when_the_org_has_no_vista_credential(self, cena):
        from app.main import app
        from app.routers.imovel_divergencias_router import get_vista_adapter_provider

        def sem_credencial(_org):
            raise VistaConfigError("sem credencial")

        app.dependency_overrides[get_vista_adapter_provider] = lambda: sem_credencial
        assert cena.req("get", "/api/imoveis/divergencias/config").json()["data"]["vista_escrita_disponivel"] is None


class TestHistorico:
    URL = f"/api/imoveis/{COD}/historico"

    def _semear(self, cena):
        sw = cena.w.sw
        sw.set_table_data("imovel_historico", [
            {"id": "h1", "org_id": ORG_ID, "codigo_canonical": COD, "ocorrido_em": "2026-11-04T10:00:00+00:00", "origem": "vista_sync", "acao": "campo_atualizado",
             "campo": "dormitorios", "valor_anterior": 2, "valor_novo": 3, "ator_user_id": None, "conversa": None, "detalhe": None, "conflito_id": None},
            {"id": "h2", "org_id": ORG_ID, "codigo_canonical": COD, "ocorrido_em": "2026-11-04T11:00:00+00:00", "origem": "julia", "acao": "aprovacao_pendente",
             "campo": "valor_venda", "valor_anterior": 900.0, "valor_novo": 850.0, "ator_user_id": None, "conversa": {"id": "jc-1", "url": "/julia/conversas?contato=jc-1"},
             "detalhe": "x", "conflito_id": "c-prc"},
            {"id": "h3", "org_id": ORG_ID, "codigo_canonical": COD, "ocorrido_em": "2026-11-04T12:00:00+00:00", "origem": "julia", "acao": "enviado_ao_vista",
             "campo": "valor_venda", "valor_anterior": 900.0, "valor_novo": 850.0, "ator_user_id": None, "conversa": {"id": "jc-1", "url": "/julia/conversas?contato=jc-1"},
             "detalhe": "enviado", "conflito_id": None},
            {"id": "h4", "org_id": ORG_ID, "codigo_canonical": COD, "ocorrido_em": "2026-11-04T09:00:00+00:00", "origem": "vista_sync", "acao": "vista_prevaleceu",
             "campo": "logradouro", "valor_anterior": "Rua Nossa", "valor_novo": "Rua Deles", "ator_user_id": None, "conversa": None, "detalhe": None, "conflito_id": None},
            {"id": "h-outro", "org_id": ORG_ID, "codigo_canonical": "OUTRO", "ocorrido_em": "2026-11-04T13:00:00+00:00", "origem": "vista_sync", "acao": "campo_atualizado",
             "campo": "vagas", "valor_anterior": 1, "valor_novo": 2},
        ])
        sw.set_table_data("imovel_preco_historico", [{"id": "pp1", "org_id": ORG_ID, "codigo_canonical": COD, "valor_venda_anterior": 800.0, "valor_venda_novo": 900.0,
                                                    "valor_locacao_anterior": None, "valor_locacao_novo": None, "evento": "alteracao", "fonte": "vista_sync",
                                                    "observado_em": "2026-11-04T08:00:00+00:00"}])
        sw.set_table_data("imovel_notas", [{"id": "n1", "org_id": ORG_ID, "codigo": COD, "texto": "chave com o porteiro", "created_by": None,
                                            "created_at": "2026-11-04T07:00:00+00:00"}])

    def test_no_session_is_strictly_401(self, cena):
        assert cena.tc.get(self.URL).status_code == 401

    def test_merges_history_prices_and_notes_newest_first_with_the_documented_payloads(self, cena_membro):
        self._semear(cena_membro)
        d = cena_membro.req("get", self.URL).json()["data"]
        assert [i["id"] for i in d["items"]] == ["h3", "h2", "h1", "h4", "pp1:valor_venda", "n1"] and d["next_cursor"] is None
        por_id = {i["id"]: i for i in d["items"]}
        assert por_id["h1"]["kind"] == "vista" and por_id["h1"]["payload"] == {"campo": "dormitorios", "rotulo": "dormitórios", "de": 2, "para": 3, "acao": "campo_atualizado"}
        assert por_id["h1"]["ator"] == {"tipo": "vista", "nome": "Vista"} and por_id["h1"]["campo"] == "dormitorios"  # flattened like the lead card
        assert por_id["h4"]["kind"] == "vista" and por_id["h4"]["payload"]["acao"] == "vista_prevaleceu"
        assert por_id["h2"]["kind"] == "aprovacao" and por_id["h2"]["payload"]["conversa"] == {"id": "jc-1", "url": "/julia/conversas?contato=jc-1"}
        assert por_id["h2"]["payload"]["status"] == "pendente" and por_id["h2"]["payload"]["divergencia_id"] == "c-prc"
        assert por_id["h3"]["kind"] == "vista_envio" and por_id["h3"]["ator"] == {"tipo": "julia", "nome": "Julia"}
        assert por_id["pp1:valor_venda"]["kind"] == "preco" and por_id["pp1:valor_venda"]["payload"]["para"] == 900.0
        assert por_id["n1"]["kind"] == "nota" and por_id["n1"]["payload"]["corpo"] == "chave com o porteiro"
        assert "h-outro" not in por_id  # another imóvel's history never leaks in

    def test_a_decided_approval_reports_its_status_from_the_conflict_row(self, cena_membro):
        self._semear(cena_membro)
        cena_membro.w.sw.table("imovel_campo_conflitos").update({"status": "aceito"}).eq("id", "c-prc").execute()
        d = cena_membro.req("get", self.URL).json()["data"]
        assert next(i for i in d["items"] if i["id"] == "h2")["payload"]["status"] == "aprovada"

    def test_pagination_walks_the_whole_thread_by_cursor(self, cena_membro):
        self._semear(cena_membro)
        p1 = cena_membro.req("get", f"{self.URL}?limit=2").json()["data"]
        assert [i["id"] for i in p1["items"]] == ["h3", "h2"] and p1["next_cursor"]
        p2 = cena_membro.req("get", f"{self.URL}?limit=2&cursor={p1['next_cursor']}").json()["data"]
        assert [i["id"] for i in p2["items"]] == ["h1", "h4"]
        p3 = cena_membro.req("get", f"{self.URL}?limit=2&cursor={p2['next_cursor']}").json()["data"]
        assert [i["id"] for i in p3["items"]] == ["pp1:valor_venda", "n1"] and p3["next_cursor"] is None

    def test_a_bad_cursor_is_a_400_and_an_unknown_imovel_a_404(self, cena_membro):
        assert cena_membro.req("get", f"{self.URL}?cursor=nao-e-cursor").status_code == 400
        assert cena_membro.req("get", "/api/imoveis/NAOEXISTE/historico").status_code == 404

    def test_limit_is_bounded(self, cena_membro):
        assert cena_membro.req("get", f"{self.URL}?limit=0").status_code == 422
        assert cena_membro.req("get", f"{self.URL}?limit=101").status_code == 422
