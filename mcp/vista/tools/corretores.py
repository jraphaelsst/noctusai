"""vista.corretores.* tools — permission-gated on most tenants.

Same gating story as clientes (see `KB § INTEGRATIONS/vista.md § 4.5`).
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
    extract_items,
)

from ..settings import get_settings
from ..types import ListCorretoresOutput


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


def _typed_error(e: Exception) -> dict:
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


async def list_corretores(args: dict) -> dict:
    client = _client()
    try:
        result = await client.listar_corretores(fields=["Codigo", "Nome"])
    except VistaPermissionDenied as e:
        return ListCorretoresOutput(
            items=[],
            typed_error=_typed_error(e),
            probe_status="live_probed",
        ).model_dump()
    except (
        VistaConfigError,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return ListCorretoresOutput(
            items=[],
            typed_error=_typed_error(e),
            probe_status="live_probed",
        ).model_dump()

    raw_items, _ = extract_items(result.data)
    return ListCorretoresOutput(
        items=raw_items,
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
                "List Vista brokers. PERMISSION-GATED: most tenants return "
                "401, in which case the response carries a typed_error and "
                "an empty items list."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors"]
