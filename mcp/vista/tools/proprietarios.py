"""vista.proprietarios.* tools — property OWNERS. 🔴 Identity-PII family.

Opened by the 2026-10-26 grant: `/proprietarios/listar` (classic envelope,
8,555 owners) and `/proprietarios/detalhes?codigo=` (the id param is `codigo`;
`pesquisa.fields` required). The field catalog is the `proprietarios`
relation of `/imoveis/listarcampos` — 149 fields including `CPFCNPJ`, `RG`,
`Banco`/`Agencia`/`Conta`, income, spouse identity.

**LGPD posture (by construction, not convention):** both tools default to
`DEFAULT_PROPRIETARIO_FIELDS` = Codigo + Nome. Any identity, contact, bank or
income field is returned ONLY when the caller names it in `fields`, so every
CPF read is a visible, deliberate choice at the call site. The MCP server
never persists responses. Recorded in `LGPD-WARNINGS.md` (2026-10-27).
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    DEFAULT_PROPRIETARIO_FIELDS,
    extract_items,
    resolve_fields,
)

from ..types import (
    GetProprietarioInput,
    ListProprietariosInput,
    RawGetOutput,
    RawListOutput,
)
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)


async def list_proprietarios(args: dict) -> dict:
    inp = ListProprietariosInput(**args)
    try:
        result = await _client().listar_proprietarios(
            fields=resolve_fields(inp.fields, DEFAULT_PROPRIETARIO_FIELDS),
            page=inp.page,
            page_size=inp.page_size,
        )
    except HANDLED_READ_ERRORS as e:
        return RawListOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    items, pagination = extract_items(result.data)
    return RawListOutput(items=items, pagination=pagination).model_dump()


async def get_proprietario(args: dict) -> dict:
    inp = GetProprietarioInput(**args)
    try:
        result = await _client().detalhes_proprietario(
            inp.codigo, fields=resolve_fields(inp.fields, DEFAULT_PROPRIETARIO_FIELDS)
        )
    except HANDLED_READ_ERRORS as e:
        return RawGetOutput(typed_error=_typed_error(e), probe_status=probe_status_for(e)).model_dump()
    item = result.data if isinstance(result.data, dict) and result.data else None
    return RawGetOutput(item=item).model_dump()


HANDLERS = {
    "vista.proprietarios.list": list_proprietarios,
    "vista.proprietarios.get": get_proprietario,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    _lgpd = (
        "🔴 LGPD: returns ONLY Codigo + Nome by default. Owner records hold "
        "CPFCNPJ, RG, bank account, income and spouse data — such fields are "
        "returned only when named explicitly in `fields`, and should be named "
        "only when the task truly needs them."
    )
    return [
        Tool(
            name="vista.proprietarios.list",
            description=(
                "List Vista property owners (~8.5k). Paginated (max "
                "page_size=50). Field catalog: vista.diagnostics.list_fields "
                "family='imoveis' → the `proprietarios` relation. " + _lgpd
            ),
            inputSchema=ListProprietariosInput.model_json_schema(),
        ),
        Tool(
            name="vista.proprietarios.get",
            description=(
                "Fetch one Vista property owner by code "
                "(`/proprietarios/detalhes?codigo=`). " + _lgpd
            ),
            inputSchema=GetProprietarioInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
