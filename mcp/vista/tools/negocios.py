"""vista.negocios.* tools — the deal pipeline (opened by the 2026-10-26 grant).

Wire contract, live-probed 2026-10-27 (`KB § INTEGRATIONS/vista.md`):

- `/negocios/listar` needs exactly ONE of the TOP-LEVEL params `codigo_pipe`
  / `codigo_cliente` (inside `pesquisa` → 400; neither → 400; both → an
  empty 200). Pipe 1 holds ~8.7k deals, pipe 2 ~2k.
- Paging is `pesquisa.paginacao` and works ONLY alongside `pesquisa.fields`
  — which is why these tools always send a projection. Top-level
  `page`/`pagina`/`limit`/`offset` are silently ignored by Vista.
- The envelope adds a `valorTotal` string (sum of ValorNegocio across the
  whole scoped result), surfaced here as `valor_total`.
- `/negocios/detalhes?codigo_negocio=` (top-level) → one deal.
- `/negocios/etapas` is PUT-only (moves a deal between stages — a WRITE) and
  has no tool.

LGPD: the default projection omits `NomeCliente` / `FotoCliente`;
`CodigoCliente` links to `vista.clientes.get` when the identity is needed.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    DEFAULT_NEGOCIO_FIELDS,
    extract_items,
    resolve_fields,
)

from ..types import GetNegocioInput, ListNegociosInput, ListNegociosOutput, RawGetOutput
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)


async def list_negocios(args: dict) -> dict:
    inp = ListNegociosInput(**args)
    try:
        result = await _client().listar_negocios(
            fields=resolve_fields(inp.fields, DEFAULT_NEGOCIO_FIELDS),
            codigo_pipe=inp.codigo_pipe,
            codigo_cliente=inp.codigo_cliente,
            order=inp.order,
            page=inp.page,
            page_size=inp.page_size,
        )
    except ValueError as e:
        return ListNegociosOutput(typed_error=_typed_error(e)).model_dump()
    except HANDLED_READ_ERRORS as e:
        return ListNegociosOutput(
            typed_error=_typed_error(e), probe_status=probe_status_for(e)
        ).model_dump()

    items, pagination = extract_items(result.data)
    valor_total = result.data.get("valorTotal") if isinstance(result.data, dict) else None
    return ListNegociosOutput(
        items=items,
        pagination=pagination,
        valor_total=str(valor_total) if valor_total is not None else None,
    ).model_dump()


async def get_negocio(args: dict) -> dict:
    inp = GetNegocioInput(**args)
    try:
        result = await _client().detalhes_negocio(
            inp.codigo, fields=resolve_fields(inp.fields, DEFAULT_NEGOCIO_FIELDS)
        )
    except HANDLED_READ_ERRORS as e:
        return RawGetOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    item = result.data if isinstance(result.data, dict) and result.data else None
    return RawGetOutput(item=item).model_dump()


HANDLERS = {
    "vista.negocios.list": list_negocios,
    "vista.negocios.get": get_negocio,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.negocios.list",
            description=(
                "List Vista deals (negócios) for ONE pipeline (`codigo_pipe`, "
                "e.g. '1' ~8.7k deals, '2' ~2k) XOR ONE client "
                "(`codigo_cliente`) — exactly one is required; sending both "
                "returns a ValueError before any call. Paginated (max "
                "page_size=50); `pagination` = {total, paginas, pagina, "
                "quantidade}; `valor_total` = sum of ValorNegocio over the whole "
                "scope. Default fields: deal code/name/status/stage/dates/value "
                "+ CodigoCliente/CodigoImovel — the client's NAME is opt-in via "
                "`fields` (personal data). No server-side filter is exposed "
                "(not proven on this tenant)."
            ),
            inputSchema=ListNegociosInput.model_json_schema(),
        ),
        Tool(
            name="vista.negocios.get",
            description=(
                "Fetch one Vista deal by code (`/negocios/detalhes?"
                "codigo_negocio=`). Returns CodigoPipe, EtapaAtual/NomeEtapa, "
                "value, dates and CorretoresNegocio (assigned brokers). "
                "Read-only: stage moves (`/negocios/etapas`, PUT) are not "
                "exposed."
            ),
            inputSchema=GetNegocioInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
