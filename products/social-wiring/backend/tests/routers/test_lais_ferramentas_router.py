"""`POST /api/lais/ferramentas/{nome}` (lais-build-contract A3 / 2.2): the four read tools agents
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
URL = "/api/lais/ferramentas"
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
    from app.routers.lais_ferramentas_router import get_ferramentas_client

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
        assert r.status_code == 200 and set(r.json()) == {"data"}


class TestBuscarImoveis:
    def test_returns_the_contract_shape_for_the_callers_org_only(self, ok):
        data = ok.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]
        assert {d["codigo"] for d in data} == {"CA1", "CA2"}  # not OTH (other org), not HID (unpublished), not AP1 (rent)
        assert set(data[0]) == {"codigo", "titulo", "tipo", "bairro", "cidade", "preco", "quartos", "link"}
        ca1 = next(d for d in data if d["codigo"] == "CA1")
        assert (ca1["preco"], ca1["quartos"], ca1["bairro"], ca1["tipo"]) == (900000.0, 3, "Granja Viana", "Casa")

    def test_another_orgs_token_sees_another_catalogue(self, tools):
        tools.as_ctx(_product(org=_OTHER))
        assert [d["codigo"] for d in tools.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]] == ["OTH"]

    def test_filters(self, ok):
        def codes(**f):
            return {d["codigo"] for d in ok.post("buscar_imoveis", {"operacao": "compra", **f}).json()["data"]}

        assert codes(preco_max=1_000_000) == {"CA1"}
        assert codes(quartos_min=4) == {"CA2"}
        assert codes(bairro="alphaville") == {"CA2"}
        assert codes(cidade="cotia") == {"CA1", "CA2"}
        assert codes(tipo="apart") == set()
        r = ok.post("buscar_imoveis", {"operacao": "aluguel", "preco_max": 5000}).json()["data"]
        assert [(d["codigo"], d["preco"]) for d in r] == [("AP1", 4500.0)]

    def test_the_limit_is_honoured_and_capped_at_five(self, tools, catalogo):
        catalogo.set_table_data("imoveis", [_row(f"M{i}") for i in range(9)])
        tools.as_ctx(_product())
        assert len(tools.post("buscar_imoveis", {"operacao": "compra"}).json()["data"]) == 5
        assert len(tools.post("buscar_imoveis", {"operacao": "compra", "limite": 2}).json()["data"]) == 2

    def test_unpublished_listings_do_not_eat_the_limit(self, tools, catalogo):
        catalogo.set_table_data("imoveis", [_row(f"H{i}", exibir_no_site=False) for i in range(5)] + [_row("PUB")])
        tools.as_ctx(_product())
        assert [d["codigo"] for d in tools.post("buscar_imoveis", {"operacao": "compra", "limite": 1}).json()["data"]] == ["PUB"]


class TestDetalhesImovel:
    def test_returns_the_contract_shape_with_iptu_and_street_withheld_until_wave_1(self, ok):
        d = ok.post("detalhes_imovel", {"codigo": "ca1"}).json()["data"]  # case-insensitive code
        assert set(d) == {"codigo", "titulo", "descricao", "preco", "condominio", "iptu", "endereco", "caracteristicas", "encontrado"}
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
        from app.services.lais_ferramentas_service import COLUNAS

        cols = {c.strip() for c in COLUNAS.split(",")}
        assert not cols & {"corretores", "vista_raw", "observacoes", "chave", "matricula_vista", "inscricao_municipal",
                           "caracteristicas_raw", "referencia"}


class TestPendingWaves:
    def test_horarios_and_empreendimento_answer_an_empty_list_until_their_wave(self, ok):
        assert ok.post("horarios_visita", {"codigo": "CA1", "dias": 3}).json() == {"data": []}
        assert ok.post("consultar_empreendimento", {"nome": "Condomínio X"}).json() == {"data": []}
