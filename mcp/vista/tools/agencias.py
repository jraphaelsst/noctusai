"""vista.agencias.* tools — agency metadata (live-probed surface)."""
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
    extract_items,
    vista_agencia_to_showcase,
)

from ..calibration import calibrator
from ..settings import get_settings
from ..types import ListAgenciasOutput


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


def _typed_error(e: Exception) -> dict:
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


async def list_agencias(args: dict) -> dict:
    client = _client()
    fields = await calibrator.get_agencia_fields(client)
    try:
        result = await client.listar_agencias(fields=fields)
    except (
        VistaConfigError,
        VistaPermissionDenied,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return ListAgenciasOutput(items=[], probe_status="live_probed").model_dump() | {
            "error": _typed_error(e)
        }
    raw_items, _ = extract_items(result.data)
    items = [vista_agencia_to_showcase(p).model_dump() for p in raw_items]
    return ListAgenciasOutput(items=items, probe_status="live_probed").model_dump()


HANDLERS = {"vista.agencias.list": list_agencias}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.agencias.list",
            description=(
                "List agencies in this Vista tenant. Single tenant typically "
                "has 1 row. Returns ShowcaseAgencia objects with normalized "
                "field names."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors"]
