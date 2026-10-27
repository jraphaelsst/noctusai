"""vista.clientes.* tools — ✅ GRANTED on this tenant since 2026-08-21.

Per `KB § INTEGRATIONS/vista.md § 4.2`, `/clientes/listar` and
`/clientes/detalhes` answered **401** on `oneconsu-rest` until Vista applied
the per-method grant on key `…644c` (2026-08-21, verified by live re-probe
in a fresh process — not on the vendor's word). Both now return 200:
**42,960 clients** on this tenant.

Every other `/clientes/*` sub-route still answers 404 and is genuinely
absent, so it gets no tool here: a tool that can only ever return "no route"
is a lie about the surface. `/clientes/lead` is one of them — but leads CAN
be written back: the route is top-level `/lead`, wrapped by
`vista.leads.submit` (vista.md § 4.2 retraction, § 4.7).

The typed-401 path is KEPT, not deleted — a different tenant key may lack
the grant, and this one's can be rolled back. `probe_status` carries that
distinction to the caller: `permission_gated` means "ask Vista", not
"retry".

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

⚠️ **LGPD — corrected 2026-10-26 against `/clientes/listarcampos`.** The
2026-08-21 note here said this tenant exposes no CPF/e-mail/address, because
`CPF`, `Email`, `Endereco` were rejected. Those were public-doc NAMES; the
tenant's catalog (91 fields) DOES carry identity PII under its own names —
`CPFCNPJ`, `RG`, `EmailResidencial`, `EnderecoResidencial`, bank account,
spouse data, plus the `CorretorCliente` relation (broker CPF/RG/CNH). The
calibrated default projection (`CANDIDATE_CLIENTE_FIELDS`) deliberately
excludes all of them and is pinned by a test; the data-category intake
(`KB § PATTERNS/security/lgpd.md`) still gates bulk ingestion — a grant is
permission, not authorization. The MCP server itself does not persist
responses.

Added 2026-10-27: `vista.clientes.history` (the `historicos` relation — there
is no `/clientes/historico` route) and `vista.clientes.list_filters`
(`/clientes/listarConteudo`).
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    DEFAULT_HISTORICO_CLIENTE_FIELDS,
    calibrator,
    extract_items,
    resolve_fields,
)

from ..types import (
    GetClienteInput,
    GetClienteOutput,
    HistoryInput,
    HistoryOutput,
    ListClienteFiltersInput,
    ListClientesInput,
    ListClientesOutput,
    ListImoveisFiltersOutput,
)
from ._common import (
    HANDLED_READ_ERRORS as _HANDLED,
    client as _client,
    history_page,
    probe_status_for as _probe_status,
    typed_error as _typed_error,
)


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


async def cliente_history(args: dict) -> dict:
    """Client history — `historicos` relation on /clientes/detalhes, windowed."""
    inp = HistoryInput(**args)
    try:
        result = await _client().historico_cliente(
            inp.codigo, fields=resolve_fields(inp.fields, DEFAULT_HISTORICO_CLIENTE_FIELDS)
        )
    except _HANDLED as e:
        return HistoryOutput(typed_error=_typed_error(e), probe_status=_probe_status(e)).model_dump()
    items, total = history_page(result.data, "historicos", inp.offset, inp.limit)
    return HistoryOutput(items=items, total=total).model_dump()


async def list_clientes_filters(args: dict) -> dict:
    """Distinct values per client field (`/clientes/listarConteudo`)."""
    inp = ListClienteFiltersInput(**args)
    try:
        result = await _client().listar_conteudo_clientes(fields=inp.fields)
    except _HANDLED as e:
        return ListImoveisFiltersOutput(probe_status=_probe_status(e)).model_dump() | {
            "error": _typed_error(e)
        }
    content = result.data if isinstance(result.data, dict) else {}
    filters = {k: v for k, v in content.items() if isinstance(v, list)}
    return ListImoveisFiltersOutput(filters=filters).model_dump()


HANDLERS = {
    "vista.clientes.list": list_clientes,
    "vista.clientes.get": get_cliente,
    "vista.clientes.history": cliente_history,
    "vista.clientes.list_filters": list_clientes_filters,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.clientes.list",
            description=(
                "List Vista clients (customers/leads). ✅ GRANTED on this tenant "
                "2026-08-21 — returns 200 over ~42,960 clients. If a response "
                "ever carries probe_status='permission_gated', the grant was "
                "rolled back: ask Vista, do NOT retry. Paginated (max "
                "page_size=50) and there is NO DataAtualizacao field on this "
                "tenant, so clientes cannot be delta-synced — a full crawl is "
                "~860 requests. LGPD: the default projection returns Celular / "
                "DataNascimento / Sexo / EstadoCivil / Profissao (personal "
                "data) and deliberately NOT the identity fields the tenant also "
                "holds (CPFCNPJ, RG, EmailResidencial, EnderecoResidencial, "
                "bank account)."
            ),
            inputSchema=ListClientesInput.model_json_schema(),
        ),
        Tool(
            name="vista.clientes.get",
            description=(
                "Fetch one Vista client by code (`/clientes/detalhes`). ✅ "
                "GRANTED on this tenant 2026-08-21, exactly like "
                "vista.clientes.list. Note the permission check precedes "
                "parameter validation, so if the grant is ever rolled back a "
                "bad code still reads as 401 rather than 400. LGPD: returns "
                "Celular / DataNascimento / Sexo / EstadoCivil / Profissao — "
                "personal data; identity fields (CPFCNPJ, RG, addresses, bank) "
                "exist on this tenant but are NOT in the projection."
            ),
            inputSchema=GetClienteInput.model_json_schema(),
        ),
        Tool(
            name="vista.clientes.history",
            description=(
                "Client HISTORY for one client code — the `historicos` relation "
                "on /clientes/detalhes (there is no history route; "
                "/clientes/historico is 404). Whole history in one call, "
                "windowed client-side by `offset`/`limit`; `total` is the full "
                "count. Default sub-fields: Data, Hora, Assunto, Pendente, "
                "Codigoimovel, VeiculodeCaptacao — note Vista silently OMITS "
                "`Data` on this relation (Hora comes back). `Texto` (free "
                "text) and `ValorProposta` are opt-in via `fields`."
            ),
            inputSchema=HistoryInput.model_json_schema(),
        ),
        Tool(
            name="vista.clientes.list_filters",
            description=(
                "Distinct live values per client field "
                "(`/clientes/listarConteudo`), e.g. Status, Interesse, "
                "VeiculoCaptacao — use before filtering clients. `Codigo` is "
                "not enumerable (400)."
            ),
            inputSchema=ListClienteFiltersInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
