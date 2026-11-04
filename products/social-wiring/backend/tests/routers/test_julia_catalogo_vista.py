"""Julia live catalog (CONTRACT 12.7, migration 314): the per-org source (`GET|PUT /api/julia/catalogo-fonte`) and the three
listing tools reading Vista LIVE through the seed `FakeVistaAdapter` (the DI slot `configure_vista_adapter`).

The tools' auth matrix lives in test_julia_ferramentas_router; here every 401 is strict `== 401` and a member is 403. No
personal data in fixtures; the Vista `Imovel`s carry planted owner / internal fields the tools must never return."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.integrations.vista.client import VistaUpstreamError

from app.services import julia_catalogo_service as cat
from app.services import julia_busca_imoveis as busca
from tests.routers.test_julia_equipe_protecao import admin, member, override_settings_factory  # noqa: F401
from tests.routers.test_julia_ferramentas_router import _ORG, OWNER_SECRET, _product, _row, catalogo, ok, tools  # noqa: F401

URL = "/api/julia/catalogo-fonte"
H = {"Authorization": "Bearer test-token"}


def _imovel(codigo, **over) -> Imovel:
    base = dict(
        codigo=codigo, titulo=f"Casa {codigo}", categoria="Casa", status="Venda", finalidades=frozenset({"venda"}),
        bairro="Granja Viana", cidade="Cotia", uf="SP", valor_venda=900_000.0, valor_condominio=1200.0, valor_iptu=450.0,
        dormitorios=3, suites=1, vagas=2, area_total=300.0, area_privativa=200.0, descricao_web="Ótima casa.",
        caracteristicas=frozenset({"piscina"}), exibir_no_site=True, logradouro="Rua Teste", numero="10",
        data_atualizacao=date(2026, 10, 1),
        # planted: never reachable by a tool
        observacoes=OWNER_SECRET, chave=OWNER_SECRET, matricula_vista=OWNER_SECRET, vista_raw={"Proprietario": OWNER_SECRET},
    )
    base.update(over)
    return Imovel(**base)


class _Espiao(FakeVistaAdapter):
    """A Fake that records the filters it was asked for (a subclass, not a patch)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.filtros: list[dict] = []
        self.chamadas = 0

    async def search_imoveis(self, *, filter_=None, order=None, max_results=200, with_detalhes=False):
        self.chamadas += 1
        self.filtros.append(filter_ or {})
        return await super().search_imoveis(filter_=filter_, order=order, max_results=max_results, with_detalhes=with_detalhes)


@pytest.fixture
def vista(tools, catalogo):  # noqa: F811
    fake = _Espiao()
    for i in [
        _imovel("CAMP", empreendimento="Cond Alfa", valor_venda=1_000_000.0, caracteristicas=frozenset({"piscina"})),
        _imovel("IRMA", empreendimento="Cond Alfa", valor_venda=1_050_000.0),
        _imovel("VIZ", valor_venda=950_000.0, caracteristicas=frozenset({"sauna", "churrasqueira", "piscina"})),
        _imovel("APT", categoria="Apartamento", valor_venda=980_000.0),
        _imovel("CARO", valor_venda=3_000_000.0),
        _imovel("HID", exibir_no_site=False),
        _imovel("ALU", status="Aluguel", finalidades=frozenset({"aluguel"}), valor_venda=None, valor_locacao=4500.0),
    ]:
        fake.add_imovel(i)
    catalogo.set_table_data("julia_catalogo_config", [{"org_id": str(_ORG), "fonte": "vista"}])
    catalogo.set_table_data("imoveis", [_row("SO_NO_ESPELHO")])  # must never appear while the org reads Vista
    cat.configure_vista_adapter(lambda: fake)
    tools.as_ctx(_product())
    tools.fake = fake
    yield tools
    cat.configure_vista_adapter(None)


def _buscar(t, **body):
    r = t.post("buscar_imoveis", {"operacao": "compra", **body})
    assert r.status_code == 200, r.text
    return r.json()


class TestFerramentasNaVista:
    def test_the_search_reads_vista_not_the_mirror_and_never_offers_unpublished_or_other_operation(self, vista):
        got = {d["codigo"] for d in _buscar(vista, limite=5)["data"]}
        assert "SO_NO_ESPELHO" not in got and "HID" not in got and "ALU" not in got
        assert got <= {"CAMP", "IRMA", "VIZ", "APT", "CARO"} and len(got) == 5
        assert [d["codigo"] for d in vista.post("buscar_imoveis", {"operacao": "aluguel"}).json()["data"]] == ["ALU"]

    def test_the_card_has_the_same_shape_and_values_as_the_mirror(self, vista):
        d = next(x for x in _buscar(vista, limite=5)["data"] if x["codigo"] == "VIZ")
        assert d["preco"] == 950_000.0 and d["quartos"] == 3 and d["suites"] == 1 and d["vagas"] == 2
        assert d["valor_condominio"] == 1200.0 and d["valor_iptu"] == 450.0 and d["area_m2"] == 200.0
        assert d["bairro"] == "Granja Viana" and d["cidade"] == "Cotia" and d["tipo"] == "Casa"
        assert set(d["destaques"]) == {"sauna", "churrasqueira", "piscina"}

    def test_similar_a_excluir_and_relaxado_keep_their_semantics(self, vista):
        r = _buscar(vista, similar_a="camp", limite=2)
        assert [d["codigo"] for d in r["data"]] == ["IRMA", "VIZ"] and r["similar_a_encontrado"] is True and r["relaxado"] == []
        assert _buscar(vista, similar_a="NADA", limite=2)["similar_a_encontrado"] is False
        got = {d["codigo"] for d in _buscar(vista, excluir_codigos=["irma", "VIZ"], limite=5)["data"]}
        assert not got & {"IRMA", "VIZ"}
        r = _buscar(vista, preco_max=900_000, tipo="casa", limite=3)
        assert "preco" in r["relaxado"]

    def test_esgotado_is_a_short_list_with_nothing_remaining(self, vista):
        r = _buscar(vista, preco_min=2_900_000, preco_max=3_000_000, limite=3)
        assert [d["codigo"] for d in r["data"]] == ["CARO"] and r["restantes_estimados"] == 0

    def test_essential_items_filter_on_vista_features(self, vista):
        assert [d["codigo"] for d in _buscar(vista, itens_essenciais=["churrasqueira"], limite=3)["data"]] == ["VIZ"]
        r = _buscar(vista, itens_essenciais=["pets"], limite=3)
        assert len(r["data"]) == 3 and r["itens_nao_verificaveis"] == ["pets"]

    def test_the_vista_filter_is_built_from_the_args(self, vista):
        _buscar(vista, preco_min=800_000, preco_max=1_000_000, quartos_min=3, vagas_min=2, bairro="Granja Viana", cidade="Cotia")
        f = next(x for x in vista.fake.filtros if "Status" in x)
        assert f["Status"] == ["Venda", "Venda e Aluguel"] and f["ExibirNoSite"] == "Sim"
        assert f["ValorVenda"] == [800_000 * 0.85, 1_000_000 * 1.2] and f["Dormitorios"] == [">=", 2] and f["Vagas"] == [">=", 2]
        assert f["Bairro"] == ["like", "%Granja Viana%"] and f["Cidade"] == ["like", "%Cotia%"]

    def test_details_and_campaign_read_vista_and_hide_unpublished(self, vista):
        d = vista.post("detalhes_imovel", {"codigo": "viz"}).json()["data"]
        assert d["encontrado"] is True and d["codigo"] == "VIZ" and d["descricao"] == "Ótima casa."
        assert d["endereco"] == "Granja Viana, Cotia" and d["preco"] == 950_000.0
        assert vista.post("detalhes_imovel", {"codigo": "HID"}).json()["data"] == {"codigo": "HID", "encontrado": False}
        assert vista.post("detalhes_imovel", {"codigo": "NADA"}).json()["data"]["encontrado"] is False
        c = vista.post("imovel_campanha", {"codigo": "CAMP"}).json()["data"]
        assert [x["codigo"] for x in c] == ["CAMP"]
        assert vista.post("imovel_campanha", {"codigo": "HID"}).json()["data"] == []

    def test_an_owner_confirmed_price_still_overrides_vista(self, vista, catalogo):
        catalogo.set_table_data("julia_proprietarios_contatos", [{
            "org_id": str(_ORG), "imovel_codigo": "VIZ", "confirmado_at": "2026-10-20T12:00:00+00:00",
            "preco_confirmado": 925_000, "preco_tipo_confirmado": "venda", "status_confirmado": None,
        }])
        d = vista.post("detalhes_imovel", {"codigo": "VIZ"}).json()["data"]
        assert d["preco"] == 925_000.0 and d["confirmacao_proprietario"]["preco"] == 925_000.0

    def test_no_owner_or_internal_field_ever_leaves(self, vista):
        bodies = [vista.post("buscar_imoveis", {"operacao": "compra", "limite": 5}).text,
                  vista.post("detalhes_imovel", {"codigo": "VIZ"}).text, vista.post("imovel_campanha", {"codigo": "CAMP"}).text]
        assert all(OWNER_SECRET not in b for b in bodies)
        assert set(cat.linha_de_imovel(_imovel("X"))) == {c.strip() for c in cat.COLUNAS.split(",")}

    def test_a_vista_failure_is_catalogo_indisponivel_never_the_mirror(self, vista):
        class _Caido(FakeVistaAdapter):
            async def search_imoveis(self, **k):
                raise VistaUpstreamError(500, "boom", "/imoveis/listar")

            async def get_imovel(self, code):
                raise VistaUpstreamError(500, "boom", "/imoveis/detalhes")

        cat.configure_vista_adapter(lambda: _Caido())
        for nome, corpo in [("buscar_imoveis", {"operacao": "compra"}), ("detalhes_imovel", {"codigo": "VIZ"}),
                            ("imovel_campanha", {"codigo": "VIZ"})]:
            r = vista.post(nome, corpo)
            assert r.status_code == 503 and r.json()["error"]["code"] == "catalogo_indisponivel", (nome, r.text)

    def test_vista_not_configured_is_catalogo_indisponivel(self, vista):
        from noctusai_lib.integrations.vista import VistaNotConfigured

        def _sem_chave():
            raise VistaNotConfigured("VISTA_API_KEY is empty")

        cat.configure_vista_adapter(_sem_chave)
        r = vista.post("buscar_imoveis", {"operacao": "compra"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "catalogo_indisponivel"

    def test_the_real_adapter_without_credentials_is_catalogo_indisponivel(self, vista):
        from app.config import settings

        assert not (settings.crm_base_url and settings.crm_api_key), "this test needs a credential-less environment"
        cat.configure_vista_adapter(None)
        r = vista.post("detalhes_imovel", {"codigo": "VIZ"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "catalogo_indisponivel"


class TestEspelhoContinuaIgual:
    def test_an_org_without_a_config_row_or_on_espelho_never_calls_vista(self, tools, catalogo):  # noqa: F811
        fake = _Espiao()
        cat.configure_vista_adapter(lambda: fake)
        try:
            tools.as_ctx(_product())
            assert tools.post("buscar_imoveis", {"operacao": "compra"}).status_code == 200
            catalogo.set_table_data("julia_catalogo_config", [{"org_id": str(_ORG), "fonte": "espelho"}])
            assert tools.post("detalhes_imovel", {"codigo": "CA1"}).json()["data"]["encontrado"] is True
            assert fake.chamadas == 0
        finally:
            cat.configure_vista_adapter(None)


class TestFiltrosVista:
    def test_one_sided_price_and_aluguel(self):
        f = cat.filtros_vista(busca.Consulta(operacao="aluguel", preco_max=5000))[0]
        assert f["Status"] == ["Aluguel", "Venda e Aluguel"] and f["ValorLocacao"] == ["<=", 5000 * 1.2] and "ValorVenda" not in f
        f = cat.filtros_vista(busca.Consulta(operacao="compra", preco_min=1000))[0]
        assert f["ValorVenda"] == [">=", 850.0]

    def test_regions_one_query_each_and_none_when_too_many(self):
        assert len(cat.filtros_vista(busca.Consulta(operacao="compra", regioes=("A", "B")))) == 2
        assert len(cat.filtros_vista(busca.Consulta(operacao="compra", regioes=("A", "B", "C", "D")))) == 1
        assert "Bairro" not in cat.filtros_vista(busca.Consulta(operacao="compra", regioes=("A", "B", "C", "D")))[0]

    def test_no_zero_bounds_are_sent(self):
        f = cat.filtros_vista(busca.Consulta(operacao="compra", quartos_min=1, vagas_min=0))[0]
        assert "Dormitorios" not in f and "Vagas" not in f  # quartos_min 1 widens to 0; vagas 0 is no filter


class TestCatalogoFonteApi:
    @pytest.mark.parametrize("method", ["get", "put"])
    def test_no_session_is_strictly_401(self, admin, method):  # noqa: F811
        r = getattr(admin.tc, method)(URL) if method == "get" else admin.tc.put(URL, json={"fonte": "vista"})
        assert r.status_code == 401

    @pytest.mark.parametrize("method", ["get", "put"])
    def test_a_member_is_403(self, member, method):  # noqa: F811
        assert member.req(method, URL, {"fonte": "vista"} if method == "put" else None).status_code == 403

    def test_default_is_espelho_then_the_admin_switches_and_it_persists(self, admin):  # noqa: F811
        admin.w.sw.set_table_data("julia_catalogo_config", [])
        d = admin.req("get", URL).json()["data"]
        assert d["fonte"] == "espelho" and d["fontes"] == ["vista", "espelho"] and d["padrao"] == "espelho"
        r = admin.req("put", URL, {"fonte": "vista"})
        assert r.status_code == 200 and r.json()["data"]["fonte"] == "vista" and r.json()["data"]["updated_by"]
        assert admin.req("get", URL).json()["data"]["fonte"] == "vista"
        assert admin.req("put", URL, {"fonte": "espelho"}).json()["data"]["fonte"] == "espelho"
        assert len(admin.w.rows("julia_catalogo_config")) == 1  # an upsert, not a second row

    def test_validation(self, admin):  # noqa: F811
        admin.w.sw.set_table_data("julia_catalogo_config", [])
        assert admin.req("put", URL, {"fonte": "outra"}).status_code == 422
        assert admin.req("put", URL, {"fonte": "vista", "org_id": "x"}).status_code == 422
        assert admin.req("put", URL, {}).status_code == 422
