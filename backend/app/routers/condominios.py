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

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/condominios", tags=["Condominios"])


class CondominioCreate(BaseModel):
    nome: str
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    cep: Optional[str] = None
    valor_condominio: Optional[float] = None
    sindico: Optional[str] = None
    telefone_sindico: Optional[str] = None
    administradora: Optional[str] = None
    torres: Optional[int] = None
    unidades_por_andar: Optional[int] = None
    total_unidades: Optional[int] = None
    possui_portaria: bool = False
    possui_piscina: bool = False
    possui_academia: bool = False
    possui_salao_festas: bool = False
    possui_playground: bool = False
    possui_churrasqueira: bool = False
    observacoes: Optional[str] = None


class CondominioUpdate(BaseModel):
    nome: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    cep: Optional[str] = None
    valor_condominio: Optional[float] = None
    sindico: Optional[str] = None
    telefone_sindico: Optional[str] = None
    administradora: Optional[str] = None
    torres: Optional[int] = None
    unidades_por_andar: Optional[int] = None
    total_unidades: Optional[int] = None
    possui_portaria: Optional[bool] = None
    possui_piscina: Optional[bool] = None
    possui_academia: Optional[bool] = None
    possui_salao_festas: Optional[bool] = None
    possui_playground: Optional[bool] = None
    possui_churrasqueira: Optional[bool] = None
    observacoes: Optional[str] = None


async def _get_user_from_token(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    from app.database import get_supabase_client
    token = authorization.replace("Bearer ", "")
    client = get_supabase_client()
    try:
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


@router.get("")
async def listar_condominios(authorization: Optional[str] = Header(None)):
    user, token = await _get_user_from_token(authorization)
    from app.database import get_supabase_client
    client = get_supabase_client(token)
    res = client.table("condominios").select("*").order("nome").execute()
    return {"data": res.data or [], "total": len(res.data or [])}


@router.get("/{condominio_id}")
async def get_condominio(condominio_id: str, authorization: Optional[str] = Header(None)):
    _, token = await _get_user_from_token(authorization)
    from app.database import get_supabase_client
    client = get_supabase_client(token)
    res = client.table("condominios").select("*").eq("id", condominio_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Condomínio não encontrado")
    return {"data": res.data}


@router.post("")
async def criar_condominio(body: CondominioCreate, authorization: Optional[str] = Header(None)):
    user, token = await _get_user_from_token(authorization)
    from app.database import get_supabase_client
    client = get_supabase_client(token)
    data = body.model_dump(exclude_none=True)
    data["owner_id"] = user.id
    res = client.table("condominios").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Erro ao criar condomínio")
    return {"data": res.data[0]}


@router.patch("/{condominio_id}")
async def atualizar_condominio(condominio_id: str, body: CondominioUpdate, authorization: Optional[str] = Header(None)):
    _, token = await _get_user_from_token(authorization)
    from app.database import get_supabase_client
    client = get_supabase_client(token)
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    res = client.table("condominios").update(data).eq("id", condominio_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Condomínio não encontrado")
    return {"data": res.data[0]}


@router.delete("/{condominio_id}")
async def deletar_condominio(condominio_id: str, authorization: Optional[str] = Header(None)):
    _, token = await _get_user_from_token(authorization)
    from app.database import get_supabase_client
    client = get_supabase_client(token)
    client.table("condominios").delete().eq("id", condominio_id).execute()
    return {"ok": True}
