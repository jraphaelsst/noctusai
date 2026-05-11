"""
Emails CRUD Router — CRM email sending, templates, and tracking.

-- CREATE TABLE emails (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   cliente_id uuid,
--   remetente text NOT NULL,
--   destinatario text NOT NULL,
--   assunto text NOT NULL,
--   corpo text NOT NULL,
--   corpo_html text,
--   direcao text NOT NULL CHECK (direcao IN ('enviado', 'recebido')),
--   status text NOT NULL DEFAULT 'enviado' CHECK (status IN ('rascunho', 'enviado', 'entregue', 'aberto', 'erro')),
--   template_id uuid,
--   aberturas integer NOT NULL DEFAULT 0,
--   cliques integer NOT NULL DEFAULT 0,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE email_templates (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   nome text NOT NULL,
--   assunto text NOT NULL,
--   corpo text NOT NULL,
--   variaveis text[] NOT NULL DEFAULT '{}',
--   ativo boolean NOT NULL DEFAULT true,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, List
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, get_org_id, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.email_service import EmailService
from app.config import settings
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emails", tags=["Emails"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class EnviarEmailRequest(BaseModel):
    destinatario: str = Field(..., min_length=1, max_length=255)
    assunto: str = Field(..., min_length=1, max_length=500)
    corpo: str = Field(..., min_length=1)
    cliente_id: Optional[str] = None
    template_id: Optional[str] = None


class TemplateCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    assunto: str = Field(..., min_length=1, max_length=500)
    corpo: str = Field(..., min_length=1)
    variaveis: List[str] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    assunto: Optional[str] = Field(default=None, min_length=1, max_length=500)
    corpo: Optional[str] = Field(default=None, min_length=1)
    variaveis: Optional[List[str]] = None
    ativo: Optional[bool] = None


# ---------------------------------------------------------------------------
# Email endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_emails(
    cliente_id: Optional[str] = Query(None),
    direcao: Optional[Literal["enviado", "recebido"]] = Query(None),
    status: Optional[Literal["rascunho", "enviado", "entregue", "aberto", "erro"]] = Query(None),
    data_inicio: Optional[str] = Query(None, description="ISO date lower bound (inclusive)"),
    data_fim: Optional[str] = Query(None, description="ISO date upper bound (inclusive)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("emails").select("id", count="exact")
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)
    if direcao:
        count_query = count_query.eq("direcao", direcao)
    if status:
        count_query = count_query.eq("status", status)
    if data_inicio:
        count_query = count_query.gte("created_at", data_inicio)
    if data_fim:
        count_query = count_query.lte("created_at", data_fim)

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("emails").select("*").order("created_at", desc=True)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)
    if direcao:
        query = query.eq("direcao", direcao)
    if status:
        query = query.eq("status", status)
    if data_inicio:
        query = query.gte("created_at", data_inicio)
    if data_fim:
        query = query.lte("created_at", data_fim)

    query = query.range(offset, offset + validated_page_size - 1)
    result = query.execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)


@router.post("/enviar")
async def enviar_email(body: EnviarEmailRequest, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    svc = EmailService(db, user.id, org_id=get_org_id(user))

    # If a template was referenced, render it first
    corpo = body.corpo
    corpo_html = None
    if body.template_id:
        rendered = svc.aplicar_template(body.template_id, {})
        if rendered:
            corpo_html = rendered["corpo"]

    email_record = await svc.enviar(
        destinatario=body.destinatario,
        assunto=body.assunto,
        corpo=corpo,
        cliente_id=body.cliente_id,
        corpo_html=corpo_html,
        template_id=body.template_id,
    )

    if not email_record:
        raise HTTPException(status_code=500, detail="Erro ao registrar email")

    log_action(
        user.id, "enviar", "email", email_record["id"],
        f"Enviou email para {body.destinatario}",
    )
    return success_response(email_record)


# ---------------------------------------------------------------------------
# Template endpoints
# ---------------------------------------------------------------------------

@router.get("/templates")
async def listar_templates(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    count_result = db.table("email_templates").select("id", count="exact").eq(
        "ativo", True
    ).execute()
    total = count_result.count if count_result.count is not None else 0

    result = db.table("email_templates").select("*").eq(
        "ativo", True
    ).order("created_at", desc=True).range(
        offset, offset + validated_page_size - 1
    ).execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/templates/{template_id}")
async def obter_template(template_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    result = db.table("email_templates").select("*").eq("id", template_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return success_response(result.data)


@router.post("/templates")
async def criar_template(body: TemplateCreate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump()
    result = db.table("email_templates").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar template")

    log_action(
        user.id, "criar", "email_template", row["id"],
        f"Criou template de email '{body.nome}'",
    )
    return success_response(row)


@router.patch("/templates/{template_id}")
async def atualizar_template(
    template_id: str, body: TemplateUpdate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("email_templates").update(data).eq(
        "id", template_id
    ).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    log_action(
        user.id, "editar", "email_template", template_id,
        f"Editou template de email {template_id}",
    )
    return success_response(row)


@router.delete("/templates/{template_id}")
async def excluir_template(template_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "email_templates", ("id", template_id), message = "Template não encontrado")

    log_action(
        user.id, "excluir", "email_template", template_id,
        f"Excluiu template de email {template_id}",
    )
    return ok_response("Template excluído com sucesso")


# ---------------------------------------------------------------------------
# Single email lookup (must come AFTER /templates, /enviar to avoid catch-all)
# ---------------------------------------------------------------------------

@router.get("/{email_id}")
async def obter_email(email_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    result = db.table("emails").select("*").eq("id", email_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    return success_response(result.data)
