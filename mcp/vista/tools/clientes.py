"""vista.clientes.* tools — 🔒 permission-gated on this tenant.

Per `KB § INTEGRATIONS/vista.md § 4.2`, `/clientes/listar` and
`/clientes/detalhes` both answer **401** on `oneconsu-rest` — the routes
exist, our key lacks the per-method grant. Every other `/clientes/*`
sub-route answers 404 and is genuinely absent, so it gets no tool here: a
tool that can only ever return "no route" is a lie about the surface.

The tools are registered anyway, for two reasons: a different tenant key
may carry the grant, and the typed 401 is itself the answer a host LLM
needs ("ask Vista", not "retry"). `probe_status` carries that distinction
to the caller.

**Parity with the ungated families is deliberate** (imoveis/usuarios/
agencias). Until 2026-08-19 this module was a stub that diverged in four
ways, each a small lie to the caller:
  * `ListClientesInput` declared `page`/`page_size` and the handler passed
    neither to the wire — a host asking for page 2 silently got page 1;
  * `CLIENTE_CANDIDATE_FIELDS` was declared and never referenced, while the
    call hardcoded `["Codigo", "Nome"]`;
  * no calibration, so a grant would land on an uncalibrated field set;
  * `/clientes/detalhes` had no tool at all despite being 401 (unlockable),
    not 404 (absent).

⚠️ **LGPD.** `clientes` carries CPF, addresses and phones. A grant is not
authorization to ingest: the data-category intake
(`KB § PATTERNS/security/lgpd.md`) gates the first successful call. The MCP
server itself does not persist responses.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
    calibrator,
    extract_items,
)

from ..settings import get_settings
from ..types import (
    GetClienteInput,
    GetClienteOutput,
    ListClientesInput,
    ListClientesOutput,
)

#: Errors that mean "we could not read this", all surfaced as a typed_error
#: rather than raised — an MCP tool that throws gives the host LLM nothing
#: actionable, while a typed 401 tells it exactly who to ask.
_HANDLED = (
    VistaConfigError,
    VistaPermissionDenied,
    VistaNotFound,
    VistaFieldNotAvailable,
    VistaTimeout,
    VistaUpstreamError,
)


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


def _typed_error(e: Exception) -> dict:
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


def _probe_status(e: Exception) -> str:
    """Map the typed error back to the endpoint vocabulary the catalog uses."""
    if isinstance(e, VistaPermissionDenied):
        return "permission_gated"
    if isinstance(e, VistaNotFound):
        return "absent"
    return "live_probed"


async def list_clientes(args: dict) -> dict:
    """Returns typed_error when the tenant key lacks permission."""
    inp = ListClientesInput(**args)
    client = _client()
    try:
        fields = await calibrator.get_cliente_fields(client)
        result = await client.listar_clientes(
            fields=fields, page=inp.page, page_size=inp.page_size
        )
    except _HANDLED as e:
        return ListClientesOutput(
            items=[],
            pagination={},
            typed_error=_typed_error(e),
            probe_status=_probe_status(e),
        ).model_dump()

    raw_items, pagination = extract_items(result.data)
    return ListClientesOutput(
        items=raw_items,
        pagination=pagination,
        typed_error=None,
        probe_status="live_probed",
    ).model_dump()


async def get_cliente(args: dict) -> dict:
    """Per-client detail. Gated identically to list_clientes."""
    inp = GetClienteInput(**args)
    client = _client()
    try:
        fields = await calibrator.get_cliente_fields(client)
        result = await client.detalhes_cliente(inp.codigo, fields=fields)
    except _HANDLED as e:
        return GetClienteOutput(
            item=None,
            typed_error=_typed_error(e),
            probe_status=_probe_status(e),
        ).model_dump()

    item = result.data if isinstance(result.data, dict) else None
    return GetClienteOutput(
        item=item,
        typed_error=None,
        probe_status="live_probed",
    ).model_dump()


HANDLERS = {
    "vista.clientes.list": list_clientes,
    "vista.clientes.get": get_cliente,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.clientes.list",
            description=(
                "List Vista clients (customers/leads). 🔒 PERMISSION-GATED: this "
                "tenant returns 401, in which case the response carries a "
                "typed_error, an empty items list and probe_status="
                "'permission_gated' — that means ask Vista for the grant, NOT "
                "retry. Paginated (max page_size=50). LGPD: clientes carry CPF / "
                "addresses / phones — handle as personal data."
            ),
            inputSchema=ListClientesInput.model_json_schema(),
        ),
        Tool(
            name="vista.clientes.get",
            description=(
                "Fetch one Vista client by code (`/clientes/detalhes`). 🔒 "
                "PERMISSION-GATED exactly like vista.clientes.list — and gated "
                "before parameter validation, so a bad code still reads as 401 "
                "while the grant is missing. LGPD: returns CPF / address / "
                "phones on success."
            ),
            inputSchema=GetClienteInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
