"""vista.imoveis.* tools — properties (the live-probed surface).

Tools registered:
- vista.imoveis.list           — paginated property listing with filters
- vista.imoveis.get            — full property detail (auto-fetches photo from listar)
- vista.imoveis.list_filters   — enum content for Status/Categoria/Cidade/Bairro
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from noctusai_lib.integrations.vista import (
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
    extract_items,
    vista_imovel_detalhes_to_showcase,
    vista_imovel_to_showcase,
)

from ..calibration import calibrator
from ..settings import get_settings
from ..types import (
    GetImovelInput,
    GetImovelOutput,
    ListImoveisFiltersOutput,
    ListImoveisInput,
    ListImoveisOutput,
)

logger = logging.getLogger(__name__)


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


def _typed_error(e: Exception) -> dict:
    """Render a typed Vista error as a JSON-friendly payload (vista.md § 3.4)."""
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


# ─── Handlers ────────────────────────────────────────────────────────────


async def list_imoveis(args: dict) -> dict:
    inp = ListImoveisInput(**args)
    client = _client()
    fields = await calibrator.get_imovel_list_fields(client)

    filter_: dict[str, Any] = {}
    if inp.status:
        filter_["Status"] = inp.status
    if inp.categoria:
        filter_["Categoria"] = inp.categoria
    if inp.cidade:
        filter_["Cidade"] = inp.cidade
    if inp.bairro:
        filter_["Bairro"] = inp.bairro
    if inp.finalidade:
        filter_["Finalidade"] = inp.finalidade

    try:
        result = await client.listar_imoveis(
            fields=fields,
            filter_=filter_ or None,
            order={"DataAtualizacao": "desc"},
            page=inp.page,
            page_size=inp.page_size,
        )
    except (
        VistaConfigError,
        VistaPermissionDenied,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return ListImoveisOutput(
            items=[],
            pagination={},
            probe_status="live_probed",
        ).model_dump() | {"error": _typed_error(e)}

    raw_items, pagination = extract_items(result.data)
    items = [vista_imovel_to_showcase(p).model_dump() for p in raw_items]
    return ListImoveisOutput(
        items=items,
        pagination=pagination,
        probe_status="live_probed",
    ).model_dump()


async def get_imovel(args: dict) -> dict:
    inp = GetImovelInput(**args)
    client = _client()

    list_fields = await calibrator.get_imovel_list_fields(client)
    detail_fields = await calibrator.get_imovel_detail_fields(client)

    # Prefetch the listing row to grab FotoDestaque (vista.md § 4.1
    # /imoveis/detalhes quirks). Non-fatal on failure.
    listing_row = None
    try:
        listing_call = await client.listar_imoveis(
            fields=list_fields,
            filter_={"Codigo": inp.codigo},
            page=1,
            page_size=1,
        )
        items, _ = extract_items(listing_call.data)
        if items:
            listing_row = items[0]
    except (VistaConfigError, VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaUpstreamError) as e:
        logger.info("get_imovel: listing prefetch failed (non-fatal): %s", e)

    try:
        result = await client.detalhes_imovel(inp.codigo, fields=detail_fields)
    except VistaNotFound:
        return GetImovelOutput(item=None, probe_status="live_probed").model_dump()
    except (
        VistaConfigError,
        VistaPermissionDenied,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return GetImovelOutput(item=None, probe_status="live_probed").model_dump() | {
            "error": _typed_error(e)
        }

    detalhes_payload = result.data if isinstance(result.data, dict) else {}
    dto = vista_imovel_detalhes_to_showcase(detalhes_payload, listing_payload=listing_row)
    return GetImovelOutput(item=dto.model_dump(), probe_status="live_probed").model_dump()


async def list_imoveis_filters(args: dict) -> dict:
    client = _client()
    fields = await calibrator.get_imovel_conteudo_fields(client)
    try:
        result = await client.listar_conteudo_imoveis(fields=fields)
    except (
        VistaConfigError,
        VistaPermissionDenied,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return ListImoveisFiltersOutput(filters={}, probe_status="live_probed").model_dump() | {
            "error": _typed_error(e)
        }
    content = result.data if isinstance(result.data, dict) else {}
    # Vista returns {field_name: [values...]} — pass through as-is.
    filters = {k: v for k, v in content.items() if isinstance(v, list)}
    return ListImoveisFiltersOutput(filters=filters, probe_status="live_probed").model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "vista.imoveis.list": list_imoveis,
    "vista.imoveis.get": get_imovel,
    "vista.imoveis.list_filters": list_imoveis_filters,
}


def register(server: Server) -> dict:
    """Return this module's {tool_name: handler} map.

    server.py aggregates these into a single dispatch table at startup,
    plus collects `tool_descriptors()` from each module for the MCP
    `list_tools` response.
    """
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.imoveis.list",
            description=(
                "List Vista properties. Paginated (max page_size=50). Returns "
                "ShowcaseImovel objects with normalized field names. Supports "
                "Status/Categoria/Cidade/Bairro/Finalidade filters — call "
                "`vista.imoveis.list_filters` first to discover live enum values "
                "for this tenant."
            ),
            inputSchema=ListImoveisInput.model_json_schema(),
        ),
        Tool(
            name="vista.imoveis.get",
            description=(
                "Fetch full property detail by Codigo. Auto-fetches the listing "
                "row first to populate the photo URL (vista.md § 4.1 quirk). "
                "Returns ShowcaseImovelDetalhes with the full Caracteristicas dict."
            ),
            inputSchema=GetImovelInput.model_json_schema(),
        ),
        Tool(
            name="vista.imoveis.list_filters",
            description=(
                "Discover live enum values for the property filter dropdowns "
                "(Status, Categoria, Cidade, Bairro). Use this BEFORE building "
                "Cidade/Bairro filter strings — note tenant casing duplicates."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors"]
