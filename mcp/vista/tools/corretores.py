"""vista.corretores.* tools — 🔒 permission-gated on this tenant.

Same gating story as clientes (`KB § INTEGRATIONS/vista.md § 4.5`):
`/corretores/listar` answers **401** — the route exists, our key lacks the
per-method grant. `/corretores/detalhes` and `/corretores/listarConteudo`
answer **404** (re-probed 2026-08-19) and are genuinely absent, so this
module exposes exactly one tool.

**Worth knowing before you reach for this family:** `/usuarios/listar`
(§ 4.3, ungated ✅) already returns the broker roster with
`Setor: "Corretores"`, and `/imoveis/listar` embeds the listing broker's
name + email per property. So the practical gap this 401 leaves is small —
`vista.usuarios.list` is the working substitute, and the tool description
says so, because a host LLM that hits the 401 should be routed to the
substitute rather than left blocked.
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
from ..types import ListCorretoresInput, ListCorretoresOutput

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
    if isinstance(e, VistaPermissionDenied):
        return "permission_gated"
    if isinstance(e, VistaNotFound):
        return "absent"
    return "live_probed"


async def list_corretores(args: dict) -> dict:
    inp = ListCorretoresInput(**args)
    client = _client()
    try:
        fields = await calibrator.get_corretor_fields(client)
        result = await client.listar_corretores(
            fields=fields, page=inp.page, page_size=inp.page_size
        )
    except _HANDLED as e:
        return ListCorretoresOutput(
            items=[],
            pagination={},
            typed_error=_typed_error(e),
            probe_status=_probe_status(e),
        ).model_dump()

    raw_items, pagination = extract_items(result.data)
    return ListCorretoresOutput(
        items=raw_items,
        pagination=pagination,
        typed_error=None,
        probe_status="live_probed",
    ).model_dump()


HANDLERS = {"vista.corretores.list": list_corretores}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.corretores.list",
            description=(
                "List Vista brokers. 🔒 PERMISSION-GATED: this tenant returns "
                "401, in which case the response carries a typed_error, an "
                "empty items list and probe_status='permission_gated'. "
                "SUBSTITUTE: `vista.usuarios.list` is ungated and already "
                "returns the broker roster (Setor='Corretores') — prefer it "
                "over waiting on this grant. Paginated (max page_size=50)."
            ),
            inputSchema=ListCorretoresInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
