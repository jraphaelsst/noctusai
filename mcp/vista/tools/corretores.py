"""vista.corretores.* tools — ✅ GRANTED on this tenant since 2026-10-26.

`/corretores/listar` answered **401** until Vista's "full access" grant on key
`…644c` (live re-probe 2026-10-26/27, not the vendor's word). It now answers
200 — 24 brokers — with an envelope NO other family uses::

    {"items": [{"Codigo", "Nome"}], "meta": {currentPage, totalItems,
     itemCount, itemsPerPage, totalPages}}

paged by TOP-LEVEL `page` + `limit`; `pesquisa`/`fields` are ignored. The
tool used to feed this to `extract_items`, which read `meta` as a row and
dropped every broker — `extract_corretores_items` maps it onto the shared
`{total, paginas, pagina, quantidade}` vocabulary instead.

`/corretores/detalhes` and `/corretores/listarConteudo` stay **404**, so this
module still exposes exactly one tool. Richer broker data (e-mail, Setor,
photo) is `vista.usuarios.list`; the per-client broker record
(`CorretorCliente` relation on clientes) is identity PII (CPF, RG, CNH) and
is deliberately NOT surfaced by any default projection.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import extract_corretores_items

from ..types import ListCorretoresInput, ListCorretoresOutput
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)


async def list_corretores(args: dict) -> dict:
    inp = ListCorretoresInput(**args)
    try:
        result = await _client().listar_corretores(page=inp.page, page_size=inp.page_size)
    except HANDLED_READ_ERRORS as e:
        return ListCorretoresOutput(
            typed_error=_typed_error(e), probe_status=probe_status_for(e)
        ).model_dump()

    items, pagination = extract_corretores_items(result.data)
    return ListCorretoresOutput(items=items, pagination=pagination).model_dump()


HANDLERS = {"vista.corretores.list": list_corretores}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.corretores.list",
            description=(
                "List Vista brokers. ✅ GRANTED on this tenant 2026-10-26 (24 "
                "brokers). Rows carry ONLY {Codigo, Nome} — Vista ignores field "
                "selection on this route; for e-mail/Setor/photo use "
                "`vista.usuarios.list`. Paginated (max page_size=50); "
                "`pagination` uses the same {total, paginas, pagina, "
                "quantidade} keys as every other list tool. A typed_error with "
                "probe_status='permission_gated' means the grant was rolled "
                "back — ask Vista, do not retry."
            ),
            inputSchema=ListCorretoresInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
