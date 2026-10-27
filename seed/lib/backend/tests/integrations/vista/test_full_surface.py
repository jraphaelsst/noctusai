"""Vista surface opened by the 2026-10-26 "full access" grant on key `…644c`.

Every wire shape asserted here was settled by a READ-ONLY live probe of
`oneconsu-rest` on 2026-10-26/27 (GETs + empty POSTs only; see the client
docstrings for the evidence per route). Network-free: httpx.MockTransport for
the Real client, `FakeVistaClient` for the Fake — and a parity test that the
Fake records the SAME request params the Real puts on the wire.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import httpx
import pytest

from noctusai_lib.integrations.vista import (
    CLIENTE_IDENTITY_PII_FIELDS,
    DEFAULT_AGENDA_FIELDS,
    DEFAULT_CONTRATO_FIELDS,
    DEFAULT_HISTORICO_CLIENTE_FIELDS,
    DEFAULT_NEGOCIO_FIELDS,
    DEFAULT_PRONTUARIO_FIELDS,
    DEFAULT_PROPRIETARIO_FIELDS,
    VISTA_LISTARCAMPOS_FAMILIES,
    FakeVistaClient,
    VistaRecordUnpublished,
    extract_corretores_items,
    extract_items,
    extract_relation,
    project_contrato,
    unwrap_keyed_record,
)
from noctusai_lib.integrations.vista.calibration import (
    CANDIDATE_CLIENTE_FIELDS,
    CORRETOR_RETURNED_FIELDS,
    Calibrator,
)
from noctusai_lib.integrations.vista.client import VistaClient

KEY = "00000000feedface0000000000000000"

# Live shape, values replaced (2026-10-27).
CORRETORES_ENVELOPE = {
    "items": [{"Codigo": "11", "Nome": "Broker A"}, {"Codigo": "12", "Nome": "Broker B"}],
    "meta": {"currentPage": 2, "totalItems": 24, "itemCount": 2, "itemsPerPage": 10, "totalPages": 3},
}


def _real(
    seen: list[httpx.Request], body: Any = None, status: int = 200
) -> VistaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={} if body is None else body)

    return VistaClient(
        "https://t-rest.vistahost.com.br",
        KEY,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _pesquisa(req: httpx.Request) -> dict:
    return json.loads(req.url.params["pesquisa"])


# ─── /corretores/listar — the {items, meta} envelope ─────────────────────


def test_corretores_envelope_maps_meta_onto_the_shared_pagination_vocabulary() -> None:
    items, pagination = extract_corretores_items(CORRETORES_ENVELOPE)
    assert [i["Codigo"] for i in items] == ["11", "12"]
    assert pagination == {"total": 24, "paginas": 3, "pagina": 2, "quantidade": 10}


def test_corretores_envelope_never_yields_meta_as_a_row() -> None:
    """The 2026-10-26 bug: `extract_items` read `meta` (a dict) as a broker
    and dropped `items` (a list). This pins the regression on both helpers."""
    wrong_items, _ = extract_items(CORRETORES_ENVELOPE)
    assert wrong_items == [CORRETORES_ENVELOPE["meta"]], "documents why extract_items is wrong here"
    items, _ = extract_corretores_items(CORRETORES_ENVELOPE)
    assert all("Nome" in i for i in items)


def test_corretores_extractor_falls_back_to_the_classic_envelope() -> None:
    classic = {"11": {"Codigo": "11", "Nome": "A"}, "total": 1, "pagina": 1}
    items, pagination = extract_corretores_items(classic)
    assert items == [{"Codigo": "11", "Nome": "A"}]
    assert pagination == {"total": 1, "pagina": 1}


def test_corretores_is_no_longer_calibrated() -> None:
    """Vista ignores `fields` on this route — a calibration would always
    'succeed' and report fields the response never carries."""
    assert CORRETOR_RETURNED_FIELDS == ("Codigo", "Nome")
    assert not hasattr(Calibrator, "get_corretor_fields")


# ─── /negocios ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("pipe,cliente", [(None, None), ("1", "7")])
async def test_negocios_requires_exactly_one_scope_before_any_request(pipe, cliente) -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(ValueError):
        await _real(seen).listar_negocios(
            fields=["Codigo"], codigo_pipe=pipe, codigo_cliente=cliente
        )
    assert seen == [], "the XOR guard must refuse before Vista sees the call"
    with pytest.raises(ValueError):
        await FakeVistaClient().listar_negocios(
            fields=["Codigo"], codigo_pipe=pipe, codigo_cliente=cliente
        )


@pytest.mark.asyncio
async def test_negocios_scope_is_top_level_and_paging_rides_with_fields() -> None:
    seen: list[httpx.Request] = []
    await _real(seen).listar_negocios(
        fields=list(DEFAULT_NEGOCIO_FIELDS), codigo_pipe="2", page=3, page_size=500,
        order={"Codigo": "desc"},
    )
    params = seen[0].url.params
    assert params["codigo_pipe"] == "2"
    assert "codigo_pipe" not in _pesquisa(seen[0])
    pesquisa = _pesquisa(seen[0])
    # paginacao alone is a 500 — it only works alongside fields.
    assert pesquisa["fields"] and pesquisa["paginacao"] == {"pagina": 3, "quantidade": 50}
    assert pesquisa["order"] == {"Codigo": "desc"}
    assert params["showtotal"] == "1"


@pytest.mark.asyncio
async def test_negocio_detail_uses_top_level_codigo_negocio() -> None:
    seen: list[httpx.Request] = []
    client = _real(seen)
    await client.detalhes_negocio("42")
    await client.detalhes_negocio("42", fields=["Codigo"])
    assert seen[0].url.params["codigo_negocio"] == "42"
    assert "pesquisa" not in seen[0].url.params
    assert _pesquisa(seen[1]) == {"fields": ["Codigo"]}


@pytest.mark.asyncio
async def test_pipes_sends_empresa_as_string_inside_filter_and_never_showtotal() -> None:
    seen: list[httpx.Request] = []
    await _real(seen, body=[]).listar_pipes(empresa="1")
    pesquisa = _pesquisa(seen[0])
    assert pesquisa["filter"] == {"Empresa": "1"}
    assert pesquisa["fields"]  # int Empresa without fields was a 500
    # showtotal turns an empty answer into a 404 indistinguishable from "no route".
    assert "showtotal" not in seen[0].url.params


# ─── /agenda, /proprietarios, /contratos, /imoveis/* ─────────────────────


@pytest.mark.asyncio
async def test_agenda_forwards_filter_order_and_paging() -> None:
    seen: list[httpx.Request] = []
    flt = {"DataHora": [">=", "2026-10-01"]}
    await _real(seen).listar_agenda(
        fields=list(DEFAULT_AGENDA_FIELDS), filter_=flt, order={"DataHora": "desc"}, page=2, page_size=5
    )
    pesquisa = _pesquisa(seen[0])
    assert pesquisa["filter"] == flt
    assert pesquisa["order"] == {"DataHora": "desc"}
    assert pesquisa["paginacao"] == {"pagina": 2, "quantidade": 5}


@pytest.mark.asyncio
async def test_agenda_and_owner_details_use_the_top_level_codigo_param() -> None:
    seen: list[httpx.Request] = []
    client = _real(seen)
    await client.detalhes_agenda("9", fields=["Codigo"])
    await client.detalhes_proprietario("8", fields=list(DEFAULT_PROPRIETARIO_FIELDS))
    assert seen[0].url.params["codigo"] == "9" and seen[0].url.path == "/agenda/detalhes"
    assert seen[1].url.params["codigo"] == "8" and seen[1].url.path == "/proprietarios/detalhes"
    # pesquisa.fields is REQUIRED on both (else 400 "formato dos dados").
    assert _pesquisa(seen[0])["fields"] and _pesquisa(seen[1])["fields"]


def test_agenda_default_omits_the_field_detalhes_500s_on() -> None:
    assert "TipoAtividade" not in DEFAULT_AGENDA_FIELDS


def test_unwrap_keyed_record_flattens_the_agenda_detail_body() -> None:
    assert unwrap_keyed_record({"9": {"Codigo": "9"}}, "9") == {"Codigo": "9"}
    assert unwrap_keyed_record({"Codigo": "9", "Assunto": "x"}, "9") == {"Codigo": "9", "Assunto": "x"}
    assert unwrap_keyed_record([], "9") is None


@pytest.mark.asyncio
async def test_contratos_sends_no_projection_because_vista_ignores_it() -> None:
    seen: list[httpx.Request] = []
    await _real(seen, body=[]).listar_contratos()
    assert set(seen[0].url.params.keys()) == {"key"}


def test_contrato_projection_drops_identity_relations_by_default() -> None:
    row = {
        "CODIGO": "1", "IMOVEL": "CA1", "VLR_VENDA": "100", "OBS": "free text",
        "Clientes": {"1": {"Nome": "x"}}, "Proprietarios": {"2": {}}, "Corretores": {},
        "Agencias": {}, "Anexos": {},
    }
    projected = project_contrato(row)
    assert projected == {"CODIGO": "1", "IMOVEL": "CA1", "VLR_VENDA": "100"}
    assert project_contrato(row, ["CODIGO", "Clientes"]) == {"CODIGO": "1", "Clientes": {"1": {"Nome": "x"}}}


@pytest.mark.asyncio
async def test_destaques_default_does_not_request_the_field_vista_rejects() -> None:
    seen: list[httpx.Request] = []
    await _real(seen).listar_destaques_imoveis(page=1, page_size=3)
    pesquisa = _pesquisa(seen[0])
    assert pesquisa["fields"] == ["Codigo"]  # CodigoImovel comes back, but is a 400 if asked
    assert pesquisa["paginacao"] == {"pagina": 1, "quantidade": 3}


# ─── History = a field relation, not a route ─────────────────────────────


@pytest.mark.asyncio
async def test_imovel_history_rides_detalhes_with_the_prontuarios_relation() -> None:
    seen: list[httpx.Request] = []
    body = {"Codigo": "CA1", "prontuarios": {"1": {"Assunto": "a"}, "2": {"Assunto": "b"}}}
    result = await _real(seen, body=body).historico_imovel("CA1", fields=list(DEFAULT_PRONTUARIO_FIELDS))
    assert seen[0].url.path == "/imoveis/detalhes"
    assert seen[0].url.params["imovel"] == "CA1"
    assert _pesquisa(seen[0])["fields"] == ["Codigo", {"prontuarios": list(DEFAULT_PRONTUARIO_FIELDS)}]
    assert [e["Assunto"] for e in extract_relation(result.data, "prontuarios")] == ["a", "b"]


@pytest.mark.asyncio
async def test_imovel_history_keeps_the_unpublished_guard_on_real_and_fake() -> None:
    with pytest.raises(VistaRecordUnpublished):
        await _real([], body=[]).historico_imovel("ONE8065", fields=["Data"])
    with pytest.raises(VistaRecordUnpublished):
        await FakeVistaClient(responses={"/imoveis/detalhes": []}).historico_imovel("ONE8065", fields=["Data"])


@pytest.mark.asyncio
async def test_cliente_history_rides_detalhes_with_the_historicos_relation() -> None:
    seen: list[httpx.Request] = []
    await _real(seen).historico_cliente("C1", fields=list(DEFAULT_HISTORICO_CLIENTE_FIELDS))
    assert seen[0].url.path == "/clientes/detalhes"
    assert seen[0].url.params["cliente"] == "C1"
    assert _pesquisa(seen[0])["fields"][1] == {"historicos": list(DEFAULT_HISTORICO_CLIENTE_FIELDS)}


def test_extract_relation_handles_dict_list_and_absent() -> None:
    assert extract_relation({"r": {"1": {"a": 1}}}, "r") == [{"a": 1}]
    assert extract_relation({"r": [{"a": 1}, "junk"]}, "r") == [{"a": 1}]
    assert extract_relation({}, "r") == []
    assert extract_relation(None, "r") == []


# ─── Catalogs ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_listar_campos_refuses_a_family_without_the_route() -> None:
    seen: list[httpx.Request] = []
    for family in ("negocios", "proprietarios", "contratos", "corretores", "../x"):
        with pytest.raises(ValueError):
            await _real(seen).listar_campos(family)
        with pytest.raises(ValueError):
            await FakeVistaClient().listar_campos(family)
    assert seen == []
    await _real(seen).listar_campos("agenda")
    assert seen[0].url.path == "/agenda/listarcampos"
    assert set(VISTA_LISTARCAMPOS_FAMILIES) == {"imoveis", "clientes", "usuarios", "agencias", "agenda"}


# ─── Fake ↔ Real: the Fake records what the Real sends ───────────────────

_Call = Callable[[Any], Awaitable[Any]]

_PARITY_CALLS: list[tuple[str, _Call]] = [
    ("listar_corretores", lambda c: c.listar_corretores(page=1, page_size=5)),
    ("listar_negocios pipe", lambda c: c.listar_negocios(fields=["Codigo"], codigo_pipe="1")),
    ("listar_negocios cliente", lambda c: c.listar_negocios(fields=["Codigo"], codigo_cliente="7")),
    ("detalhes_negocio", lambda c: c.detalhes_negocio("1")),
    ("detalhes_negocio fields", lambda c: c.detalhes_negocio("1", fields=["Codigo"])),
    ("listar_pipes", lambda c: c.listar_pipes()),
    ("listar_agenda", lambda c: c.listar_agenda(fields=["Codigo"])),
    ("detalhes_agenda", lambda c: c.detalhes_agenda("1", fields=["Codigo"])),
    ("listar_proprietarios", lambda c: c.listar_proprietarios(fields=["Codigo"])),
    ("detalhes_proprietario", lambda c: c.detalhes_proprietario("1", fields=["Codigo"])),
    ("listar_contratos", lambda c: c.listar_contratos()),
    ("listar_destaques_imoveis", lambda c: c.listar_destaques_imoveis()),
    ("listar_finalidades_imoveis", lambda c: c.listar_finalidades_imoveis()),
    ("listar_conteudo_clientes", lambda c: c.listar_conteudo_clientes(fields=["Status"])),
    ("historico_cliente", lambda c: c.historico_cliente("1", fields=["Hora"])),
    ("listar_campos", lambda c: c.listar_campos("imoveis")),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("label,call", _PARITY_CALLS, ids=[p[0] for p in _PARITY_CALLS])
async def test_fake_records_the_same_endpoint_and_params_the_real_sends(label, call) -> None:
    seen: list[httpx.Request] = []
    await call(_real(seen))
    fake = FakeVistaClient()
    await call(fake)
    real_endpoint = seen[0].url.path
    real_keys = sorted(seen[0].url.params.keys())
    assert fake.calls[-1] == (real_endpoint, real_keys), label


# ─── LGPD — minimal-by-default, pinned ───────────────────────────────────


def test_owner_default_projection_is_codigo_and_nome_only() -> None:
    assert DEFAULT_PROPRIETARIO_FIELDS == ("Codigo", "Nome")


@pytest.mark.parametrize(
    "default",
    [
        DEFAULT_PROPRIETARIO_FIELDS,
        DEFAULT_NEGOCIO_FIELDS,
        DEFAULT_AGENDA_FIELDS,
        DEFAULT_PRONTUARIO_FIELDS,
        DEFAULT_HISTORICO_CLIENTE_FIELDS,
        DEFAULT_CONTRATO_FIELDS,
    ],
)
def test_no_default_projection_carries_identity_pii_or_free_text(default) -> None:
    forbidden = set(CLIENTE_IDENTITY_PII_FIELDS) | {
        "CPF", "CPF_CGC", "CPFCNPJ", "RG_Inscricao", "Email", "NomeCliente", "FotoCliente",
        "Texto", "OBS", "Clientes", "Proprietarios", "Corretores", "Anexos",
    }
    assert not (set(default) & forbidden)


def test_candidate_cliente_fields_never_carry_identity_pii() -> None:
    """`CANDIDATE_CLIENTE_FIELDS` is the calibration superset AND the default
    projection of `vista.clientes.*`. The catalog (`/clientes/listarcampos`,
    2026-10-26) proves the tenant exposes CPFCNPJ / RG / bank / addresses
    under its own names — none may enter the default, and neither may the
    public-doc identity names another tenant might accept."""
    leaked = set(CANDIDATE_CLIENTE_FIELDS) & (
        set(CLIENTE_IDENTITY_PII_FIELDS) | {"CPF", "Email", "Endereco", "Numero", "Complemento", "CEP"}
    )
    assert not leaked, f"identity PII in the clientes default projection: {leaked}"
