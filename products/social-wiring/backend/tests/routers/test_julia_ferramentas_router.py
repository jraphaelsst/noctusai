"""`POST /api/julia/ferramentas/{nome}` (lais-build-contract A3 / 2.2): the four read tools agents
calls back with its org's tools token.

Auth is the agents-bridge pattern; every 401 is strict `== 401`. The auth context is the honest DI
seam (`dependency_overrides[get_auth_context]`) for the 403/200 matrix; the two 401 cases run the
REAL, un-overridden chain. No personal data in fixtures; the catalogue rows carry planted
owner/internal columns the tools must never return."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.testing import MockSupabaseClient

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_OTHER = UUID("00000000-0000-4000-8000-0000000000bb")
_SCOPE = "social-wiring:lais-tools"
URL = "/api/julia/ferramentas"
OWNER_SECRET = "PLANTED-OWNER-NAME"


def _row(codigo, org=_ORG, **over):
    row = {
        "org_id": str(org), "codigo": codigo, "codigo_norm": codigo.upper(), "titulo": f"Casa {codigo}",
        "categoria": "Casa", "status": "Venda", "finalidades": ["venda"], "bairro": "Granja Viana",
        "cidade": "Cotia", "uf": "SP", "valor_venda": 900000, "valor_locacao": None, "valor_condominio": 1200,
        "valor_iptu": 450, "dormitorios": 3, "suites": 1, "vagas": 2, "area_total": 300, "area_privativa": 200,
        "descricao_web": "Ótima casa.", "caracteristicas": ["piscina"], "exibir_no_site": True,
        "logradouro": "Rua Teste", "numero": "10", "data_atualizacao": "2026-10-01",
        # planted: never selectable by a tool
        "corretores": [{"nome": OWNER_SECRET}], "vista_raw": {"Proprietario": OWNER_SECRET}, "observacoes": OWNER_SECRET,
        "chave": OWNER_SECRET, "matricula_vista": OWNER_SECRET,
    }
    row.update(over)
    return row


@pytest.fixture
def catalogo():
    db = MockSupabaseClient()
    db.set_table_data("imoveis", [
        _row("CA1"),
        _row("CA2", valor_venda=2_000_000, dormitorios=5, bairro="Alphaville"),
        _row("AP1", finalidades=["aluguel"], valor_venda=None, valor_locacao=4500, categoria="Apartamento", dormitorios=2),
        _row("HID", exibir_no_site=False),
        _row("OTH", org=_OTHER),
    ])
    return db


@pytest.fixture
def tools(client, catalogo):
    from app.dependencies import get_auth_context
    from app.main import app
    from app.routers.julia_ferramentas_router import get_ferramentas_client

    app.dependency_overrides[get_ferramentas_client] = lambda: catalogo
    prev = app.dependency_overrides.get(get_auth_context)

    class T:
        raw = client.raw()

        def as_ctx(self, ctx):
            app.dependency_overrides[get_auth_context] = lambda: ctx

        def post(self, nome, body=None):
            return self.raw.post(f"{URL}/{nome}", json=body if body is not None else {})

    yield T()
    app.dependency_overrides.pop(get_ferramentas_client, None)
    if prev is None:
        app.dependency_overrides.pop(get_auth_context, None)
    else:
        app.dependency_overrides[get_auth_context] = prev


def _product(*, scopes=(_SCOPE,), issuer="agents", org=_ORG):
    return AuthContext(org_id=org, caller_kind="product", user_id=None, scopes=list(scopes),
                       raw_token="t", api_token_id=uuid4(), issuer=issuer)


def _user():
    return AuthContext(org_id=_ORG, caller_kind="user", user_id=uuid4(), scopes=[], raw_token="s", api_token_id=None)


@pytest.fixture
def ok(tools):
    tools.as_ctx(_product())
    return tools


class TestAuthMatrix:
    def test_no_credential_is_exactly_401(self, tools):
        assert tools.post("buscar_imoveis", {"operacao": "compra"}).status_code == 401

    def test_an_invalid_token_is_exactly_401(self, tools):
        r = tools.raw.post(f"{URL}/buscar_imoveis", json={"operacao": "compra"}, headers={"Authorization": "Bearer pk_" + "0" * 64})
        assert r.status_code == 401

    def test_an_unknown_tool_without_credentials_is_still_401_not_404(self, tools):
        assert tools.post("nao_existe").status_code == 401

    def test_a_human_session_is_403_product_required(self, tools):
        tools.as_ctx(_user())
        r = tools.post("buscar_imoveis", {"operacao": "compra"})
        assert r.status_code == 403 and r.json()["code"] == "product_required"

    def test_a_product_token_without_the_scope_is_403_scope_missing(self, tools):
        tools.as_ctx(_product(scopes=["social-wiring:one-chat:read"]))
        r = tools.post("buscar_imoveis", {"operacao": "compra"})
        assert r.status_code == 403 and r.json()["code"] == "scope_missing"

    def test_another_issuer_with_the_same_scope_is_403_issuer_not_allowed(self, tools):
        tools.as_ctx(_product(issuer="outro-produto"))
        r = tools.post("buscar_imoveis", {"operacao": "compra"})
        assert r.status_code == 403 and r.json()["code"] == "issuer_not_allowed"

    def test_a_token_with_no_issuer_is_refused_too(self, tools):
        tools.as_ctx(_product(issuer=None))
        assert tools.post("buscar_imoveis", {"operacao": "compra"}).status_code == 403


class TestRouting:
    def test_an_unknown_tool_is_404_ferramenta_desconhecida(self, ok):
        r = ok.post("apagar_tudo")
        assert r.status_code == 404 and r.json()["error"]["code"] == "ferramenta_desconhecida"

    @pytest.mark.parametrize("nome,corpo", [
        ("buscar_imoveis", {}),
        ("buscar_imoveis", {"operacao": "troca"}),
        ("buscar_imoveis", {"operacao": "compra", "limite": 6}),
        ("buscar_imoveis", {"operacao": "compra", "org_id": str(_OTHER)}),  # a body can never pick the org
        ("detalhes_imovel", {}),
        ("detalhes_imovel", {"codigo": "CA1", "x": 1}),
        ("horarios_visita", {"dias": 8}),
        ("consultar_empreendimento", {}),
    ])
    def test_a_bad_body_is_422_invalid_field(self, ok, nome, corpo):
        r = ok.post(nome, corpo)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_field"

    def test_success_is_the_data_envelope(self, ok):
        r = ok.post("buscar_imoveis", {"operacao": "compra"})
        assert r.status_code == 200 and set(r.json()) == {"data", "restantes_estimados", "relaxado"}
        assert set(ok.post("horarios_visita", {}).json()) == {"data"}


class TestBuscarImoveis:
    def test_returns_the_contract_shape_for_the_callers_org_only(self, ok):
        data = ok.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]
        assert {d["codigo"] for d in data} == {"CA1", "CA2"}  # not OTH (other org), not HID (unpublished), not AP1 (rent)
        # absent fields are OMITTED (no link pattern saved => no `link`; no suites/condominio => no key)
        assert set(data[0]) == {"codigo", "titulo", "tipo", "bairro", "cidade", "preco", "preco_venda", "valor_condominio", "valor_iptu",
                                "area_m2", "quartos", "suites", "vagas", "destaques"}
        ca1 = next(d for d in data if d["codigo"] == "CA1")
        assert (ca1["preco"], ca1["quartos"], ca1["bairro"], ca1["tipo"]) == (900000.0, 3, "Granja Viana", "Casa")

    def test_another_orgs_token_sees_another_catalogue(self, tools):
        tools.as_ctx(_product(org=_OTHER))
        assert [d["codigo"] for d in tools.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]] == ["OTH"]

    def test_filters(self, ok):
        def codes(**f):
            # limite=1: a strict hit exists, so no widening step runs (those are covered in test_julia_busca_imoveis)
            return {d["codigo"] for d in ok.post("buscar_imoveis", {"operacao": "compra", "limite": 1, **f}).json()["data"]}

        assert codes(preco_max=1_000_000) == {"CA1"}
        assert codes(quartos_min=4) == {"CA2"}
        assert codes(bairro="alphaville") == {"CA2"}
        assert codes(cidade="cotia") <= {"CA1", "CA2"} and len(codes(cidade="cotia")) == 1
        # nothing is an apartment: the typology widens and says so
        r = ok.post("buscar_imoveis", {"operacao": "compra", "tipo": "apart"}).json()
        assert r["relaxado"] == ["tipologia"] and {d["codigo"] for d in r["data"]} == {"CA1", "CA2"}
        r = ok.post("buscar_imoveis", {"operacao": "aluguel", "preco_max": 5000}).json()["data"]
        assert [(d["codigo"], d["preco"]) for d in r] == [("AP1", 4500.0)]

    def test_the_limit_is_honoured_and_capped_at_five(self, tools, catalogo):
        catalogo.set_table_data("imoveis", [_row(f"M{i}") for i in range(9)])
        tools.as_ctx(_product())
        assert len(tools.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]) == 3  # default lote
        assert len(tools.post("buscar_imoveis", {"operacao": "compra", "limite": 5}).json()["data"]) == 5
        assert len(tools.post("buscar_imoveis", {"operacao": "compra", "limite": 2}).json()["data"]) == 2

    def test_unpublished_listings_do_not_eat_the_limit(self, tools, catalogo):
        catalogo.set_table_data("imoveis", [_row(f"H{i}", exibir_no_site=False) for i in range(5)] + [_row("PUB")])
        tools.as_ctx(_product())
        assert [d["codigo"] for d in tools.post("buscar_imoveis", {"operacao": "compra", "limite": 1}).json()["data"]] == ["PUB"]


class TestLinkDoImovel:
    def test_no_site_saved_means_no_link(self, ok):
        assert {d.get("link") for d in ok.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]} == {None}

    def test_the_default_template_builds_site_imovel_codigo(self, tools, catalogo):
        catalogo.set_table_data("julia_conhecimento_secoes", [
            {"org_id": str(_ORG), "secao": "perfil_whatsapp", "versao": 1, "dados": {"site": "imobiliaria.example/"}},
        ])
        tools.as_ctx(_product())
        data = tools.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]
        assert {d["codigo"]: d["link"] for d in data} == {
            "CA1": "https://imobiliaria.example/imovel/CA1", "CA2": "https://imobiliaria.example/imovel/CA2",
        }
        assert tools.post("detalhes_imovel", {"codigo": "ca1"}).json()["data"]["link"] == "https://imobiliaria.example/imovel/CA1"

    def test_a_custom_template_and_an_empty_one(self, tools, catalogo):
        dados = {"site": "https://imobiliaria.example", "link_imovel": "{site}/anuncio?ref={codigo}"}
        catalogo.set_table_data("julia_conhecimento_secoes", [
            {"org_id": str(_ORG), "secao": "perfil_whatsapp", "versao": 1, "dados": dados},
        ])
        tools.as_ctx(_product())
        assert tools.post("detalhes_imovel", {"codigo": "CA1"}).json()["data"]["link"] == "https://imobiliaria.example/anuncio?ref=CA1"
        catalogo.set_table_data("julia_conhecimento_secoes", [
            {"org_id": str(_ORG), "secao": "perfil_whatsapp", "versao": 1, "dados": {**dados, "link_imovel": ""}},
        ])
        assert tools.post("detalhes_imovel", {"codigo": "CA1"}).json()["data"]["link"] is None

    def test_another_orgs_site_never_builds_this_orgs_links(self, tools, catalogo):
        catalogo.set_table_data("julia_conhecimento_secoes", [
            {"org_id": str(_OTHER), "secao": "perfil_whatsapp", "versao": 1, "dados": {"site": "outra.example"}},
        ])
        tools.as_ctx(_product())
        assert {d.get("link") for d in tools.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]} == {None}


class TestDetalhesImovel:
    def test_returns_the_contract_shape_with_iptu_and_street_withheld_until_wave_1(self, ok):
        d = ok.post("detalhes_imovel", {"codigo": "ca1"}).json()["data"]  # case-insensitive code
        assert set(d) == {"codigo", "titulo", "descricao", "preco", "condominio", "iptu", "endereco", "caracteristicas", "link",
                          "encontrado"}
        assert d["encontrado"] is True and d["preco"] == 900000.0 and d["condominio"] == 1200.0
        assert d["iptu"] is None
        assert d["endereco"] == "Granja Viana, Cotia"
        assert "Rua Teste" not in str(d) and d["caracteristicas"] == ["piscina"]

    def test_a_missing_hidden_or_foreign_imovel_is_reported_not_found_and_leaks_nothing(self, ok):
        for codigo in ("NADA", "HID", "OTH"):
            assert ok.post("detalhes_imovel", {"codigo": codigo}).json()["data"] == {"codigo": codigo, "encontrado": False}


class TestNeverReturnsOwnerData:
    def test_no_tool_response_contains_a_planted_owner_or_internal_value(self, ok):
        bodies = [
            ok.post("buscar_imoveis", {"operacao": "compra"}).text,
            ok.post("buscar_imoveis", {"operacao": "aluguel"}).text,
            ok.post("detalhes_imovel", {"codigo": "CA1"}).text,
            ok.post("horarios_visita", {}).text,
            ok.post("consultar_empreendimento", {"nome": "X"}).text,
        ]
        assert all(OWNER_SECRET not in b for b in bodies)

    def test_the_column_allow_list_excludes_every_owner_and_internal_column(self):
        from app.services.julia_ferramentas_service import COLUNAS

        cols = {c.strip() for c in COLUNAS.split(",")}
        assert not cols & {"corretores", "vista_raw", "observacoes", "chave", "matricula_vista", "inscricao_municipal",
                           "caracteristicas_raw", "referencia"}


class TestHorarios:
    def test_horarios_answer_an_empty_list_without_a_visit_config(self, ok):
        assert ok.post("horarios_visita", {"codigo": "CA1", "dias": 3}).json() == {"data": []}


class TestConsultarEmpreendimento:
    @pytest.fixture
    def predios(self, tools, catalogo):
        catalogo.set_table_data("imoveis", [
            _row("E1", empreendimento="Edifício Aurora", construtora="Construtora Alfa", categoria="Apartamento",
                 dormitorios=2, valor_venda=500000, area_privativa=60),
            _row("E2", empreendimento="edifício aurora", categoria="Apartamento", dormitorios=3, valor_venda=700000,
                 area_privativa=90),
            _row("E3", empreendimento="Edifício Aurora", exibir_no_site=False, valor_venda=1),
            _row("E4", empreendimento="Edifício Aurora", org=_OTHER),
            _row("E5", empreendimento="Outro Prédio", valor_venda=300000),
            _row("E6", empreendimento=None),
        ])
        tools.as_ctx(_product())
        return tools

    def test_serves_the_development_from_the_vista_mirror(self, predios):
        data = predios.post("consultar_empreendimento", {"nome": "aurora"}).json()["data"]
        assert len(data) == 1
        e = data[0]
        assert e["nome"] == "Edifício Aurora" and e["construtora"] == "Construtora Alfa"
        assert e["unidades"] == 2  # hidden + other org's + other building excluded
        assert e["quartos"] == {"min": 2.0, "max": 3.0} and e["preco_venda"] == {"min": 500000.0, "max": 700000.0}
        assert e["preco_locacao"] is None and e["tipos"] == ["Apartamento"]
        assert {x["codigo"] for x in e["exemplos"]} == {"E1", "E2"}

    def test_no_match_is_an_empty_list_and_leaks_no_owner_data(self, predios):
        assert predios.post("consultar_empreendimento", {"nome": "inexistente"}).json() == {"data": []}
        assert OWNER_SECRET not in predios.post("consultar_empreendimento", {"nome": "Outro"}).text

    def test_the_allow_list_excludes_owner_columns(self):
        from app.services.julia_ferramentas_service import COLUNAS_EMPREENDIMENTO

        cols = {c.strip() for c in COLUNAS_EMPREENDIMENTO.split(",")}
        assert not cols & {"corretores", "vista_raw", "observacoes", "chave", "matricula_vista"}


class TestRegistroDeConsultas:
    @staticmethod
    def _eventos(catalogo):
        return catalogo.table("julia_eventos").select("*").execute().data or []

    @pytest.fixture
    def mundo(self, catalogo):
        catalogo.set_table_data("julia_eventos", [])
        catalogo.set_table_data("julia_interacoes", [
            {"id": "00000000-0000-4000-8000-000000000001", "org_id": str(_ORG), "contato_id": "c-1"},
            {"id": "00000000-0000-4000-8000-000000000002", "org_id": str(_OTHER), "contato_id": "c-other"},
        ])
        return catalogo

    def test_a_search_records_the_codes_returned_with_the_contato_of_the_turn(self, ok, mundo):
        iid = "00000000-0000-4000-8000-000000000001"
        assert ok.post("buscar_imoveis", {"operacao": "compra", "interacao_id": iid}).status_code == 200
        (ev,) = self._eventos(mundo)
        assert (ev["tipo"], ev["org_id"], ev["contato_id"]) == ("imovel_consultado", str(_ORG), "c-1")
        assert sorted(ev["payload"]["codigos"]) == ["CA1", "CA2"] and ev["payload"]["ferramenta"] == "buscar_imoveis"

    def test_a_detail_view_records_the_viewed_code_but_not_a_miss(self, ok, mundo):
        iid = "00000000-0000-4000-8000-000000000001"
        ok.post("detalhes_imovel", {"codigo": "ca1", "interacao_id": iid})
        ok.post("detalhes_imovel", {"codigo": "NADA", "interacao_id": iid})
        (ev,) = self._eventos(mundo)
        assert ev["payload"]["codigos"] == ["CA1"]

    def test_an_interacao_of_another_org_is_never_resolved(self, ok, mundo):
        ok.post("buscar_imoveis", {"operacao": "compra", "interacao_id": "00000000-0000-4000-8000-000000000002"})
        (ev,) = self._eventos(mundo)
        assert ev["contato_id"] is None  # stored (the lookup happened) but tied to nobody

    def test_without_an_interacao_the_lookup_is_stored_anonymous_and_empty_results_store_nothing(self, ok, mundo):
        ok.post("buscar_imoveis", {"operacao": "compra"})
        ok.post("buscar_imoveis", {"operacao": "compra", "bairro": "nenhum-bairro"})
        (ev,) = self._eventos(mundo)
        assert ev["contato_id"] is None


class TestConfirmacaoDoProprietario:
    """Owner-confirmed status/price (Julia-owned storage) overlaid on the Vista value when newer, with provenance."""
    VISTA_DIA = "2026-10-01"

    @pytest.fixture
    def conf(self, tools, catalogo):
        catalogo.set_table_data("julia_proprietarios_contatos", [])
        tools.as_ctx(_product())

        def confirmar(codigo, *, quando, status=None, preco=None, tipo="venda", org=_ORG):
            catalogo.table("julia_proprietarios_contatos").insert({
                "id": str(uuid4()), "org_id": str(org), "imovel_codigo": codigo, "telefone": "5511999990000",
                "nome": OWNER_SECRET, "status_confirmado": status, "preco_confirmado": preco,
                "preco_tipo_confirmado": tipo if preco is not None else None, "confirmado_at": quando}).execute()

        tools.confirmar = confirmar
        return tools

    def test_a_newer_confirmation_wins_with_provenance_in_search_and_details(self, conf):
        conf.confirmar("CA1", quando="2026-10-10T15:00:00+00:00", status="Suspenso", preco=850000)
        item = next(d for d in conf.post("buscar_imoveis", {"operacao": "compra"}).json()["data"] if d["codigo"] == "CA1")
        assert item["preco"] == 850000.0
        assert item["confirmacao_proprietario"] == {
            "status": "Suspenso", "preco": 850000.0, "preco_tipo": "venda", "em": "2026-10-10",
            "provenance": "confirmado pelo proprietário em 10/10/2026"}
        d = conf.post("detalhes_imovel", {"codigo": "ca1"}).json()["data"]
        assert d["preco"] == 850000.0 and d["confirmacao_proprietario"]["status"] == "Suspenso"
        assert OWNER_SECRET not in str(d) and "5511999990000" not in str(d)

    def test_a_confirmation_not_newer_than_the_vista_edit_loses_and_adds_nothing(self, conf):
        conf.confirmar("CA1", quando="2026-10-01T12:00:00+00:00", preco=850000)   # same day as Vista's edit
        conf.confirmar("CA2", quando="2026-09-20T12:00:00+00:00", status="Vendido")  # older
        for item in conf.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]:
            assert "confirmacao_proprietario" not in item
        assert next(d for d in conf.post("buscar_imoveis", {"operacao": "compra"}).json()["data"] if d["codigo"] == "CA1")["preco"] == 900000.0

    def test_status_and_price_come_from_the_newest_row_that_has_each(self, conf):
        conf.confirmar("CA1", quando="2026-10-05T12:00:00+00:00", preco=800000)
        conf.confirmar("CA1", quando="2026-10-12T12:00:00+00:00", status="Reservado")
        c = conf.post("detalhes_imovel", {"codigo": "CA1"}).json()["data"]["confirmacao_proprietario"]
        assert (c["status"], c["preco"], c["em"]) == ("Reservado", 800000.0, "2026-10-12")

    def test_the_price_kind_must_match_the_operation_and_an_unknown_kind_never_overrides_a_price(self, conf):
        conf.confirmar("CA1", quando="2026-10-10T12:00:00+00:00", preco=5000, tipo="locacao")
        conf.confirmar("CA2", quando="2026-10-10T12:00:00+00:00", preco=1, tipo=None)
        rows = {d["codigo"]: d for d in conf.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]}
        assert rows["CA1"]["preco"] == 900000.0 and "confirmacao_proprietario" not in rows["CA1"]
        assert rows["CA2"]["preco"] == 2000000.0

    def test_another_orgs_confirmation_is_never_applied(self, conf):
        conf.confirmar("CA1", quando="2026-10-10T12:00:00+00:00", status="Vendido", org=_OTHER)
        assert "confirmacao_proprietario" not in conf.post("detalhes_imovel", {"codigo": "CA1"}).json()["data"]
