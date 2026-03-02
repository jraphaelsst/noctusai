"""
Portal do Cliente CRUD Router — Client portal access and support ticket management.

Provides both admin-side endpoints (authenticated) for managing portal access
and client-facing endpoints (token-based, no Bearer auth) for client self-service.

-- CREATE TABLE portal_acessos (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   cliente_id uuid NOT NULL,
--   token text NOT NULL UNIQUE,
--   ativo boolean NOT NULL DEFAULT true,
--   data_expiracao timestamptz,
--   ultimo_acesso timestamptz,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE chamados_portal (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   cliente_id uuid NOT NULL,
--   portal_acesso_id uuid NOT NULL REFERENCES portal_acessos(id),
--   assunto text NOT NULL,
--   descricao text NOT NULL,
--   status text NOT NULL DEFAULT 'aberto' CHECK (status IN ('aberto', 'em_andamento', 'resolvido', 'fechado')),
--   prioridade text NOT NULL DEFAULT 'media' CHECK (prioridade IN ('baixa', 'media', 'alta', 'urgente')),
--   resposta text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.portal_cliente_service import PortalClienteService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portal-cliente", tags=["Portal do Cliente"])


# --- Pydantic models ---

class GerarAcessoRequest(BaseModel):
    cliente_id: str = Field(..., description="ID do cliente para gerar acesso")
    data_expiracao: Optional[str] = Field(
        default=None,
        description="Data de expiração do acesso (ISO 8601). Se não informado, acesso não expira.",
    )


class ChamadoCreate(BaseModel):
    assunto: str = Field(..., min_length=1, max_length=255, description="Assunto do chamado")
    descricao: str = Field(..., min_length=1, max_length=2000, description="Descrição detalhada")
    prioridade: Optional[str] = Field(
        default="media",
        pattern="^(baixa|media|alta|urgente)$",
        description="Prioridade: baixa, media, alta, urgente",
    )


class ChamadoUpdate(BaseModel):
    status: Optional[str] = Field(
        default=None,
        pattern="^(aberto|em_andamento|resolvido|fechado)$",
        description="Status: aberto, em_andamento, resolvido, fechado",
    )
    resposta: Optional[str] = Field(default=None, max_length=2000, description="Resposta ao chamado")


# ---------------------------------------------------------------------------
# Admin-side endpoints (require Bearer auth)
# ---------------------------------------------------------------------------

@router.post("/gerar-acesso")
async def gerar_acesso(body: GerarAcessoRequest, authorization: Optional[str] = Header(None)):
    """Gera um token de acesso ao portal para um cliente. Requer autenticação."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    service = PortalClienteService(db, user.id)
    portal_token = service.gerar_token()

    data = {
        "cliente_id": body.cliente_id,
        "token": portal_token,
        "ativo": True,
    }
    if body.data_expiracao:
        data["data_expiracao"] = body.data_expiracao

    result = db.table("portal_acessos").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao gerar acesso ao portal")

    log_action(user.id, "criar", "portal_acesso", row["id"],
               f"Gerou acesso ao portal para cliente {body.cliente_id}")

    return success_response({
        **row,
        "link": f"/portal-cliente/{portal_token}",
    })


@router.get("/acessos")
async def listar_acessos(
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """Lista acessos ativos ao portal com paginação. Requer autenticação."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("portal_acessos").select("id", count="exact").eq("ativo", True)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)

    # Build data query
    query = db.table("portal_acessos").select("*").eq("ativo", True).order("created_at", desc=True)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.delete("/acessos/{acesso_id}")
async def revogar_acesso(acesso_id: str, authorization: Optional[str] = Header(None)):
    """Revoga (desativa) um acesso ao portal. Requer autenticação."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("portal_acessos").update(
        {"ativo": False}
    ).eq("id", acesso_id).execute()
    row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=404, detail="Acesso não encontrado")

    log_action(user.id, "revogar", "portal_acesso", acesso_id,
               f"Revogou acesso ao portal {acesso_id}")

    return ok_response("Acesso ao portal revogado com sucesso")


@router.get("/chamados")
async def listar_chamados(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    authorization: Optional[str] = Header(None),
):
    """Lista todos os chamados do portal com filtros e paginação. Requer autenticação."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("chamados_portal").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)

    # Build data query
    query = db.table("chamados_portal").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.patch("/chamados/{chamado_id}")
async def atualizar_chamado(
    chamado_id: str,
    body: ChamadoUpdate,
    authorization: Optional[str] = Header(None),
):
    """Atualiza um chamado (status e/ou resposta). Requer autenticação."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("chamados_portal").update(data).eq("id", chamado_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    log_action(user.id, "editar", "chamado_portal", chamado_id,
               f"Atualizou chamado {chamado_id}")

    return success_response(row)


# ---------------------------------------------------------------------------
# Client-facing endpoints (token-based, NO Bearer auth required)
# ---------------------------------------------------------------------------

@router.get("/{token}/dashboard")
async def portal_dashboard(token: str):
    """Retorna o dashboard do cliente: contratos, pagamentos recentes e documentos."""
    service = PortalClienteService.__from_token__(token)
    acesso = service.validar_token(token)

    cliente_id = acesso["cliente_id"]
    dashboard = service.get_dashboard(cliente_id)

    return success_response(dashboard)


@router.get("/{token}/financeiro")
async def portal_financeiro(token: str):
    """Retorna a visão financeira do cliente (lançamentos vinculados)."""
    service = PortalClienteService.__from_token__(token)
    acesso = service.validar_token(token)

    cliente_id = acesso["cliente_id"]
    financeiro = service.get_financeiro(cliente_id)

    return success_response(financeiro)


@router.get("/{token}/chamados")
async def portal_listar_chamados(token: str):
    """Retorna os chamados de suporte do cliente."""
    service = PortalClienteService.__from_token__(token)
    acesso = service.validar_token(token)

    cliente_id = acesso["cliente_id"]
    portal_acesso_id = acesso["id"]
    chamados = service.get_chamados(cliente_id, portal_acesso_id)

    return success_response(chamados)


@router.post("/{token}/chamados")
async def portal_criar_chamado(token: str, body: ChamadoCreate):
    """Abre um chamado de suporte pelo portal do cliente."""
    service = PortalClienteService.__from_token__(token)
    acesso = service.validar_token(token)

    cliente_id = acesso["cliente_id"]
    portal_acesso_id = acesso["id"]
    org_id = acesso["org_id"]

    data = {
        "org_id": org_id,
        "cliente_id": cliente_id,
        "portal_acesso_id": portal_acesso_id,
        "assunto": body.assunto,
        "descricao": body.descricao,
        "prioridade": body.prioridade or "media",
        "status": "aberto",
    }

    result = service.db.table("chamados_portal").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar chamado")

    return success_response(row)
