"""
Filiais (Multi-branch Management) API endpoints.

Manages organizational branches: CRUD, stats, and consolidated reporting.

-- CREATE TABLE filiais (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   nome text NOT NULL,
--   codigo text NOT NULL,
--   endereco text,
--   cidade text,
--   estado text,
--   telefone text,
--   responsavel_id uuid,
--   is_active boolean NOT NULL DEFAULT true,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- ALTER TABLE ativos ADD COLUMN filial_id uuid REFERENCES filiais(id);
-- ALTER TABLE clientes ADD COLUMN filial_id uuid REFERENCES filiais(id);
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/filiais", tags=["Filiais"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FilialCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    codigo: str = Field(..., min_length=1, max_length=20)
    endereco: Optional[str] = Field(default=None, max_length=500)
    cidade: Optional[str] = Field(default=None, max_length=100)
    estado: Optional[str] = Field(default=None, max_length=2)
    telefone: Optional[str] = Field(default=None, max_length=20)
    responsavel_id: Optional[str] = None


class FilialUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    codigo: Optional[str] = Field(default=None, min_length=1, max_length=20)
    endereco: Optional[str] = Field(default=None, max_length=500)
    cidade: Optional[str] = Field(default=None, max_length=100)
    estado: Optional[str] = Field(default=None, max_length=2)
    telefone: Optional[str] = Field(default=None, max_length=20)
    responsavel_id: Optional[str] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_filiais(
    is_active: Optional[bool] = Query(None, description="Filtrar por ativas/inativas"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """Lista todas as filiais da organização."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_query = db.table("filiais").select("id", count="exact")
    if is_active is not None:
        count_query = count_query.eq("is_active", is_active)
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query
    query = db.table("filiais").select("*").order("nome")
    if is_active is not None:
        query = query.eq("is_active", is_active)
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("")
async def criar_filial(body: FilialCreate, auth = Depends(get_current_user)):
    """Cria uma nova filial."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["is_active"] = True

    result = db.table("filiais").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar filial")

    log_action(user.id, "criar", "filial", row["id"],
               f"Criou filial '{body.nome}' (código: {body.codigo})")
    return success_response(row)


@router.get("/consolidado")
async def consolidado_filiais(auth = Depends(get_current_user)):
    """Retorna relatório consolidado com estatísticas de todas as filiais."""
    user, token = auth
    db = get_user_client(token)

    # Get all active branches
    filiais_result = db.table("filiais").select("*").eq("is_active", True).order("nome").execute()
    filiais = filiais_result.data or []

    filial_ids = [f["id"] for f in filiais]

    # Batch count: fetch filial_id for all ativos/clientes in 2 queries total
    imoveis_counts: dict[str, int] = {}
    clientes_counts: dict[str, int] = {}
    if filial_ids:
        imoveis_result = db.table("ativos").select(
            "filial_id"
        ).in_("filial_id", filial_ids).execute()
        for row in (imoveis_result.data or []):
            fid = row["filial_id"]
            imoveis_counts[fid] = imoveis_counts.get(fid, 0) + 1

        clientes_result = db.table("clientes").select(
            "filial_id"
        ).in_("filial_id", filial_ids).execute()
        for row in (clientes_result.data or []):
            fid = row["filial_id"]
            clientes_counts[fid] = clientes_counts.get(fid, 0) + 1

    consolidado = []
    totais = {"imoveis": 0, "clientes": 0, "filiais": len(filiais)}

    for filial in filiais:
        n_imoveis = imoveis_counts.get(filial["id"], 0)
        n_clientes = clientes_counts.get(filial["id"], 0)
        totais["imoveis"] += n_imoveis
        totais["clientes"] += n_clientes
        consolidado.append({
            **filial,
            "total_imoveis": n_imoveis,
            "total_clientes": n_clientes,
        })

    return success_response({
        "filiais": consolidado,
        "totais": totais,
    })


@router.get("/{filial_id}")
async def obter_filial(filial_id: str, auth = Depends(get_current_user)):
    """Retorna detalhes de uma filial com suas estatísticas."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("filiais").select("*").eq("id", filial_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Filial não encontrada")

    filial = result.data

    # Count properties
    imoveis_count = db.table("ativos").select("id", count="exact").eq(
        "filial_id", filial_id
    ).execute()
    filial["total_imoveis"] = imoveis_count.count if imoveis_count.count is not None else 0

    # Count clients
    clientes_count = db.table("clientes").select("id", count="exact").eq(
        "filial_id", filial_id
    ).execute()
    filial["total_clientes"] = clientes_count.count if clientes_count.count is not None else 0

    return success_response(filial)


@router.patch("/{filial_id}")
async def atualizar_filial(filial_id: str, body: FilialUpdate, auth = Depends(get_current_user)):
    """Atualiza informações de uma filial."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("filiais").update(data).eq("id", filial_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Filial não encontrada")

    log_action(user.id, "editar", "filial", filial_id, f"Atualizou filial {filial_id}")
    return success_response(row)


@router.delete("/{filial_id}")
async def desativar_filial(filial_id: str, auth = Depends(get_current_user)):
    """Desativa uma filial (soft delete)."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("filiais").update(
        {"is_active": False}
    ).eq("id", filial_id).execute()
    row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=404, detail="Filial não encontrada")

    log_action(user.id, "desativar", "filial", filial_id, f"Desativou filial {filial_id}")
    return ok_response("Filial desativada com sucesso")
