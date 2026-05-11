"""
Clientes CRUD Router — Manages clients, archiving, and pipeline moves.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field, EmailStr
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clientes", tags=["Clientes"])


class ClienteCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    telefone: Optional[str] = Field(default=None, max_length=20)
    origem: Optional[str] = None
    interesse: Optional[str] = None
    observacoes: Optional[str] = None
    probabilidade: Optional[int] = Field(default=None, ge=0, le=100)
    valor_estimado: Optional[float] = Field(default=None, ge=0)


class ClienteUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    telefone: Optional[str] = Field(default=None, max_length=20)
    origem: Optional[str] = None
    interesse: Optional[str] = None
    observacoes: Optional[str] = None
    probabilidade: Optional[int] = Field(default=None, ge=0, le=100)
    valor_estimado: Optional[float] = Field(default=None, ge=0)
    etapa_atual: Optional[str] = None


class MoverEtapaRequest(BaseModel):
    para_etapa: str
    motivo: Optional[str] = None
    novo_indice: Optional[int] = None


@router.get("")
async def listar_clientes(
    busca: Optional[str] = Query(None),
    responsavel_id: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    etapa: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    # Calculate pagination
    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build base query for counting
    count_query = db.table("clientes").select("id", count="exact")
    if not incluir_arquivados:
        count_query = count_query.eq("arquivado", False)
    if etapa:
        count_query = count_query.eq("etapa_atual", etapa)
    if origem and origem != "todas":
        count_query = count_query.eq("origem", origem)
    if responsavel_id and responsavel_id != "todos":
        count_query = count_query.eq("usuario_id", responsavel_id)
    if busca:
        count_query = count_query.or_(f"nome.ilike.%{busca}%,email.ilike.%{busca}%,telefone.ilike.%{busca}%")

    # Build data query with pagination
    query = db.table("clientes").select(
        "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
    ).order("created_at", desc=True)

    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa:
        query = query.eq("etapa_atual", etapa)
    if origem and origem != "todas":
        query = query.eq("origem", origem)
    if responsavel_id and responsavel_id != "todos":
        query = query.eq("usuario_id", responsavel_id)
    if busca:
        query = query.or_(f"nome.ilike.%{busca}%,email.ilike.%{busca}%,telefone.ilike.%{busca}%")

    # Apply pagination
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    # Get total count
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/{cliente_id}")
async def obter_cliente(cliente_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    result = db.table("clientes").select(
        "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
    ).eq("id", cliente_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_cliente(body: ClienteCreate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["usuario_id"] = user.id

    result = db.table("clientes").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar cliente")

    log_action(user.id, "criar", "cliente", row["id"],
               f"Criou cliente {body.nome}")
    return success_response(row)


@router.patch("/{cliente_id}")
async def atualizar_cliente(cliente_id: str, body: ClienteUpdate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("clientes").update(data).eq("id", cliente_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    log_action(user.id, "editar", "cliente", cliente_id, f"Editou cliente {cliente_id}")
    return success_response(row)


@router.delete("/{cliente_id}")
async def excluir_cliente(cliente_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "clientes", ("id", cliente_id), message = "Cliente não encontrado")
    log_action(user.id, "excluir", "cliente", cliente_id, f"Excluiu cliente {cliente_id}")
    return ok_response("Cliente excluído com sucesso")


@router.post("/{cliente_id}/arquivar")
async def toggle_arquivar(cliente_id: str, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    # Get current state
    current = db.table("clientes").select("arquivado, nome").eq("id", cliente_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    novo_estado = not current.data["arquivado"]
    result = db.table("clientes").update({"arquivado": novo_estado}).eq("id", cliente_id).execute()
    row = first_or_none(result)

    acao = "arquivar" if novo_estado else "desarquivar"
    log_action(user.id, acao, "cliente", cliente_id,
               f"{'Arquivou' if novo_estado else 'Desarquivou'} cliente {current.data['nome']}")
    return success_response(row)


@router.post("/{cliente_id}/mover-etapa")
async def mover_etapa(cliente_id: str, body: MoverEtapaRequest, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    valid_etapas = {"qualificacao", "visitas", "proposta", "negociacao", "fechado"}
    if body.para_etapa not in valid_etapas:
        raise HTTPException(status_code=400, detail=f"Etapa inválida. Use: {valid_etapas}")

    update_data = {"etapa_atual": body.para_etapa}
    if body.novo_indice is not None:
        update_data["kanban_pos"] = body.novo_indice

    result = db.table("clientes").update(update_data).eq("id", cliente_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    log_action(user.id, "mover", "cliente", cliente_id,
               f"Moveu cliente para etapa {body.para_etapa}",
               {"para_etapa": body.para_etapa, "motivo": body.motivo})
    return success_response(row)
