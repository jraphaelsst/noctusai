"""vista.agenda.* tools — activities / visits (opened by the 2026-10-26 grant).

`/agenda/listar` uses the classic dict-keyed envelope (~3.9k rows) with the
usual `pesquisa` filter/order/paginacao; field names come from
`/agenda/listarcampos` (29). `/agenda/detalhes?codigo=` needs `pesquisa.fields`
and keys its answer by the activity code (`{"<codigo>": {...}}`) —
`unwrap_keyed_record` flattens it. `TipoAtividade` is valid on listar but a
500 on detalhes (live 2026-10-27), so the shared default omits it.

LGPD: `NomeCliente`, `Texto` and `Local` are opt-in via `fields`.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    DEFAULT_AGENDA_FIELDS,
    extract_items,
    resolve_fields,
    unwrap_keyed_record,
)

from ..types import GetAgendaInput, ListAgendaInput, RawGetOutput, RawListOutput
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)


async def list_agenda(args: dict) -> dict:
    inp = ListAgendaInput(**args)
    try:
        result = await _client().listar_agenda(
            fields=resolve_fields(inp.fields, DEFAULT_AGENDA_FIELDS),
            filter_=inp.filter,
            order=inp.order,
            page=inp.page,
            page_size=inp.page_size,
        )
    except HANDLED_READ_ERRORS as e:
        return RawListOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    items, pagination = extract_items(result.data)
    return RawListOutput(items=items, pagination=pagination).model_dump()


async def get_agenda(args: dict) -> dict:
    inp = GetAgendaInput(**args)
    try:
        result = await _client().detalhes_agenda(
            inp.codigo, fields=resolve_fields(inp.fields, DEFAULT_AGENDA_FIELDS)
        )
    except HANDLED_READ_ERRORS as e:
        return RawGetOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    return RawGetOutput(item=unwrap_keyed_record(result.data, inp.codigo)).model_dump()


HANDLERS = {
    "vista.agenda.list": list_agenda,
    "vista.agenda.get": get_agenda,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.agenda.list",
            description=(
                "List Vista agenda activities (visits, tasks, calls; ~3.9k). "
                "Supports `filter` (e.g. {\"DataHora\": [\">=\", "
                "\"2026-10-01\"]}), `order` (e.g. {\"DataHora\": \"desc\"}) and "
                "paging (max page_size=50). Field names: "
                "vista.diagnostics.list_fields family='agenda'. Default fields "
                "omit NomeCliente / Texto / Local (personal data / free text) — "
                "name them in `fields` to include."
            ),
            inputSchema=ListAgendaInput.model_json_schema(),
        ),
        Tool(
            name="vista.agenda.get",
            description=(
                "Fetch one Vista agenda activity by code (`/agenda/detalhes?"
                "codigo=`). Same default projection as vista.agenda.list; "
                "`TipoAtividade` is NOT accepted on this route (Vista 500)."
            ),
            inputSchema=GetAgendaInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
