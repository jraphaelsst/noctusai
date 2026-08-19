"""vista.diagnostics.* tools — health probes + calibration introspection."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import VISTA_ENDPOINT_BASELINE, VistaClient

from noctusai_lib.integrations.vista import calibrator
from ..settings import get_settings
from ..types import CalibratedFieldsOutput, ProbeOutput

# The endpoint baseline is seed-canonical (`VISTA_ENDPOINT_BASELINE`) — this
# module and the ERP showcase service consume the SAME tuple, so a re-probe
# updates one place. Kept as a module alias for back-compat with callers that
# imported `PROBE_ENDPOINTS` from here.
PROBE_ENDPOINTS = VISTA_ENDPOINT_BASELINE

# Which dotted tool wraps each probed path (None = reachable but unwrapped).
_TOOL_BY_PATH = {
    "/imoveis/listar": "vista.imoveis.list",
    "/imoveis/listarConteudo": "vista.imoveis.list_filters",
    "/usuarios/listar": "vista.usuarios.list",
    "/agencias/listar": "vista.agencias.list",
    "/clientes/listar": "vista.clientes.list",
    "/clientes/detalhes": "vista.clientes.get",
    "/corretores/listar": "vista.corretores.list",
}

# Known to Vista's public docs but NOT in the probe loop — either wrapped by a
# tool that takes a required arg (`/imoveis/detalhes`), or confirmed 404 on
# this tenant. Listed so a caller stops re-deriving their reachability.
# `absent` ≠ `permission_gated`: a support request will NOT unlock these.
_UNPROBED_KNOWN: list[dict] = [
    {"path": "/imoveis/detalhes", "probe_status": "live_probed", "tool": "vista.imoveis.get"},
    {"path": "/clientes/pesquisar", "probe_status": "absent", "tool": None},
    {"path": "/clientes/historicos", "probe_status": "absent", "tool": None},
    {"path": "/clientes/lead", "probe_status": "absent", "tool": None},
    {"path": "/clientes/cadastrar", "probe_status": "absent", "tool": None},
]


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


async def probe(args: dict) -> dict:
    """Sequential probe of every endpoint in PROBE_ENDPOINTS.

    Each row carries the live result AND the documented baseline, so a
    caller can tell "this tenant drifted" apart from "this endpoint always
    answers a bare GET that way". `unexpected` lists only the genuine
    deviations — that is the field an operator should read first.
    """
    client = _client()
    if not client.configured:
        return ProbeOutput(probes=[], tenant_base_url="", configured=False).model_dump()
    rows = []
    unexpected = []
    for endpoint, expected_status, _probe_status, note in PROBE_ENDPOINTS:
        row = await client.probe(endpoint)
        as_expected = row.get("http_status") == expected_status
        row["expected_http_status"] = expected_status
        row["as_expected"] = as_expected
        row["note"] = note
        if not as_expected:
            unexpected.append(endpoint)
        rows.append(row)
    return ProbeOutput(
        probes=rows,
        tenant_base_url=client.base_url,
        configured=True,
        unexpected=unexpected,
    ).model_dump()


async def list_known_endpoints(args: dict) -> dict:
    """Static catalog of endpoints this MCP knows about + their probe_status.

    Statuses (all re-probed live 2026-08-05 — vista.md § 4, § 8):
      live_probed       — reachable, wrapped by a tool.
      permission_gated  — route EXISTS, this tenant's key lacks the
                          per-method grant. One Vista-side flag away.
      write_only        — route exists but rejects GET (405). Needs POST.
      absent            — no route at all (404). Not a permission problem;
                          asking Vista to "grant" it will not help.

    The permission_gated/absent split is the actionable one: only the
    former is unlocked by a support request. See vista.md § 4.2.
    """
    # Probed rows derive from the seed baseline — never restated here, so the
    # catalog cannot disagree with what `probe` actually measures.
    rows = [
        {"path": path, "probe_status": probe_status, "tool": _TOOL_BY_PATH.get(path)}
        for path, _expected, probe_status, _note in VISTA_ENDPOINT_BASELINE
    ]
    rows.extend(_UNPROBED_KNOWN)
    return {"endpoints": rows}


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
    # 🔒 Gated families. These stay empty on a 401 BY DESIGN — `_calibrate`
    # returns the floor without caching a permission denial, so an empty list
    # here means "still gated", never "calibrated to nothing".
    if "clientes" in snap:
        out.clientes = [f for f in snap["clientes"].safe_fields if isinstance(f, str)]
        out.rejected["clientes"] = snap["clientes"].rejected
    if "corretores" in snap:
        out.corretores = [f for f in snap["corretores"].safe_fields if isinstance(f, str)]
        out.rejected["corretores"] = snap["corretores"].rejected
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
                "latency_ms, expected_http_status, as_expected, note}. ~1.4s "
                "wall-clock for 7 endpoints. Read the `unexpected` list to see "
                "genuine deviations: several endpoints answer a bare GET with "
                "400/401/405 BY DESIGN, so a non-200 row is not itself a fault."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="vista.diagnostics.list_known_endpoints",
            description=(
                "Static catalog of Vista endpoints this MCP knows about, with "
                "probe_status (live_probed | permission_gated | write_only | "
                "absent) and the dotted tool name that wraps each. "
                "permission_gated = route exists, key lacks the grant (a "
                "support request unlocks it); absent = 404, no such route on "
                "this tenant (a request will NOT unlock it)."
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
