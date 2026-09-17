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
import json
import logging
from typing import Optional, Literal, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from pydantic import Field

from noctusai_lib.integrations.signature import (
    EnvelopeRecusado,
    ProvedorIndisponivel,
    ProvedorNaoConfigurado,
)
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id, log_action
from app.rate_limit import limiter
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.assinatura_service import AssinaturaService
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assinaturas", tags=["Assinaturas"])


async def _resolve_assinatura_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Resolve the per-org webhook secret for the assinatura referenced
    in the (unverified) request body.

    Looks up `org_settings.assinatura_webhook_secret` keyed by the
    `org_id` of the named assinatura. Returns a `None` secret when no
    config row exists — paired with `bypass_when_unset=True`, that
    preserves the legacy "no secret configured" pass-through.
    """
    try:
        payload_dict = json.loads(body) if body else {}
    except (ValueError, TypeError):
        return ResolvedSecret(secret=None, extras=None)

    assinatura_id = payload_dict.get("assinatura_id")
    if not assinatura_id:
        return ResolvedSecret(secret=None, extras=None)

    db = get_admin_client()
    if not db:
        return ResolvedSecret(secret=None, extras=None)

    res = (
        db.table("assinaturas")
        .select("org_id, provedor")
        .eq("id", assinatura_id)
        .execute()
    )
    if not res.data:
        return ResolvedSecret(secret=None, extras={"assinatura_id": assinatura_id, "org_id": None})

    org_id = res.data[0].get("org_id")
    if not org_id:
        return ResolvedSecret(secret=None, extras={"assinatura_id": assinatura_id, "org_id": None})

    # org_settings is the cross-product per-org per-key secret store; it
    # lives in core (see projects/keeper-trio-erp/PROJECT.md §7 Q1 + the
    # accept-with-rationale catalog). Use `db.schema("core")` so the
    # admin client reaches the canonical table rather than hitting the
    # phantom local `erp.org_settings`. The Wave 0 detector tuning
    # (40269c3) treats `.schema(X).table(Y)` chains as legitimate.
    secret_res = (
        db.schema("core")
        .table("org_settings")
        .select("value")
        .eq("org_id", org_id)
        .eq("key", "assinatura_webhook_secret")
        .execute()
    )
    webhook_secret = secret_res.data[0]["value"] if secret_res.data else None
    return ResolvedSecret(
        secret=webhook_secret,
        extras={"assinatura_id": assinatura_id, "org_id": org_id},
    )


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


class WebhookPayload(StrictHttpModel):
    assinatura_id: str = Field(..., description="ID da assinatura")
    evento: str = Field(..., min_length=1, max_length=100, description="Tipo do evento (ex: assinado, recusado, expirado)")
    dados: Optional[dict] = Field(default=None, description="Dados adicionais do evento")


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
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_assinatura_secret,
        scheme="sha256_prefixed",
        signature_header="X-Hub-Signature-256",
        bypass_when_unset=True,
        log_prefix="assinaturas-webhook",
    ),
    service: AssinaturaService = Depends(get_assinatura_service_webhook),
):
    """
    Callback endpoint for signing provider events.

    Unauthenticated — called directly by the signing provider (ClickSign,
    DocuSign, D4Sign, etc.). Signature verification runs in the
    `webhook_endpoint(...)` dependency before this body executes; on
    bypass (no secret configured for the org) the seed-lib helper logs
    a WARNING and lets the request through.
    """
    try:
        payload_dict = json.loads(verified.body) if verified.body else {}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    body = WebhookPayload.model_validate(payload_dict)

    updated = await service.processar_webhook(
        assinatura_id=body.assinatura_id,
        evento=body.evento,
        dados=body.dados,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Assinatura nao encontrada para o webhook")

    logger.info(f"Webhook processado: assinatura={body.assinatura_id}, evento={body.evento}")

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
