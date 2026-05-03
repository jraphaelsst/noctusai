"""vista.diagnostics.* tools — health probes + calibration introspection."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import VistaClient

from ..calibration import calibrator
from ..settings import get_settings
from ..types import CalibratedFieldsOutput, ProbeOutput

PROBE_ENDPOINTS = [
    "/imoveis/listar",
    "/imoveis/listarConteudo",
    "/usuarios/listar",
    "/agencias/listar",
    "/clientes/listar",     # 401 expected on most tenants (vista.md § 4.2)
    "/corretores/listar",   # 401 expected on most tenants (vista.md § 4.5)
    "/imoveis/fotos",       # 404 expected on most tenants (vista.md § 4.1)
]


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


async def probe(args: dict) -> dict:
    """Sequential probe of every endpoint in PROBE_ENDPOINTS.

    Returns a `ProbeOutput` listing each endpoint's status, http_status,
    and latency_ms (when applicable). Used by host operators to verify
    per-tenant endpoint availability at runtime.
    """
    client = _client()
    if not client.configured:
        return ProbeOutput(probes=[], tenant_base_url="", configured=False).model_dump()
    rows = []
    for endpoint in PROBE_ENDPOINTS:
        rows.append(await client.probe(endpoint))
    return ProbeOutput(
        probes=rows,
        tenant_base_url=client.base_url,
        configured=True,
    ).model_dump()


async def list_known_endpoints(args: dict) -> dict:
    """Static catalog of endpoints this MCP knows about + their probe_status."""
    return {
        "endpoints": [
            {"path": "/imoveis/listar", "probe_status": "live_probed", "tool": "vista.imoveis.list"},
            {"path": "/imoveis/detalhes", "probe_status": "live_probed", "tool": "vista.imoveis.get"},
            {"path": "/imoveis/listarConteudo", "probe_status": "live_probed", "tool": "vista.imoveis.list_filters"},
            {"path": "/usuarios/listar", "probe_status": "live_probed", "tool": "vista.usuarios.list"},
            {"path": "/agencias/listar", "probe_status": "live_probed", "tool": "vista.agencias.list"},
            {"path": "/clientes/listar", "probe_status": "permission_gated", "tool": "vista.clientes.list"},
            {"path": "/corretores/listar", "probe_status": "permission_gated", "tool": "vista.corretores.list"},
            {"path": "/imoveis/fotos", "probe_status": "tier_gated", "tool": None},
        ],
    }


async def show_calibrated_fields(args: dict) -> dict:
    """Report the current per-tenant calibration cache.

    Empty until the first real call triggers the lazy probe routine in
    `calibration.py`.
    """
    snap = calibrator.snapshot()
    out = CalibratedFieldsOutput()
    if "imoveis_list" in snap:
        out.imoveis_list = snap["imoveis_list"].safe_fields
        out.calibrated_at = snap["imoveis_list"].calibrated_at
        out.rejected["imoveis_list"] = snap["imoveis_list"].rejected
    if "imoveis_detail" in snap:
        out.imoveis_detail = snap["imoveis_detail"].safe_fields
        out.rejected["imoveis_detail"] = snap["imoveis_detail"].rejected
    if "imoveis_conteudo" in snap:
        out.imoveis_conteudo = [f for f in snap["imoveis_conteudo"].safe_fields if isinstance(f, str)]
        out.rejected["imoveis_conteudo"] = snap["imoveis_conteudo"].rejected
    if "usuarios" in snap:
        out.usuarios = [f for f in snap["usuarios"].safe_fields if isinstance(f, str)]
        out.rejected["usuarios"] = snap["usuarios"].rejected
    if "agencias" in snap:
        out.agencias = [f for f in snap["agencias"].safe_fields if isinstance(f, str)]
        out.rejected["agencias"] = snap["agencias"].rejected
    return out.model_dump()


HANDLERS = {
    "vista.diagnostics.probe": probe,
    "vista.diagnostics.list_known_endpoints": list_known_endpoints,
    "vista.diagnostics.show_calibrated_fields": show_calibrated_fields,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.diagnostics.probe",
            description=(
                "Sequential health probe of every endpoint family this MCP "
                "knows about. Each row reports {endpoint, status, http_status, "
                "latency_ms}. ~1.4s wall-clock for 7 endpoints. Useful for "
                "host operators verifying per-tenant availability."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="vista.diagnostics.list_known_endpoints",
            description=(
                "Static catalog of Vista endpoints this MCP knows about, with "
                "probe_status (live_probed | permission_gated | tier_gated) "
                "and the dotted tool name that wraps each."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="vista.diagnostics.show_calibrated_fields",
            description=(
                "Report the per-tenant safe field-set the calibration routine "
                "has discovered so far. Empty until the first call to a "
                "vista.imoveis.* / .usuarios.* / .agencias.* tool triggers "
                "lazy calibration."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors", "PROBE_ENDPOINTS"]
