"""vista.diagnostics.* tools — health probes + calibration introspection."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    VISTA_ENDPOINT_BASELINE,
    VISTA_WRITE_PERMISSION_BASELINE,
)

from noctusai_lib.integrations.vista import calibrator
from ..settings import get_settings
from ..types import (
    CalibratedFieldsOutput,
    ListFieldsInput,
    ListFieldsOutput,
    ProbeOutput,
    WritePermissionsOutput,
)
from ._common import (
    HANDLED_READ_ERRORS,
    client as _client,
    probe_status_for,
    typed_error as _typed_error,
)

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
    "/status": None,
}

# Which dotted tool writes to each write route (None = no tool on purpose).
_WRITE_TOOL_BY_PATH = {
    "/imoveis/fotos": "vista.imoveis.add_photos",
    "/lead": "vista.leads.submit",
    "/clientes/anexos": None,  # PERMITTED since 2026-10-26; no tool on purpose
}

# Known to this MCP but NOT in the probe loop — either wrapped by a tool that
# needs a required arg / scope param, or confirmed 404/405 on this tenant.
# Listed so a caller stops re-deriving their reachability.
# `absent` ≠ `permission_gated`: a support request will NOT unlock these.
#
# Re-swept against the PUBLISHED method names 2026-08-21 (vistasoft.com.br/api),
# then re-probed 2026-10-26/27 after Vista's "full access" grant on `…644c`,
# which surfaced a large never-seen surface (field catalogs, deals, agenda,
# owners, contracts). HISTORY is not a route on this tenant — it is a field
# relation (`prontuarios` on imóveis, `historicos` on clientes); the
# `/…/historico` rows below stay 404 for that reason. Every row was probed:
# 200/400 = route exists (needs params), 404 = no route, 405 = rejects GET.
_UNPROBED_KNOWN: list[dict] = [
    {"path": "/imoveis/detalhes", "probe_status": "live_probed", "tool": "vista.imoveis.get"},
    # ── opened by the 2026-10-26 grant (live_probed 2026-10-27) ──
    {"path": "/imoveis/listarcampos", "probe_status": "live_probed", "tool": "vista.diagnostics.list_fields"},
    {"path": "/clientes/listarcampos", "probe_status": "live_probed", "tool": "vista.diagnostics.list_fields"},
    {"path": "/usuarios/listarcampos", "probe_status": "live_probed", "tool": "vista.diagnostics.list_fields"},
    {"path": "/agencias/listarcampos", "probe_status": "live_probed", "tool": "vista.diagnostics.list_fields"},
    {"path": "/agenda/listarcampos", "probe_status": "live_probed", "tool": "vista.diagnostics.list_fields"},
    {"path": "/imoveis/destaques", "probe_status": "live_probed", "tool": "vista.imoveis.list_destaques"},
    {"path": "/imoveis/finalidades", "probe_status": "live_probed", "tool": "vista.imoveis.list_finalidades"},
    {"path": "/clientes/listarConteudo", "probe_status": "live_probed", "tool": "vista.clientes.list_filters"},
    {"path": "/negocios/listar", "probe_status": "live_probed", "tool": "vista.negocios.list",
     "note": "needs top-level codigo_pipe XOR codigo_cliente (bare GET → 400)"},
    {"path": "/negocios/detalhes", "probe_status": "live_probed", "tool": "vista.negocios.get"},
    {"path": "/pipes/listar", "probe_status": "live_probed", "tool": "vista.pipes.list",
     "note": "needs pesquisa.filter.Empresa; answers [] on oneconsu-rest (unsettled)"},
    {"path": "/agenda/listar", "probe_status": "live_probed", "tool": "vista.agenda.list"},
    {"path": "/agenda/detalhes", "probe_status": "live_probed", "tool": "vista.agenda.get"},
    {"path": "/proprietarios/listar", "probe_status": "live_probed", "tool": "vista.proprietarios.list",
     "note": "identity-PII family (LGPD) — tool defaults to Codigo+Nome"},
    {"path": "/proprietarios/detalhes", "probe_status": "live_probed", "tool": "vista.proprietarios.get"},
    {"path": "/contratos/listar", "probe_status": "live_probed", "tool": "vista.contratos.list"},
    {"path": "/vendas", "probe_status": "live_probed", "tool": None,
     "note": "route exists (bare GET → 500); query shape unknown"},
    {"path": "/reloadcache", "probe_status": "live_probed", "tool": None,
     "note": "Vista-side cache flush — side-effecting; never call from an automatic probe"},
    # ── write-only routes found 2026-10-26 (GET → 405); no tool on purpose ──
    {"path": "/negocios/etapas", "probe_status": "write_only", "tool": None,
     "note": "PUT-only — moves a deal between pipeline stages"},
    {"path": "/contratos/detalhes", "probe_status": "write_only", "tool": None,
     "note": "POST/PUT-only; empty POST passes auth (400 'informar os dados no indice fields')"},
    # ── still 404 after the 2026-10-26 grant (no catalog route) ──
    {"path": "/negocios/listarcampos", "probe_status": "absent", "tool": None},
    {"path": "/proprietarios/listarcampos", "probe_status": "absent", "tool": None,
     "note": "owner fields = the `proprietarios` relation of /imoveis/listarcampos"},
    {"path": "/contratos/listarcampos", "probe_status": "absent", "tool": None},
    {"path": "/corretores/listarcampos", "probe_status": "absent", "tool": None},
    {"path": "/corretores/detalhes", "probe_status": "absent", "tool": None},
    {"path": "/corretores/listarConteudo", "probe_status": "absent", "tool": None},
    # ── /clientes sub-routes: documented by Vista, absent on this tenant ──
    {"path": "/clientes/historico", "probe_status": "absent", "tool": None,
     "note": "history is the `historicos` relation → vista.clientes.history"},
    {"path": "/clientes/porcorretor", "probe_status": "absent", "tool": None},
    {"path": "/clientes/poragencia", "probe_status": "absent", "tool": None},
    {"path": "/clientes/favoritos", "probe_status": "absent", "tool": None},
    {"path": "/clientes/campos", "probe_status": "absent", "tool": None,
     "note": "the real catalog route is /clientes/listarcampos"},
    # Absent under THIS name — leads are top-level `/lead` (write rows below).
    {"path": "/clientes/lead", "probe_status": "absent", "tool": None},
    {"path": "/clientes/cadastrar", "probe_status": "absent", "tool": None},
    {"path": "/clientes/update", "probe_status": "absent", "tool": None},
    {"path": "/clientes/cadhis", "probe_status": "absent", "tool": None},
    {"path": "/clientes/cadcor", "probe_status": "absent", "tool": None},
    # ── /imoveis sub-routes: documented by Vista, absent on this tenant ──
    {"path": "/imoveis/listas", "probe_status": "absent", "tool": None},
    {"path": "/imoveis/campos", "probe_status": "absent", "tool": None,
     "note": "the real catalog route is /imoveis/listarcampos"},
    {"path": "/imoveis/historico", "probe_status": "absent", "tool": None,
     "note": "history is the `prontuarios` relation → vista.imoveis.history"},
    {"path": "/imoveis/docs", "probe_status": "absent", "tool": None},
    {"path": "/imoveis/porcorretor", "probe_status": "absent", "tool": None},
    {"path": "/imoveis/poragencia", "probe_status": "absent", "tool": None},
    {"path": "/imoveis/cadastrar", "probe_status": "absent", "tool": None},
    {"path": "/imoveis/update", "probe_status": "absent", "tool": None},
]


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

    Statuses (all re-probed live 2026-08-21 — vista.md § 4, § 8):
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
    # Write routes carry this key's recorded write verdict. `/imoveis/fotos`
    # is already a read-baseline row (its bare GET is 405), so it is enriched
    # in place rather than listed twice.
    by_path = {r["path"]: r for r in rows}
    for path, verdict, _note in VISTA_WRITE_PERMISSION_BASELINE:
        row = by_path.get(path)
        if row is None:
            row = {"path": path, "probe_status": "write_only"}
            rows.append(row)
        row["write_permission"] = verdict
        row["tool"] = _WRITE_TOOL_BY_PATH[path]
    return {"endpoints": rows}


async def probe_write_permissions(args: dict) -> dict:
    """Non-mutating write-permission verdict per write route (vista.md § 4.7).

    Empty POSTs only: Vista authorises before it validates, so the reply
    tells denied from permitted and, with no payload, nothing is created.
    """
    client = _client()
    writes_enabled = get_settings().writes_enabled
    if not client.configured:
        return WritePermissionsOutput(writes_enabled=writes_enabled).model_dump()
    rows, unexpected = [], []
    for endpoint, expected, note in VISTA_WRITE_PERMISSION_BASELINE:
        row = await client.probe_write_permission(endpoint)
        row["expected_verdict"] = expected
        row["as_expected"] = row["verdict"] == expected
        row["note"] = note
        if not row["as_expected"]:
            unexpected.append(endpoint)
        rows.append(row)
    return WritePermissionsOutput(
        probes=rows, configured=True, unexpected=unexpected, writes_enabled=writes_enabled
    ).model_dump()


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
    # `corretores` is no longer calibrated (2026-10-27): the route ignores
    # `fields` and always answers Codigo + Nome, so `out.corretores` stays
    # empty by design — see `calibration.CORRETOR_RETURNED_FIELDS`.
    return out.model_dump()


async def list_fields(args: dict) -> dict:
    """The tenant's real field catalog for one family (`/<family>/listarcampos`)."""
    inp = ListFieldsInput(**args)
    try:
        result = await _client().listar_campos(inp.family)
    except HANDLED_READ_ERRORS as e:
        return ListFieldsOutput(
            family=inp.family, typed_error=_typed_error(e), probe_status=probe_status_for(e)
        ).model_dump()
    data = result.data if isinstance(result.data, dict) else {}
    fields = {k: [str(f) for f in v] for k, v in data.items() if isinstance(v, list)}
    return ListFieldsOutput(family=inp.family, fields=fields).model_dump()


HANDLERS = {
    "vista.diagnostics.probe": probe,
    "vista.diagnostics.list_known_endpoints": list_known_endpoints,
    "vista.diagnostics.probe_write_permissions": probe_write_permissions,
    "vista.diagnostics.show_calibrated_fields": show_calibrated_fields,
    "vista.diagnostics.list_fields": list_fields,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.diagnostics.probe",
            # Endpoint count is DERIVED from the seed-canonical baseline, never
            # typed. It was hand-written as "7" and silently went stale the day
            # `/clientes/detalhes` joined the baseline (2026-08-19) — leaving the
            # host LLM told to expect one fewer row than the probe returns, on
            # precisely the row that detects the Tier-1 grant landing.
            description=(
                "Sequential health probe of every endpoint family this MCP "
                "knows about. Each row reports {endpoint, status, http_status, "
                "latency_ms, expected_http_status, as_expected, note}. Probes "
                f"{len(VISTA_ENDPOINT_BASELINE)} endpoints sequentially (~1.4s "
                "wall-clock). Read the `unexpected` list to see "
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
            name="vista.diagnostics.probe_write_permissions",
            description=(
                "Non-mutating check of whether this tenant key may WRITE to "
                "each Vista write route (/imoveis/fotos, /lead, "
                "/clientes/anexos). Sends empty POSTs — Vista checks "
                "permission before parameters, so nothing is ever created. "
                "Each row: {endpoint, verdict (permitted|denied|absent|"
                "unknown), http_status, expected_verdict, as_expected, note}. "
                "Use it to verify a vendor-side grant actually landed; read "
                "`unexpected` first."
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
        Tool(
            name="vista.diagnostics.list_fields",
            description=(
                "Read the tenant's REAL field catalog for a family "
                "(`/<family>/listarcampos`; family ∈ imoveis | clientes | "
                "usuarios | agencias | agenda). Returns {family: [fields], "
                "Relation: [sub-fields]} — e.g. imoveis carries the "
                "`prontuarios` (history) and `proprietarios` (owners, PII) "
                "relations, clientes the `historicos` and `CorretorCliente` "
                "ones. Use it before passing any `fields` argument and before "
                "concluding a capability is absent: on this tenant history and "
                "owner data are field relations, not routes. Field NAMES only — "
                "no records are read."
            ),
            inputSchema=ListFieldsInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "PROBE_ENDPOINTS"]
