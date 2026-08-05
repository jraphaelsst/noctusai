"""Vista showcase service — coordinates per-tab fetches + audit logging.

The router never instantiates VistaClient directly; it goes through this
module so every outbound call is funnelled through the same audit path.

LGPD posture: see `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` § 5.4
(audit-log contract). The Vista response payload is NEVER persisted —
`_audit` only stores metadata (path, status, latency, params keys). The
DTOs returned to the caller include the raw payload so the live request
can render in-memory, but nothing about the payload survives the request
lifecycle on the server.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app import dependencies as _deps  # call _deps.log_action(...) so test patches apply
from noctusai_lib.integrations.vista import (
    VISTA_PROBE_PATHS,
    VistaCallResult,
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
    extract_items,
    vista_agencia_to_showcase,
    vista_imovel_detalhes_to_showcase,
    vista_imovel_to_showcase,
    vista_usuario_to_showcase,
)

from app.services.vista_showcase_types import (
    ShowcaseDiagnostic,
    ShowcaseEnvelope,
    ShowcasePagination,
    ShowcaseTabStatus,
)

logger = logging.getLogger(__name__)


# Field sets calibrated against the live tenant `oneconsu-rest.vistahost.com.br`
# 2026-05-02, re-verified 2026-05-03 (full inventory + per-field rationale in
# KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md §5.1).
# Vista enforces field-level permissions per tenant key; unknown / blocked
# fields return HTTP 400 with `Campo X não está disponível` and fail the
# WHOLE request. Restrict to fields verified live before adding more.
#
# IMPORTANT — per-tenant calibration is NOT runtime-probed. Constants below
# are hardcoded for `oneconsu-rest`. A different tenant key may need a
# different set; see vista.md §6 ("Per-tenant calibration — current state
# vs design intent") for the gap and the Phase-0/1 routine the in-repo
# MCP server must ship to fix it generically.
#
# Tenant-specific notes:
#   - `Estado` is rejected — Vista returns the UF in a field literally named `UF`.
#   - `Banheiros` (aggregate count) is rejected — `BanheiroSocial` is what's exposed.
#   - `Foto` is rejected on listar/detalhes — the listing only exposes `FotoDestaque`.
#   - `Slug`, `PalavrasChave`, `CodigoImobiliaria`, `FotoPrincipal` all rejected.
IMOVEL_LIST_FIELDS: list[Any] = [
    "Codigo", "TituloSite", "Categoria", "Finalidade", "Status",
    "Cidade", "Bairro", "Endereco", "CEP", "UF",
    "ValorVenda", "ValorLocacao",
    "AreaTotal", "AreaPrivativa", "AreaConstruida",
    "Dormitorios", "Suites", "Vagas", "BanheiroSocial",
    "FotoDestaque",
    "Latitude", "Longitude",
    "DataAtualizacao",
    {"Corretor": ["Nome", "Email"]},
]

IMOVEL_DETAIL_FIELDS: list[Any] = [
    "Codigo", "TituloSite", "Categoria", "Finalidade", "Status",
    "Cidade", "Bairro", "Endereco", "Numero", "Complemento", "CEP", "UF",
    "ValorVenda", "ValorLocacao",
    "AreaTotal", "AreaPrivativa", "AreaConstruida",
    "Dormitorios", "Suites", "Vagas", "BanheiroSocial",
    "Latitude", "Longitude",
    "DataCadastro", "DataAtualizacao",
    "Caracteristicas",
    "Empreendimento", "Construtora",
    {"Corretor": ["Nome", "Email", "Fone"]},
]

USUARIO_FIELDS = ["Codigo", "Nome", "Email", "Foto", "Setor"]
AGENCIA_FIELDS = ["Codigo", "Nome", "Endereco", "Cidade", "Bairro", "Site"]
CONTEUDO_FIELDS = ["Status", "Categoria", "Cidade", "Bairro"]

KNOWN_TABS: list[ShowcaseTabStatus] = [
    ShowcaseTabStatus(tab="imoveis", label="Imóveis", status="live", endpoint="/imoveis/listar"),
    ShowcaseTabStatus(tab="usuarios", label="Usuários", status="live", endpoint="/usuarios/listar"),
    ShowcaseTabStatus(tab="agencias", label="Agência", status="live", endpoint="/agencias/listar"),
    ShowcaseTabStatus(
        tab="clientes", label="Clientes", status="permission_denied",
        endpoint="/clientes/listar",
        note="Permissão pendente — solicite expansão de chave junto à Vista (código 401).",
    ),
    ShowcaseTabStatus(
        tab="corretores", label="Corretores", status="permission_denied",
        endpoint="/corretores/listar",
        note="Permissão pendente — solicite expansão de chave junto à Vista (código 401).",
    ),
    ShowcaseTabStatus(
        tab="fotos", label="Fotos", status="not_found",
        endpoint="/imoveis/fotos",
        note="Endpoint /imoveis/fotos não está habilitado neste tenant (404). As fotos primárias aparecem direto em /imoveis/listar e estão visíveis no tab Imóveis.",
    ),
    ShowcaseTabStatus(tab="diagnostico", label="Diagnóstico", status="live", endpoint="(adapter)"),
]


# ---------------------------------------------------------------------------
# Audit-log helper — single audit path for every Vista call
# ---------------------------------------------------------------------------


def _audit(
    *,
    user_id: str,
    result: Optional[VistaCallResult] = None,
    error: Optional[Exception] = None,
    endpoint: str,
    entidade_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Insert one row into erp.user_actions_log for an outbound Vista call.

    Never persists the Vista response body — only metadata. See § 5 of
    PROJECT.md and § 3 of VISTA-API.md.
    """
    detalhes: dict[str, Any] = {
        "endpoint": endpoint,
        "tenant_call": True,
    }
    if result is not None:
        detalhes["status"] = result.status
        detalhes["latency_ms"] = result.latency_ms
        detalhes["params_keys"] = result.params_keys
    if error is not None:
        detalhes["error_class"] = type(error).__name__
        detalhes["error"] = str(error)[:300]
        if isinstance(error, VistaUpstreamError):
            detalhes["status"] = error.status
    if extra:
        detalhes.update(extra)

    descricao = f"{'OK' if result else 'ERRO'} GET {endpoint}"
    try:
        _deps.log_action(
            user_id=user_id,
            tipo_acao="consulta_externa",
            tipo_entidade="integracao_vista",
            entidade_id=entidade_id,
            descricao=descricao,
            detalhes=detalhes,
        )
    except Exception as e:  # pragma: no cover — log_action already swallows
        logger.warning("vista audit-log failed (%s); continuing", e)


# ---------------------------------------------------------------------------
# Tab catalog
# ---------------------------------------------------------------------------


def list_tabs(client: VistaClient) -> list[ShowcaseTabStatus]:
    """Return the static tab catalog with `not_configured` overrides if creds are missing."""
    if client.configured:
        return KNOWN_TABS
    return [
        t.model_copy(update={"status": "not_configured", "note": "VISTA_BASE_URL / VISTA_API_KEY ausentes."})
        if t.tab not in {"diagnostico"}
        else t
        for t in KNOWN_TABS
    ]


# ---------------------------------------------------------------------------
# Imóveis tab
# ---------------------------------------------------------------------------


async def fetch_imoveis(
    client: VistaClient,
    *,
    user_id: str,
    page: int = 1,
    page_size: int = 50,
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    cidade: Optional[str] = None,
    bairro: Optional[str] = None,
    finalidade: Optional[str] = None,
) -> ShowcaseEnvelope:
    filter_: dict[str, Any] = {}
    if status:
        filter_["Status"] = status
    if categoria:
        filter_["Categoria"] = categoria
    if cidade:
        filter_["Cidade"] = cidade
    if bairro:
        filter_["Bairro"] = bairro
    if finalidade:
        filter_["Finalidade"] = finalidade

    try:
        result = await client.listar_imoveis(
            fields=IMOVEL_LIST_FIELDS,
            filter_=filter_ or None,
            order={"DataAtualizacao": "desc"},
            page=page,
            page_size=page_size,
        )
    except (VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaConfigError, VistaUpstreamError) as e:
        _audit(user_id=user_id, error=e, endpoint="/imoveis/listar")
        raise

    _audit(user_id=user_id, result=result, endpoint="/imoveis/listar")

    raw_items, pagination = extract_items(result.data)
    items = [vista_imovel_to_showcase(p).model_dump() for p in raw_items]
    return ShowcaseEnvelope(
        tab="imoveis",
        fetched_at=_now_iso(),
        pagination=ShowcasePagination(
            pagina=int(pagination.get("pagina") or page),
            quantidade=int(pagination.get("quantidade") or len(items)),
            total=int(pagination["total"]) if pagination.get("total") not in (None, "") else None,
            paginas=int(pagination["paginas"]) if pagination.get("paginas") not in (None, "") else None,
        ),
        items=items,
    )


async def fetch_imovel_detalhes(
    client: VistaClient, *, user_id: str, codigo: str
) -> ShowcaseEnvelope:
    listing_row: Optional[dict] = None
    try:
        listing_call = await client.listar_imoveis(
            fields=IMOVEL_LIST_FIELDS,
            filter_={"Codigo": codigo},
            page=1,
            page_size=1,
        )
        _audit(
            user_id=user_id, result=listing_call, endpoint="/imoveis/listar",
            entidade_id=codigo, extra={"phase": "detail-listing-prefetch"},
        )
        items, _ = extract_items(listing_call.data)
        if items:
            listing_row = items[0]
    except (VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaUpstreamError) as e:
        _audit(
            user_id=user_id, error=e, endpoint="/imoveis/listar", entidade_id=codigo,
            extra={"phase": "detail-listing-prefetch"},
        )
        # Listing prefetch failure is non-fatal — we still try detalhes.

    try:
        result = await client.detalhes_imovel(codigo, fields=IMOVEL_DETAIL_FIELDS)
    except (VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaConfigError, VistaUpstreamError, VistaFieldNotAvailable) as e:
        _audit(user_id=user_id, error=e, endpoint="/imoveis/detalhes", entidade_id=codigo)
        raise

    _audit(user_id=user_id, result=result, endpoint="/imoveis/detalhes", entidade_id=codigo)

    detalhes_payload = result.data if isinstance(result.data, dict) else {}
    dto = vista_imovel_detalhes_to_showcase(detalhes_payload, listing_payload=listing_row)
    return ShowcaseEnvelope(
        tab="imoveis-detalhes",
        fetched_at=_now_iso(),
        items=[dto.model_dump()],
    )


async def fetch_imoveis_conteudo(
    client: VistaClient, *, user_id: str
) -> ShowcaseEnvelope:
    try:
        result = await client.listar_conteudo_imoveis(fields=CONTEUDO_FIELDS)
    except (VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaConfigError, VistaUpstreamError) as e:
        _audit(user_id=user_id, error=e, endpoint="/imoveis/listarConteudo")
        raise

    _audit(user_id=user_id, result=result, endpoint="/imoveis/listarConteudo")

    content = result.data if isinstance(result.data, dict) else {}
    return ShowcaseEnvelope(
        tab="imoveis-conteudo",
        fetched_at=_now_iso(),
        items=[content],
    )


# ---------------------------------------------------------------------------
# Usuários + Agência tabs
# ---------------------------------------------------------------------------


async def fetch_usuarios(
    client: VistaClient, *, user_id: str
) -> ShowcaseEnvelope:
    try:
        result = await client.listar_usuarios(fields=USUARIO_FIELDS)
    except (VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaConfigError, VistaUpstreamError) as e:
        _audit(user_id=user_id, error=e, endpoint="/usuarios/listar")
        raise

    _audit(user_id=user_id, result=result, endpoint="/usuarios/listar")

    raw_items, _ = extract_items(result.data)
    items = [vista_usuario_to_showcase(p).model_dump() for p in raw_items]
    return ShowcaseEnvelope(
        tab="usuarios",
        fetched_at=_now_iso(),
        items=items,
    )


async def fetch_agencias(
    client: VistaClient, *, user_id: str
) -> ShowcaseEnvelope:
    try:
        result = await client.listar_agencias(fields=AGENCIA_FIELDS)
    except (VistaPermissionDenied, VistaNotFound, VistaTimeout, VistaConfigError, VistaUpstreamError) as e:
        _audit(user_id=user_id, error=e, endpoint="/agencias/listar")
        raise

    _audit(user_id=user_id, result=result, endpoint="/agencias/listar")

    raw_items, _ = extract_items(result.data)
    items = [vista_agencia_to_showcase(p).model_dump() for p in raw_items]
    return ShowcaseEnvelope(
        tab="agencias",
        fetched_at=_now_iso(),
        items=items,
    )


# ---------------------------------------------------------------------------
# Diagnostic tab — admin-only health probe
# ---------------------------------------------------------------------------


# Seed-canonical (`noctusai_lib.integrations.vista.VISTA_PROBE_PATHS`) — this
# used to be a hand-copied fork of the MCP server's identical list, and both
# drifted the same way. Consume, never restate. See vista.md § 5.3.
PROBE_ENDPOINTS = list(VISTA_PROBE_PATHS)


async def diagnose(client: VistaClient, *, user_id: str) -> ShowcaseDiagnostic:
    # TODO(perf): probes run sequentially (≈1.4s for 7 endpoints). If probe
    # count or tenant count grows, parallelize via asyncio.gather. Acceptable
    # for now — admin-only debug tool, latency is observable not user-blocking.
    if not client.configured:
        return ShowcaseDiagnostic(
            tenant_base_url="",
            configured=False,
            probes=[],
        )
    probes: list[dict] = []
    for endpoint in PROBE_ENDPOINTS:
        probe_result = await client.probe(endpoint)
        probes.append(probe_result)
    _audit(
        user_id=user_id,
        endpoint="/diagnostico",
        result=None,
        extra={
            "probe_endpoints": PROBE_ENDPOINTS,
            "probe_outcomes": [p["status"] for p in probes],
        },
    )
    return ShowcaseDiagnostic(
        tenant_base_url=client.base_url,
        configured=True,
        probes=probes,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
