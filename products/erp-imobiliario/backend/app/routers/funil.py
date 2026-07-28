"""
Funil (Pipeline) Router — Kanban pipeline data.

RESHAPED (roadmap P1.5.4): cards are NEGOCIAÇÕES, not clientes.

A cliente can have several deals in flight at different stages, and
`erp.clientes.etapa_atual` holds exactly one stage — so grouping clientes by
that column could never show the second deal. Cards are now
`erp.negociacoes_venda` rows carrying their cliente as a nested join.

Behaviour guarantee: a cliente with exactly one deal (every row post-backfill)
renders identically to before. The reshape is only visible for multi-deal
clientes — which previously could not be represented at all.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query
from app.dependencies import get_current_user, get_user_client
from app.responses import success_response
from app.services.negociacoes_venda_service import (
    NEGOCIACAO_SELECT,
    STATUS_ABERTA,
    negociacao_row_to_dto,
    search_negociacoes,
)
from app.services.pipelines import PIPELINE_FUNIL
from noctusai_lib.domain.pipeline import group_into_colunas, list_stages

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/funil", tags=["Funil"])

# The stage vocabulary is no longer a constant anywhere: since migration 042 it
# is per-organization rows the user edits, read fresh on every board request.


@router.get("")
async def obter_funil(
    busca: Optional[str] = Query(None),
    responsavel_id: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    etapa_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth = Depends(get_current_user)):
    """
    Returns kanban columns with NEGOCIAÇÕES grouped by pipeline stage.
    All filtering and grouping done server-side.

    Columns are the caller org's configured stages — read per request, so a
    rename or reorder is visible on the next refresh with no deploy.
    """
    user, token = auth
    db = get_user_client(token)

    stages = list_stages(db, PIPELINE_FUNIL)

    query = db.table("negociacoes_venda").select(NEGOCIACAO_SELECT).order(
        "kanban_pos", desc=False
    )

    # Only OPEN deals are on the board. An accepted deal has moved to Processos
    # de Venda and a lost one is closed — both are retained for statistics, and
    # neither is still being worked.
    query = query.eq("status", STATUS_ABERTA)

    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa_id:
        query = query.eq("etapa_id", etapa_id)
    if responsavel_id and responsavel_id != "todos":
        query = query.eq("corretor_id", responsavel_id)

    negociacoes = query.execute().data or []

    # `origem` lives on the CLIENTE, not the deal, so it filters on the nested
    # join rather than a column of this table.
    if origem and origem != "todas":
        negociacoes = [
            n for n in negociacoes if (n.get("cliente") or {}).get("origem") == origem
        ]

    # Server-side search — across the deal title AND its cliente's identity.
    if busca:
        negociacoes = search_negociacoes(negociacoes, busca)

    return success_response(
        group_into_colunas(
            PIPELINE_FUNIL, stages, negociacoes, row_to_dto=negociacao_row_to_dto
        )
    )
