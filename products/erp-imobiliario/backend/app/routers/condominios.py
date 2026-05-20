"""
Condominios API endpoints.

GET    /api/condominios       — List condominios
GET    /api/condominios/{id}  — Get by ID
POST   /api/condominios       — Create
PATCH  /api/condominios/{id}  — Update
DELETE /api/condominios/{id}  — Delete
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import Field

from app.dependencies import get_current_user, get_user_client
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/condominios", tags=["Condominios"])


class CondominioCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=255)
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = Field(default=None, max_length=2)
    cep: Optional[str] = Field(default=None, max_length=9)
    valor_condominio: Optional[float] = Field(default=None, ge=0)
    sindico: Optional[str] = None
    telefone_sindico: Optional[str] = Field(default=None, max_length=20)
    administradora: Optional[str] = None
    torres: Optional[int] = Field(default=None, ge=0)
    unidades_por_andar: Optional[int] = Field(default=None, ge=0)
    total_unidades: Optional[int] = Field(default=None, ge=0)
    possui_portaria: bool = False
    possui_piscina: bool = False
    possui_academia: bool = False
    possui_salao_festas: bool = False
    possui_playground: bool = False
    possui_churrasqueira: bool = False
    observacoes: Optional[str] = None


class CondominioUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = Field(default=None, max_length=2)
    cep: Optional[str] = Field(default=None, max_length=9)
    valor_condominio: Optional[float] = Field(default=None, ge=0)
    sindico: Optional[str] = None
    telefone_sindico: Optional[str] = Field(default=None, max_length=20)
    administradora: Optional[str] = None
    torres: Optional[int] = Field(default=None, ge=0)
    unidades_por_andar: Optional[int] = Field(default=None, ge=0)
    total_unidades: Optional[int] = Field(default=None, ge=0)
    possui_portaria: Optional[bool] = None
    possui_piscina: Optional[bool] = None
    possui_academia: Optional[bool] = None
    possui_salao_festas: Optional[bool] = None
    possui_playground: Optional[bool] = None
    possui_churrasqueira: Optional[bool] = None
    observacoes: Optional[str] = None


@router.get("")
async def listar_condominios(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    # Calculate pagination
    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count query
    count_result = db.table("condominios").select("id", count="exact").execute()
    total = count_result.count if count_result.count is not None else 0

    # Data query with pagination
    res = db.table("condominios").select("*").order("nome").range(
        offset, offset + validated_page_size - 1
    ).execute()

    return paginated_response(res.data or [], total, validated_page, validated_page_size)


@router.get("/{condominio_id}")
async def get_condominio(condominio_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    res = db.table("condominios").select("*").eq("id", condominio_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Condomínio não encontrado")
    return success_response(res.data)


@router.post("")
async def criar_condominio(body: CondominioCreate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["owner_id"] = user.id

    res = db.table("condominios").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar condomínio")
    return success_response(res.data[0])


@router.patch("/{condominio_id}")
async def atualizar_condominio(condominio_id: str, body: CondominioUpdate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    res = db.table("condominios").update(data).eq("id", condominio_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Condomínio não encontrado")
    return success_response(res.data[0])


@router.delete("/{condominio_id}")
async def deletar_condominio(condominio_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "condominios", ("id", condominio_id), message="Condomínio não encontrado")
    return ok_response("Condomínio excluído com sucesso")
