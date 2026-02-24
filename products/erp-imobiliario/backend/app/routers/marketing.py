"""
Marketing Automation Router — campaigns, sends, and interest-based alerts.

-- CREATE TABLE campanhas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   nome text NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('email', 'whatsapp', 'alerta_imovel')),
--   status text NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'ativa', 'pausada', 'concluida')),
--   template text NOT NULL,
--   filtros jsonb NOT NULL DEFAULT '{}',
--   total_enviados int NOT NULL DEFAULT 0,
--   total_abertos int NOT NULL DEFAULT 0,
--   total_cliques int NOT NULL DEFAULT 0,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE envios_email (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   campanha_id uuid NOT NULL REFERENCES campanhas(id),
--   cliente_id uuid NOT NULL,
--   email text NOT NULL,
--   status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'enviado', 'aberto', 'clicado', 'erro')),
--   enviado_at timestamptz,
--   aberto_at timestamptz,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.marketing_service import get_campaign_stats, process_alerts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CampanhaCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    tipo: Literal["email", "whatsapp", "alerta_imovel"]
    template: str = Field(..., min_length=1)
    filtros: dict = Field(default_factory=dict)
    status: Literal["rascunho", "ativa", "pausada", "concluida"] = "rascunho"


class CampanhaUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    tipo: Optional[Literal["email", "whatsapp", "alerta_imovel"]] = None
    template: Optional[str] = None
    filtros: Optional[dict] = None
    status: Optional[Literal["rascunho", "ativa", "pausada", "concluida"]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/campanhas")
async def listar_campanhas(
    status: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """List marketing campaigns with optional filters."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_query = db.table("campanhas").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    query = db.table("campanhas").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if tipo:
        query = query.eq("tipo", tipo)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    return paginated_response(data, total, validated_page, validated_page_size)


@router.post("/campanhas")
async def criar_campanha(body: CampanhaCreate, authorization: Optional[str] = Header(None)):
    """Create a new marketing campaign."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    payload = body.model_dump()
    result = db.table("campanhas").insert(payload).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar campanha")

    campanha = result.data
    log_action(user.id, "criar", "campanha", campanha["id"], f"Criou campanha '{body.nome}'")
    return success_response(campanha)


@router.get("/campanhas/{campanha_id}")
async def obter_campanha(campanha_id: str, authorization: Optional[str] = Header(None)):
    """Get a campaign with aggregated stats."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("campanhas").select("*").eq("id", campanha_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    campanha = result.data
    campanha["stats"] = get_campaign_stats(campanha_id, db)
    return success_response(campanha)


@router.patch("/campanhas/{campanha_id}")
async def atualizar_campanha(
    campanha_id: str, body: CampanhaUpdate, authorization: Optional[str] = Header(None)
):
    """Update a campaign."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("campanhas").update(data).eq("id", campanha_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    log_action(user.id, "editar", "campanha", campanha_id, f"Editou campanha {campanha_id}")
    return success_response(result.data)


@router.delete("/campanhas/{campanha_id}")
async def excluir_campanha(campanha_id: str, authorization: Optional[str] = Header(None)):
    """Delete a campaign and its sends."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Delete sends first (foreign key)
    db.table("envios_email").delete().eq("campanha_id", campanha_id).execute()
    db.table("campanhas").delete().eq("id", campanha_id).execute()

    log_action(user.id, "excluir", "campanha", campanha_id, f"Excluiu campanha {campanha_id}")
    return ok_response("Campanha excluída com sucesso")


@router.post("/campanhas/{campanha_id}/enviar")
async def enviar_campanha(campanha_id: str, authorization: Optional[str] = Header(None)):
    """
    Trigger campaign send.
    Creates envio_email records for matching clients based on campaign filters.
    Actual email delivery would be handled by an async worker/webhook.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Fetch campaign
    camp_result = db.table("campanhas").select("*").eq("id", campanha_id).single().execute()
    if not camp_result.data:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    campanha = camp_result.data
    if campanha["status"] not in ("rascunho", "ativa"):
        raise HTTPException(status_code=400, detail="Campanha não pode ser enviada neste status")

    # Fetch target clients based on filters
    filtros = campanha.get("filtros") or {}
    clientes_query = db.table("clientes").select("id, email, nome")
    if filtros.get("origem"):
        clientes_query = clientes_query.eq("origem", filtros["origem"])
    if filtros.get("etapa"):
        clientes_query = clientes_query.eq("etapa_atual", filtros["etapa"])

    clientes_result = clientes_query.execute()
    clientes = clientes_result.data or []

    # Filter only clients with email
    clientes_com_email = [c for c in clientes if c.get("email")]
    if not clientes_com_email:
        raise HTTPException(status_code=400, detail="Nenhum cliente com e-mail encontrado para os filtros")

    # Create send records
    envios = []
    for cliente in clientes_com_email:
        envios.append({
            "campanha_id": campanha_id,
            "cliente_id": cliente["id"],
            "email": cliente["email"],
            "status": "pendente",
        })

    if envios:
        db.table("envios_email").insert(envios).execute()

    # Update campaign status and count
    db.table("campanhas").update({
        "status": "ativa",
        "total_enviados": len(envios),
    }).eq("id", campanha_id).execute()

    log_action(
        user.id, "enviar", "campanha", campanha_id,
        f"Disparou campanha para {len(envios)} destinatários"
    )

    return success_response({
        "campanha_id": campanha_id,
        "total_destinatarios": len(envios),
        "mensagem": f"Campanha enviada para {len(envios)} destinatários",
    })


@router.get("/alertas")
async def processar_alertas(authorization: Optional[str] = Header(None)):
    """
    Process interest-based alerts — match new properties to client interests.
    Returns a list of matches that could be sent as alerts.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    org_id = user.user_metadata.get("org_id", "") if user.user_metadata else ""
    matches = process_alerts(org_id, db)

    return success_response(matches)
