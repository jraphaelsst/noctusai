"""vista.usuarios.* tools — internal Vista users (live-probed surface)."""
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
    vista_usuario_to_showcase,
)

from noctusai_lib.integrations.vista import calibrator
from ..settings import get_settings
from ..types import ListUsuariosOutput


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


def _typed_error(e: Exception) -> dict:
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


async def list_usuarios(args: dict) -> dict:
    client = _client()
    fields = await calibrator.get_usuario_fields(client)
    try:
        result = await client.listar_usuarios(fields=fields)
    except (
        VistaConfigError,
        VistaPermissionDenied,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return ListUsuariosOutput(items=[], probe_status="live_probed").model_dump() | {
            "error": _typed_error(e)
        }
    raw_items, _ = extract_items(result.data)
    items = [vista_usuario_to_showcase(p).model_dump() for p in raw_items]
    return ListUsuariosOutput(items=items, probe_status="live_probed").model_dump()


HANDLERS = {"vista.usuarios.list": list_usuarios}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.usuarios.list",
            description=(
                "List internal Vista users (brokers, agency staff). Returns "
                "ShowcaseUsuario objects with normalized field names. Email "
                "addresses are returned in the clear — caller is responsible "
                "for any LGPD-mandated masking."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors"]
