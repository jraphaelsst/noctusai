"""
Funil (Pipeline) Router — Kanban pipeline data.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, Query
from app.dependencies import get_current_user, get_user_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/funil", tags=["Funil"])

ETAPAS = ["qualificacao", "visitas", "proposta", "negociacao", "fechado"]


@router.get("")
async def obter_funil(
    busca: Optional[str] = Query(None),
    responsavel_id: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    etapa: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    authorization: Optional[str] = Header(None),
):
    """
    Returns kanban columns with clients grouped by pipeline stage.
    All filtering and grouping done server-side.
    """
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    query = db.table("clientes").select(
        "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
    ).order("kanban_pos", desc=False)

    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa:
        query = query.eq("etapa_atual", etapa)
    if origem and origem != "todas":
        query = query.eq("origem", origem)
    if responsavel_id and responsavel_id != "todos":
        query = query.eq("usuario_id", responsavel_id)

    result = query.execute()
    clientes = result.data or []

    # Server-side search
    if busca:
        q = busca.lower()
        clientes = [c for c in clientes if any(
            q in str(c.get(f, "") or "").lower()
            for f in ["nome", "email", "telefone"]
        )]

    # Group by etapa (server-side)
    colunas = []
    for etapa_name in ETAPAS:
        cards = [c for c in clientes if c.get("etapa_atual") == etapa_name]
        cards.sort(key=lambda c: c.get("kanban_pos", 0))
        colunas.append({
            "etapa": etapa_name,
            "total": len(cards),
            "valorTotal": sum(float(c.get("valor_estimado", 0) or 0) for c in cards),
            "cards": cards,
        })

    return {"data": colunas}
