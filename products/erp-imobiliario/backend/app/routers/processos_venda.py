"""
Processos de Venda Router — the post-proposal execution board.

Deliberately has NO bare create endpoint: a processo is spawned by
`POST /api/negociacoes-venda/{id}/aceitar-proposta`. Creating one by hand would
produce an execution with no deal behind it.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import success_response
from app.services.processos_venda_service import (
    ETAPAS_PROCESSO,
    PROCESSO_SELECT,
    group_into_colunas,
    processo_row_to_dto,
    processo_rows_to_dto,
    search_processos,
)
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/processos-venda", tags=["Processos de Venda"])


class ProcessoUpdate(StrictHttpModel):
    corretor_id: Optional[str] = None
    etapa: Optional[str] = None
    valor: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = None
    arquivado: Optional[bool] = None


class MoverEtapaProcessoRequest(StrictHttpModel):
    para_etapa: str
    novo_indice: Optional[int] = None


def _validate_etapa(etapa: str) -> None:
    if etapa not in ETAPAS_PROCESSO:
        raise HTTPException(
            status_code=400,
            detail=f"Etapa inválida. Use uma de: {', '.join(ETAPAS_PROCESSO)}",
        )


@router.get("")
async def obter_board(
    busca: Optional[str] = Query(None),
    corretor_id: Optional[str] = Query(None),
    etapa: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth=Depends(get_current_user),
):
    """Kanban columns of processos grouped by execution stage.

    Returns all 8 columns always, so the board never loses a stage just
    because it happens to be empty.
    """
    _user, token = auth
    db = get_user_client(token)

    query = db.table("processos_venda").select(PROCESSO_SELECT).order(
        "kanban_pos", desc=False
    )
    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa:
        query = query.eq("etapa", etapa)
    if corretor_id and corretor_id != "todos":
        query = query.eq("corretor_id", corretor_id)

    rows = query.execute().data or []
    if busca:
        rows = search_processos(rows, busca)

    return success_response(group_into_colunas(rows))


@router.get("/lista")
async def listar_processos(
    incluir_arquivados: bool = Query(False),
    auth=Depends(get_current_user),
):
    """Flat list — for consumers that want rows rather than columns."""
    _user, token = auth
    db = get_user_client(token)

    query = db.table("processos_venda").select(PROCESSO_SELECT).order(
        "created_at", desc=True
    )
    if not incluir_arquivados:
        query = query.eq("arquivado", False)

    return success_response(processo_rows_to_dto(query.execute().data or []))


@router.get("/{processo_id}")
async def obter_processo(processo_id: str, auth=Depends(get_current_user)):
    _user, token = auth
    db = get_user_client(token)

    result = db.table("processos_venda").select(PROCESSO_SELECT).eq(
        "id", processo_id
    ).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return success_response(processo_row_to_dto(result.data))


@router.patch("/{processo_id}")
async def atualizar_processo(
    processo_id: str, body: ProcessoUpdate, auth=Depends(get_current_user)
):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    if "etapa" in data:
        _validate_etapa(data["etapa"])

    row = first_or_none(
        db.table("processos_venda").update(data).eq("id", processo_id).execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    log_action(user.id, "editar", "cliente", processo_id,
               f"Editou processo de venda {processo_id}")
    return success_response(processo_row_to_dto(row))


@router.post("/{processo_id}/mover-etapa")
async def mover_etapa(
    processo_id: str, body: MoverEtapaProcessoRequest, auth=Depends(get_current_user)
):
    user, token = auth
    db = get_user_client(token)

    _validate_etapa(body.para_etapa)

    current = db.table("processos_venda").select("id, etapa").eq(
        "id", processo_id
    ).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    de_etapa = current.data["etapa"]

    update_data = {"etapa": body.para_etapa}
    if body.novo_indice is not None:
        update_data["kanban_pos"] = body.novo_indice

    row = first_or_none(
        db.table("processos_venda").update(update_data).eq("id", processo_id).execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    log_action(
        user.id, "mover", "cliente", processo_id,
        f"Moveu processo para etapa {body.para_etapa}",
        {"de_etapa": de_etapa, "para_etapa": body.para_etapa},
    )
    return success_response(processo_row_to_dto(row))


@router.post("/{processo_id}/arquivar")
async def arquivar_processo(processo_id: str, auth=Depends(get_current_user)):
    """Toggle archive — how a finished processo leaves the terminal column.

    `nota_fiscal` is terminal, so without archiving the last column grows
    without bound and the board stops being readable.
    """
    user, token = auth
    db = get_user_client(token)

    current = db.table("processos_venda").select("id, arquivado").eq(
        "id", processo_id
    ).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    novo_estado = not current.data["arquivado"]
    row = first_or_none(
        db.table("processos_venda").update({"arquivado": novo_estado}).eq(
            "id", processo_id
        ).execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    log_action(
        user.id, "arquivar" if novo_estado else "desarquivar", "cliente", processo_id,
        f"{'Arquivou' if novo_estado else 'Desarquivou'} processo {processo_id}",
    )
    return success_response(processo_row_to_dto(row))
