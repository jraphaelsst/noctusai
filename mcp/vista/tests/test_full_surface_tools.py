"""Tool-level tests for the surface opened by the 2026-10-26 Vista grant.

Clients are injected through the DI seam `_common.configure_client_factory`
— a `FakeVistaClient` for payload shapes, or a Real `VistaClient` on an
`httpx.MockTransport` where the assertion is about what reaches the WIRE
(the LGPD projections). Nothing here patches our own code or touches Vista.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import pytest

from noctusai_lib.integrations.vista import (
    DEFAULT_PROPRIETARIO_FIELDS,
    FakeVistaClient,
    VistaClient,
    VistaPermissionDenied,
)

NEW_TOOLS = {
    "vista.negocios.list",
    "vista.negocios.get",
    "vista.pipes.list",
    "vista.agenda.list",
    "vista.agenda.get",
    "vista.proprietarios.list",
    "vista.proprietarios.get",
    "vista.contratos.list",
    "vista.imoveis.list_destaques",
    "vista.imoveis.list_finalidades",
    "vista.imoveis.history",
    "vista.clientes.history",
    "vista.clientes.list_filters",
    "vista.diagnostics.list_fields",
}


@pytest.fixture
def use_client():
    from vista.tools import _common

    def _install(client):
        _common.configure_client_factory(lambda: client)
        return client

    yield _install
    _common.configure_client_factory(None)


def _wire_client(seen: list[httpx.Request], body=None) -> VistaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={} if body is None else body)

    return VistaClient(
        "https://t-rest.vistahost.com.br",
        "k" * 32,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _handlers():
    from vista.tools import all_handlers

    return all_handlers()


def test_every_new_tool_is_registered_with_a_descriptor():
    from vista.tools import all_descriptors

    names = {d.name for d in all_descriptors()}
    assert NEW_TOOLS <= names
    assert NEW_TOOLS <= set(_handlers())


@pytest.mark.asyncio
async def test_known_endpoint_catalog_only_names_tools_that_exist():
    out = await _handlers()["vista.diagnostics.list_known_endpoints"]({})
    named = {r["tool"] for r in out["endpoints"] if r.get("tool")}
    assert named <= set(_handlers()), f"catalog names unregistered tools: {named - set(_handlers())}"
    by_path = {r["path"]: r for r in out["endpoints"]}
    assert by_path["/corretores/listar"]["probe_status"] == "live_probed"
    assert by_path["/negocios/etapas"]["probe_status"] == "write_only"
    assert by_path["/contratos/detalhes"]["probe_status"] == "write_only"
    assert by_path["/imoveis/historico"]["probe_status"] == "absent"


# ─── corretores — the envelope bug ───────────────────────────────────────


@pytest.mark.asyncio
async def test_corretores_list_returns_brokers_not_the_meta_object(use_client):
    use_client(FakeVistaClient(responses={"/corretores/listar": {
        "items": [{"Codigo": "1", "Nome": "A"}, {"Codigo": "2", "Nome": "B"}],
        "meta": {"currentPage": 1, "totalItems": 2, "itemCount": 2, "itemsPerPage": 50, "totalPages": 1},
    }}))
    out = await _handlers()["vista.corretores.list"]({})
    assert [i["Codigo"] for i in out["items"]] == ["1", "2"]
    assert out["pagination"] == {"total": 2, "paginas": 1, "pagina": 1, "quantidade": 50}
    assert out["typed_error"] is None and out["probe_status"] == "live_probed"


@pytest.mark.asyncio
async def test_corretores_rollback_reads_as_permission_gated(use_client):
    use_client(FakeVistaClient(errors={"/corretores/listar": VistaPermissionDenied(401, "{}", "/corretores/listar")}))
    out = await _handlers()["vista.corretores.list"]({})
    assert out["items"] == [] and out["probe_status"] == "permission_gated"


# ─── negocios / pipes ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [{}, {"codigo_pipe": "1", "codigo_cliente": "2"}])
async def test_negocios_list_refuses_without_exactly_one_scope(use_client, args):
    fake = use_client(FakeVistaClient())
    out = await _handlers()["vista.negocios.list"](args)
    assert out["typed_error"]["error_class"] == "ValueError"
    assert fake.calls == []


@pytest.mark.asyncio
async def test_negocios_list_surfaces_rows_pagination_and_valor_total(use_client):
    use_client(FakeVistaClient(responses={"/negocios/listar": {
        "7": {"Codigo": "7", "NomeNegocio": "n"},
        "total": 8712, "paginas": 175, "pagina": 1, "quantidade": 50, "valorTotal": "123.45",
    }}))
    out = await _handlers()["vista.negocios.list"]({"codigo_pipe": "1"})
    assert out["items"] == [{"Codigo": "7", "NomeNegocio": "n"}]
    assert out["pagination"]["total"] == 8712
    assert out["valor_total"] == "123.45"


@pytest.mark.asyncio
async def test_negocios_default_projection_omits_the_client_name_on_the_wire(use_client):
    seen: list[httpx.Request] = []
    use_client(_wire_client(seen))
    await _handlers()["vista.negocios.list"]({"codigo_cliente": "5"})
    fields = json.loads(seen[0].url.params["pesquisa"])["fields"]
    assert "NomeCliente" not in fields and "CodigoCliente" in fields


@pytest.mark.asyncio
async def test_pipes_list_accepts_vistas_list_body(use_client):
    use_client(FakeVistaClient(responses={"/pipes/listar": []}))
    out = await _handlers()["vista.pipes.list"]({})
    assert out["items"] == [] and out["typed_error"] is None


# ─── proprietarios — LGPD on the wire ────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_tools_send_only_codigo_and_nome_by_default(use_client):
    seen: list[httpx.Request] = []
    use_client(_wire_client(seen))
    await _handlers()["vista.proprietarios.list"]({})
    await _handlers()["vista.proprietarios.get"]({"codigo": "8"})
    for req in seen:
        assert json.loads(req.url.params["pesquisa"])["fields"] == list(DEFAULT_PROPRIETARIO_FIELDS)
    assert seen[1].url.params["codigo"] == "8"


@pytest.mark.asyncio
async def test_owner_pii_reaches_the_wire_only_when_named(use_client):
    seen: list[httpx.Request] = []
    use_client(_wire_client(seen))
    await _handlers()["vista.proprietarios.list"]({"fields": ["Codigo", "Nome", "CPFCNPJ"]})
    assert "CPFCNPJ" in json.loads(seen[0].url.params["pesquisa"])["fields"]


def test_owner_tool_descriptions_state_the_lgpd_default():
    from vista.tools.proprietarios import tool_descriptors

    for d in tool_descriptors():
        assert "Codigo + Nome" in d.description and "LGPD" in d.description


# ─── agenda / contratos ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agenda_get_unwraps_the_code_keyed_body(use_client):
    use_client(FakeVistaClient(responses={"/agenda/detalhes": {"9": {"Codigo": "9", "Assunto": "Visita"}}}))
    out = await _handlers()["vista.agenda.get"]({"codigo": "9"})
    assert out["item"] == {"Codigo": "9", "Assunto": "Visita"}


@pytest.mark.asyncio
async def test_agenda_list_forwards_filter_and_order(use_client):
    seen: list[httpx.Request] = []
    use_client(_wire_client(seen))
    flt = {"DataHora": [">=", "2026-10-01"]}
    await _handlers()["vista.agenda.list"]({"filter": flt, "order": {"DataHora": "desc"}, "page": 2})
    pesquisa = json.loads(seen[0].url.params["pesquisa"])
    assert pesquisa["filter"] == flt and pesquisa["order"] == {"DataHora": "desc"}
    assert pesquisa["paginacao"]["pagina"] == 2


@pytest.mark.asyncio
async def test_contratos_list_projects_away_identity_relations(use_client):
    use_client(FakeVistaClient(responses={"/contratos/listar": [
        {"CODIGO": "1", "VLR_VENDA": "10", "Clientes": {"1": {"Nome": "x"}}, "OBS": "t"},
    ]}))
    out = await _handlers()["vista.contratos.list"]({})
    assert out["items"] == [{"CODIGO": "1", "VLR_VENDA": "10"}]


# ─── imoveis / clientes extras ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_imovel_history_windows_the_whole_relation(use_client):
    entries = {str(i): {"Assunto": f"a{i}"} for i in range(1, 8)}
    use_client(FakeVistaClient(responses={"/imoveis/detalhes": {"Codigo": "CA1", "prontuarios": entries}}))
    out = await _handlers()["vista.imoveis.history"]({"codigo": "CA1", "offset": 2, "limit": 3})
    assert out["total"] == 7
    assert [e["Assunto"] for e in out["items"]] == ["a3", "a4", "a5"]


@pytest.mark.asyncio
async def test_imovel_history_of_an_unpublished_code_is_a_typed_error(use_client):
    use_client(FakeVistaClient(responses={"/imoveis/detalhes": []}))
    out = await _handlers()["vista.imoveis.history"]({"codigo": "ONE8065"})
    assert out["items"] == [] and out["typed_error"]["error_class"] == "VistaRecordUnpublished"


@pytest.mark.asyncio
async def test_cliente_history_reads_the_historicos_relation(use_client):
    use_client(FakeVistaClient(responses={"/clientes/detalhes": {
        "Codigo": "C1", "Numero_Historico": "2", "historicos": {"1": {"Hora": "10:00"}, "2": {"Hora": "11:00"}},
    }}))
    out = await _handlers()["vista.clientes.history"]({"codigo": "C1"})
    assert out["total"] == 2 and out["items"][1] == {"Hora": "11:00"}


@pytest.mark.asyncio
async def test_finalidades_destaques_and_client_filters(use_client):
    use_client(FakeVistaClient(responses={
        "/imoveis/finalidades": ["Venda", "Aluguel"],
        "/imoveis/destaques": {"ONE1": {"Codigo": "ONE1", "CodigoImovel": "CA1"}},
        "/clientes/listarConteudo": {"Status": ["Ativo"], "Interesse": ["Compra"]},
    }))
    h = _handlers()
    assert (await h["vista.imoveis.list_finalidades"]({}))["finalidades"] == ["Venda", "Aluguel"]
    assert (await h["vista.imoveis.list_destaques"]({}))["items"] == [{"Codigo": "ONE1", "CodigoImovel": "CA1"}]
    assert (await h["vista.clientes.list_filters"]({}))["filters"] == {"Status": ["Ativo"], "Interesse": ["Compra"]}


@pytest.mark.asyncio
async def test_list_fields_returns_the_catalog(use_client):
    use_client(FakeVistaClient(responses={"/clientes/listarcampos": {
        "clientes": ["Codigo", "Nome"], "historicos": ["Data", "Hora"],
    }}))
    out = await _handlers()["vista.diagnostics.list_fields"]({"family": "clientes"})
    assert out["fields"] == {"clientes": ["Codigo", "Nome"], "historicos": ["Data", "Hora"]}


def test_list_fields_refuses_a_family_without_a_catalog_route():
    from pydantic import ValidationError
    from vista.types import ListFieldsInput

    with pytest.raises(ValidationError):
        ListFieldsInput(family="proprietarios")
