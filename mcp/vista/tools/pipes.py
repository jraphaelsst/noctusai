"""vista.pipes.* tools — sales pipelines (`/pipes/listar`).

Live 2026-10-27: `Empresa` (agency code) is mandatory INSIDE
`pesquisa.filter`; an integer Empresa without `fields` is a 500, and
`showtotal=1` turns an empty answer into a 404 (the client avoids both).

⚠️ Unsettled contract: on `oneconsu-rest` the call returns 200 `[]` even
though `/negocios/listar?codigo_pipe=1|2` holds 10k+ deals — so the tool
says so instead of implying "no pipelines". Pipe codes are discoverable from
the deals' own `CodigoPipe` (`vista.negocios.list` / `.get`).
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import extract_items

from ..types import ListPipesInput, RawListOutput
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)


async def list_pipes(args: dict) -> dict:
    inp = ListPipesInput(**args)
    try:
        result = await _client().listar_pipes(empresa=inp.empresa)
    except HANDLED_READ_ERRORS as e:
        return RawListOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    data = result.data
    if isinstance(data, list):
        items = [r for r in data if isinstance(r, dict)]
        pagination: dict = {}
    else:
        items, pagination = extract_items(data)
    return RawListOutput(items=items, pagination=pagination).model_dump()


HANDLERS = {"vista.pipes.list": list_pipes}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.pipes.list",
            description=(
                "List Vista sales pipelines for an agency (`empresa`, default "
                "'1'). ⚠️ On this tenant Vista currently answers an EMPTY list "
                "even though pipelines 1 and 2 hold 10k+ deals — an empty "
                "result does NOT mean there are no pipelines. Discover pipe "
                "codes from `CodigoPipe` on vista.negocios.list / .get."
            ),
            inputSchema=ListPipesInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
