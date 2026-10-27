"""vista.contratos.* tools — sale contracts (`/contratos/listar`).

Live 2026-10-27: a JSON **list** (2-3 rows on `oneconsu-rest`, all ANO 2024),
UPPERCASE keys (CODIGO, IMOVEL, VLR_VENDA, VLR_COMISSAO, PERC_*, …) plus
relation objects `Clientes`, `Proprietarios`, `Corretores`, `Agencias`,
`Anexos`. Vista ignores `pesquisa` entirely (no projection, no paging) and a
filter on ANO is a 500 — so minimisation is CLIENT-SIDE (`project_contrato`):
the default keeps the commercial scalars and drops OBS + every relation
object (buyer/owner identities). `/contratos/detalhes` is POST/PUT-only (a
write) and has no tool.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import project_contrato

from ..types import ListContratosInput, RawListOutput
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)


async def list_contratos(args: dict) -> dict:
    inp = ListContratosInput(**args)
    try:
        result = await _client().listar_contratos()
    except HANDLED_READ_ERRORS as e:
        return RawListOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    rows = result.data if isinstance(result.data, list) else []
    items = [project_contrato(r, inp.fields) for r in rows if isinstance(r, dict)]
    return RawListOutput(items=items).model_dump()


HANDLERS = {"vista.contratos.list": list_contratos}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.contratos.list",
            description=(
                "List Vista sale contracts (few rows on this tenant; Vista "
                "returns all of them at once — no paging, no server filter). "
                "Rows carry sale value, commission values/percentages, imóvel "
                "code, contract number and date (UPPERCASE keys). LGPD: the "
                "Clientes / Proprietarios / Corretores / Agencias / Anexos "
                "relation objects and OBS are dropped CLIENT-SIDE by default; "
                "name them in `fields` to include."
            ),
            inputSchema=ListContratosInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
