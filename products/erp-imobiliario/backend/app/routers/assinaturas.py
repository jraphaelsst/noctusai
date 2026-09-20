"""
Assinatura Digital Router — Digital signature management.

Manages sending documents for signature, tracking signing status,
processing webhook callbacks from providers, and audit trails. Sending
itself is delegated to the seed `signature` IO module — see
`app.services.assinatura_service` and
`projects/signature-integration-CONTRACT.md` §5.

-- CREATE TABLE assinaturas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   documento_nome text NOT NULL,
--   documento_url text,
--   contrato_id uuid,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'enviado', 'assinado', 'recusado', 'expirado', 'cancelado')),
--   provedor text NOT NULL DEFAULT 'interno' CHECK (provedor IN ('interno', 'clicksign', 'docusign', 'd4sign')),
--   link_assinatura text,
--   external_id text,  -- migration 047: the provider's envelope id
--   signatarios jsonb NOT NULL DEFAULT '[]',
--   historico jsonb NOT NULL DEFAULT '[]',
--   data_envio timestamptz,
--   data_assinatura timestamptz,
--   data_expiracao timestamptz,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Callable, Optional, Literal, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from pydantic import Field

from noctusai_lib.integrations.signature import (
    PROVEDORES_SUPORTADOS,
    EnvelopeRecusado,
    ProvedorIndisponivel,
    ProvedorNaoConfigurado,
    SignatureAdapter,
    WebhookInvalido,
    make_signature_adapter,
)

from app.config import settings
from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id, log_action
from app.rate_limit import limiter
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.assinatura_service import AssinaturaService
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assinaturas", tags=["Assinaturas"])

#: Same shape as social-wiring's `card_hub.deps.SignatureAdapterFactory`
#: (this route's sibling — see `get_signature_adapter_factory` below).
SignatureAdapterFactory = Callable[[Optional[str]], SignatureAdapter]


def get_signature_adapter_factory() -> SignatureAdapterFactory:
    """FastAPI dependency — builds the D4Sign adapter the webhook route
    verifies `Content-HMAC` against.

    `org_id=None` on purpose: D4Sign registers ONE callback URL per
    account, not per org (mirrors social-wiring's `card_hub.assinatura_
    webhook_router`'s documented rationale for the identical call) — so
    webhook verification always resolves the PLATFORM-tier credential
    (`resolve_credential`'s `org_settings` tier is skipped;
    `platform_settings`/env still apply). `AssinaturaService`'s own
    per-org `adapter_factory` seam (used by `POST /enviar`) is a
    different call site and is unaffected by this — a org CAN override
    its own send-time credentials; only the shared webhook signature
    check reads the platform-tier one.

    A factory, not an eager instance, so `ProvedorNaoConfigurado` surfaces
    inside the route body (which logs + maps it to 401) rather than as an
    unhandled dependency-resolution error.

    Tests MUST override this seam
    (`app.dependency_overrides[get_signature_adapter_factory] = ...`)
    with one returning a `FakeSignatureAdapter` (`KB § PATTERNS/backend/
    di-test-seam.md` Class-B) — the real one calls D4Sign / raises on a
    missing credential, neither of which is the webhook-parsing behaviour
    under test.
    """
    return lambda org_id: make_signature_adapter(real=True, provedor="d4sign", org_id=org_id)


# --- Pydantic models ---

class Signatario(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=5, max_length=200)
    papel: str = Field(..., min_length=1, max_length=100, description="Papel do signatario (ex: comprador, vendedor, testemunha)")


class EnviarAssinaturaRequest(StrictHttpModel):
    documento_nome: str = Field(..., min_length=1, max_length=300)
    documento_url: Optional[str] = Field(default=None, max_length=1000)
    contrato_id: Optional[str] = None
    signatarios: List[Signatario] = Field(..., min_length=1, description="Lista de signatarios (minimo 1)")
    # "interno"/"clicksign"/"docusign" are still accepted on the wire for
    # backward compatibility, but only "d4sign" is actually supported —
    # anything else is refused with ASSINATURA_PROVEDOR_NAO_CONFIGURADO-
    # shaped 503 naming the provider (contract §5). Default flips to the
    # one provider that works.
    provedor: Optional[Literal["interno", "clicksign", "docusign", "d4sign"]] = "d4sign"


class AssinaturaUpdate(StrictHttpModel):
    documento_nome: Optional[str] = Field(default=None, min_length=1, max_length=300)
    documento_url: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Literal["pendente", "enviado", "assinado", "recusado", "expirado", "cancelado"]] = None
    signatarios: Optional[List[Signatario]] = None
    data_expiracao: Optional[str] = None


# --- Dependencies ---
#
# Exposed as module-level FastAPI dependencies (not built inline in each
# handler) so tests can override them via `app.dependency_overrides[...]`
# instead of patching `AssinaturaService` methods (`KB § PATTERNS/backend/
# di-test-seam.md` — patching our own class would stop exercising it).

def get_assinatura_service(auth = Depends(get_current_user)) -> AssinaturaService:
    """User-scoped `AssinaturaService` for the authenticated endpoints."""
    user, token = auth
    db = get_user_client(token)
    return AssinaturaService(db, user.id, org_id=get_org_id(user))


def get_assinatura_service_webhook() -> AssinaturaService:
    """Admin-scoped `AssinaturaService` for the unauthenticated webhook —
    no `auth` to derive a user/org from; identity is `"webhook"`."""
    db = get_admin_client()
    return AssinaturaService(db, user_id="webhook")


# --- Endpoints ---

@router.post("/enviar")
async def enviar_assinatura(
    body: EnviarAssinaturaRequest,
    auth = Depends(get_current_user),
    service: AssinaturaService = Depends(get_assinatura_service),
):
    """Send a document for digital signing."""
    user, token = auth

    signatarios_data = [s.model_dump() for s in body.signatarios]

    try:
        assinatura = await service.preparar_envio(
            documento_nome=body.documento_nome,
            documento_url=body.documento_url,
            signatarios=signatarios_data,
            provedor=body.provedor or "d4sign",
            contrato_id=body.contrato_id,
        )
    except ProvedorNaoConfigurado as exc:
        # Covers both "credentials missing" and "provider not supported in
        # this version" (assinatura_service raises the same exception for
        # an unsupported provedor, naming it in `faltando` — contract §5).
        raise HTTPException(
            status_code=503,
            detail=f"Plataforma de assinatura não configurada: {', '.join(exc.faltando)}",
        )
    except EnvelopeRecusado:
        raise HTTPException(
            status_code=502,
            detail="A plataforma de assinatura recusou o envio do documento.",
        )
    except ProvedorIndisponivel:
        raise HTTPException(
            status_code=502,
            detail="A plataforma de assinatura está indisponível no momento.",
        )
    except httpx.HTTPError:
        logger.error("Falha ao baixar documento para assinatura", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Não foi possível baixar o documento para assinatura.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not assinatura:
        raise HTTPException(status_code=500, detail="Erro ao enviar documento para assinatura")

    log_action(user.id, "enviar", "assinatura", assinatura["id"],
               f"Enviou documento para assinatura: {body.documento_nome}")

    return success_response(assinatura)


@router.get("")
async def listar_assinaturas(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    contrato_id: Optional[str] = Query(None, description="Filtrar por contrato"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    """List signature requests with filters and pagination."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("assinaturas").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if contrato_id:
        count_query = count_query.eq("contrato_id", contrato_id)

    # Build data query
    query = db.table("assinaturas").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if contrato_id:
        query = query.eq("contrato_id", contrato_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/resumo")
async def resumo_assinaturas(
    auth = Depends(get_current_user),
    service: AssinaturaService = Depends(get_assinatura_service),
):
    """Get signature summary: counts by status."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("assinaturas").select("*").execute()
    assinaturas = result.data or []

    resumo = service.get_resumo(assinaturas)
    return success_response(resumo)


@router.get("/provedores")
async def listar_provedores(auth = Depends(get_current_user)):
    """List the e-signature providers this deployment actually supports.

    Sourced from `noctusai_lib.integrations.signature.PROVEDORES_SUPORTADOS`
    (the same constant `AssinaturaService.preparar_envio` validates
    against) so the FE's provider picker can never drift ahead of what the
    seed adapter will accept — the failure mode task 2 of the 2026-09-20
    wiring audit closed (`Assinaturas.tsx` defaulted to `'interno'` and
    offered 3 providers the seed never shipped, so every untouched send
    503'd).
    """
    return success_response({"suportados": list(PROVEDORES_SUPORTADOS)})


@router.get("/{assinatura_id}")
async def obter_assinatura(assinatura_id: str, auth = Depends(get_current_user)):
    """Get signing details including audit trail."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("assinaturas").select("*").eq("id", assinatura_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Assinatura nao encontrada")
    return success_response(result.data)


@router.post("/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def processar_webhook(
    request: Request,
    service: AssinaturaService = Depends(get_assinatura_service_webhook),
    adapter_factory: SignatureAdapterFactory = Depends(get_signature_adapter_factory),
):
    """
    Callback endpoint for the D4Sign signing provider.

    Unauthenticated — called directly by D4Sign, which posts
    form-urlencoded `uuid` + `type_post` with a `Content-HMAC` header (NOT
    the generic JSON `{assinatura_id, evento}` shape + `X-Hub-Signature-256`
    header this endpoint mistakenly accepted before — 2026-09-20 wiring
    audit, tasks 3+4). Parsing AND signature verification are delegated
    entirely to the seed adapter's `validar_webhook` (`noctusai_lib.
    integrations.signature.real.D4SignAdapter`) — this router never parses
    D4Sign's own wire shape.

    🔴 No unset-credential bypass. A missing/unconfigured platform-tier
    D4Sign credential is a REFUSAL (401), never a pass-through — the
    previous `bypass_when_unset=True` (paired with the wrong signature
    scheme AND a lookup key — `org_settings.assinatura_webhook_secret` —
    nothing ever wrote to) let anyone who learned an `assinatura_id` POST
    a status change with zero verification.
    """
    body = await request.body()

    try:
        adapter = adapter_factory(None)
    except ProvedorNaoConfigurado as exc:
        logger.error(
            "assinaturas-webhook: D4Sign nao configurado na camada de "
            "plataforma: %s", exc,
        )
        raise HTTPException(status_code=401, detail="Webhook nao autorizado")

    try:
        evento = adapter.validar_webhook(body, dict(request.headers))
    except WebhookInvalido as exc:
        logger.warning("assinaturas-webhook: assinatura invalida: %s", exc)
        raise HTTPException(status_code=401, detail="Webhook nao autorizado")

    updated = await service.processar_webhook(evento)

    if not updated:
        raise HTTPException(status_code=404, detail="Assinatura nao encontrada para o webhook")

    logger.info(f"Webhook processado: external_id={evento.external_id}, status={evento.status}")

    return ok_response("Webhook processado com sucesso")


@router.delete("/{assinatura_id}")
async def cancelar_assinatura(
    assinatura_id: str,
    auth = Depends(get_current_user),
    service: AssinaturaService = Depends(get_assinatura_service),
):
    """Cancel a signing request."""
    user, token = auth

    cancelled = await service.cancelar(assinatura_id)

    if not cancelled:
        raise HTTPException(status_code=404, detail="Assinatura nao encontrada")

    log_action(user.id, "cancelar", "assinatura", assinatura_id,
               f"Cancelou assinatura {assinatura_id}")

    return ok_response("Assinatura cancelada com sucesso")
