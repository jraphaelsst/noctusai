"""
Vistorias (Property Inspections) Router — Manages inspection scheduling,
checklists, and photo documentation.

-- CREATE TABLE vistorias (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   imovel_id uuid NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('entrada', 'saida', 'periodica')),
--   data_vistoria date NOT NULL,
--   responsavel_id uuid NOT NULL,
--   responsavel_nome text,
--   status text NOT NULL DEFAULT 'agendada' CHECK (status IN ('agendada', 'em_andamento', 'concluida', 'cancelada')),
--   checklist jsonb NOT NULL DEFAULT '[]',
--   fotos text[] NOT NULL DEFAULT '{}',
--   observacoes_gerais text,
--   assinatura_locatario text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, List, Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.vistorias_service import (
    get_default_checklist,
    validate_checklist,
    summarise_checklist,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vistorias", tags=["Vistorias"])


# --------------- Schemas ---------------

class ChecklistItem(BaseModel):
    item: str
    estado: Literal["bom", "regular", "ruim", "NA"] = "bom"
    observacao: Optional[str] = ""


class VistoriaCreate(BaseModel):
    imovel_id: str
    tipo: Literal["entrada", "saida", "periodica"]
    data_vistoria: str = Field(..., description="Data da vistoria (YYYY-MM-DD)")
    responsavel_id: str
    responsavel_nome: Optional[str] = None
    checklist: Optional[List[ChecklistItem]] = None
    fotos: Optional[List[str]] = None
    observacoes_gerais: Optional[str] = None


class VistoriaUpdate(BaseModel):
    tipo: Optional[Literal["entrada", "saida", "periodica"]] = None
    data_vistoria: Optional[str] = None
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = None
    status: Optional[Literal["agendada", "em_andamento", "concluida", "cancelada"]] = None
    checklist: Optional[List[ChecklistItem]] = None
    fotos: Optional[List[str]] = None
    observacoes_gerais: Optional[str] = None
    assinatura_locatario: Optional[str] = None


class FotosRequest(BaseModel):
    urls: List[str] = Field(..., min_length=1, description="Lista de URLs de fotos")


# --------------- Endpoints ---------------

@router.get("")
async def listar_vistorias(
    imovel_id: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """List inspections with optional filters."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_query = db.table("vistorias").select("id", count="exact")
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if status:
        count_query = count_query.eq("status", status)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    query = db.table("vistorias").select("*").order("data_vistoria", desc=True)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if tipo:
        query = query.eq("tipo", tipo)
    if status:
        query = query.eq("status", status)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("")
async def criar_vistoria(body: VistoriaCreate, authorization: Optional[str] = Header(None)):
    """Create a new property inspection."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)

    # Use default checklist if none provided
    if "checklist" not in data or not data["checklist"]:
        data["checklist"] = get_default_checklist()
    else:
        data["checklist"] = validate_checklist(
            [item if isinstance(item, dict) else item.model_dump() for item in data["checklist"]]
        )

    if "fotos" not in data:
        data["fotos"] = []

    result = db.table("vistorias").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar vistoria")

    log_action(user.id, "criar", "vistoria", result.data["id"],
               f"Criou vistoria {body.tipo} para imóvel {body.imovel_id}")
    return success_response(result.data)


@router.get("/template-checklist")
async def obter_template_checklist(authorization: Optional[str] = Header(None)):
    """Return the default checklist template."""
    await get_current_user(authorization)
    return success_response(get_default_checklist())


@router.get("/{vistoria_id}")
async def obter_vistoria(vistoria_id: str, authorization: Optional[str] = Header(None)):
    """Get a single inspection by ID, including checklist summary."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("vistorias").select("*").eq("id", vistoria_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Vistoria não encontrada")

    vistoria = result.data
    vistoria["resumo_checklist"] = summarise_checklist(vistoria.get("checklist") or [])

    return success_response(vistoria)


@router.patch("/{vistoria_id}")
async def atualizar_vistoria(
    vistoria_id: str,
    body: VistoriaUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update an inspection (status, checklist, photos, etc.)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Validate checklist if provided
    if "checklist" in data and data["checklist"]:
        data["checklist"] = validate_checklist(
            [item if isinstance(item, dict) else item.model_dump() for item in data["checklist"]]
        )

    result = db.table("vistorias").update(data).eq(
        "id", vistoria_id
    ).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Vistoria não encontrada")

    log_action(user.id, "editar", "vistoria", vistoria_id,
               f"Atualizou vistoria {vistoria_id}")
    return success_response(result.data)


@router.delete("/{vistoria_id}")
async def excluir_vistoria(vistoria_id: str, authorization: Optional[str] = Header(None)):
    """Delete an inspection."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("vistorias").delete().eq("id", vistoria_id).execute()
    log_action(user.id, "excluir", "vistoria", vistoria_id,
               f"Excluiu vistoria {vistoria_id}")
    return ok_response("Vistoria excluída com sucesso")


@router.post("/{vistoria_id}/fotos")
async def adicionar_fotos(
    vistoria_id: str,
    body: FotosRequest,
    authorization: Optional[str] = Header(None),
):
    """Add photos to an existing inspection (appends to existing array)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get current photos
    current = db.table("vistorias").select("fotos").eq(
        "id", vistoria_id
    ).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Vistoria não encontrada")

    existing_fotos = current.data.get("fotos") or []
    updated_fotos = existing_fotos + body.urls

    result = db.table("vistorias").update({
        "fotos": updated_fotos,
    }).eq("id", vistoria_id).select().single().execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao adicionar fotos")

    log_action(user.id, "editar", "vistoria", vistoria_id,
               f"Adicionou {len(body.urls)} foto(s) à vistoria {vistoria_id}")
    return success_response(result.data)
