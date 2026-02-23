"""
Clientes CRUD Router — Manages clients, archiving, and pipeline moves.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clientes", tags=["Clientes"])


class ClienteCreate(BaseModel):
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    origem: Optional[str] = None
    interesse: Optional[str] = None
    observacoes: Optional[str] = None
    probabilidade: Optional[int] = None
    valor_estimado: Optional[float] = None


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    origem: Optional[str] = None
    interesse: Optional[str] = None
    observacoes: Optional[str] = None
    probabilidade: Optional[int] = None
    valor_estimado: Optional[float] = None
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
    authorization: Optional[str] = Header(None),
):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

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

    result = query.execute()
    data = result.data or []

    # Server-side search
    if busca:
        q = busca.lower()
        data = [c for c in data if any(
            q in str(c.get(f, "") or "").lower()
            for f in ["nome", "email", "telefone", "interesse", "observacoes"]
        )]

    return {"data": data, "total": len(data)}


@router.get("/{cliente_id}")
async def obter_cliente(cliente_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("clientes").select(
        "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
    ).eq("id", cliente_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"data": result.data}


@router.post("")
async def criar_cliente(body: ClienteCreate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["usuario_id"] = user.id

    result = db.table("clientes").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar cliente")

    log_action(user.id, "criar", "cliente", result.data["id"],
               f"Criou cliente {body.nome}")
    return {"data": result.data}


@router.patch("/{cliente_id}")
async def atualizar_cliente(cliente_id: str, body: ClienteUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("clientes").update(data).eq("id", cliente_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    log_action(user.id, "editar", "cliente", cliente_id, f"Editou cliente {cliente_id}")
    return {"data": result.data}


@router.delete("/{cliente_id}")
async def excluir_cliente(cliente_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    db.table("clientes").delete().eq("id", cliente_id).execute()
    log_action(user.id, "excluir", "cliente", cliente_id, f"Excluiu cliente {cliente_id}")
    return {"ok": True}


@router.post("/{cliente_id}/arquivar")
async def toggle_arquivar(cliente_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get current state
    current = db.table("clientes").select("arquivado, nome").eq("id", cliente_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    novo_estado = not current.data["arquivado"]
    result = db.table("clientes").update({"arquivado": novo_estado}).eq("id", cliente_id).select().single().execute()

    acao = "arquivar" if novo_estado else "desarquivar"
    log_action(user.id, acao, "cliente", cliente_id,
               f"{'Arquivou' if novo_estado else 'Desarquivou'} cliente {current.data['nome']}")
    return {"data": result.data}


@router.post("/{cliente_id}/mover-etapa")
async def mover_etapa(cliente_id: str, body: MoverEtapaRequest, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    valid_etapas = {"qualificacao", "visitas", "proposta", "negociacao", "fechado"}
    if body.para_etapa not in valid_etapas:
        raise HTTPException(status_code=400, detail=f"Etapa inválida. Use: {valid_etapas}")

    update_data = {"etapa_atual": body.para_etapa}
    if body.novo_indice is not None:
        update_data["kanban_pos"] = body.novo_indice

    result = db.table("clientes").update(update_data).eq("id", cliente_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    log_action(user.id, "mover", "cliente", cliente_id,
               f"Moveu cliente para etapa {body.para_etapa}",
               {"para_etapa": body.para_etapa, "motivo": body.motivo})
    return {"data": result.data}
