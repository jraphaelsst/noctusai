"""Agenda operacional — captações e checklist de equipamentos (spec § 3)."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_current_user
from app.schemas.captacoes import (
    CaptacaoCreate,
    CaptacaoOut,
    CaptacaoUpdate,
    ChecklistUpdate,
)
from app.services.base import somente_preenchidos
from app.services.captacoes_service import CaptacoesService

router = APIRouter(prefix="/api/captacoes", tags=["captacoes"])


def _service(user: CurrentUser) -> CaptacoesService:
    return CaptacoesService(user.db, user.org_id)


@router.get("", response_model=list[CaptacaoOut])
def listar(
    inicio: Optional[date] = Query(default=None),
    fim: Optional[date] = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    """Captações do período. Sem filtro devolve a agenda inteira — as visões
    de dia/semana/mês da tela passam o intervalo correspondente."""
    return _service(user).listar_periodo(inicio, fim)


@router.post("", response_model=CaptacaoOut, status_code=201)
def criar(payload: CaptacaoCreate, user: CurrentUser = Depends(get_current_user)):
    dados = payload.model_dump(mode="json")
    equipamento_ids = dados.pop("equipamento_ids", [])
    return _service(user).criar_com_checklist(dados, equipamento_ids)


@router.get("/{captacao_id}", response_model=CaptacaoOut)
def obter(captacao_id: str, user: CurrentUser = Depends(get_current_user)):
    return _service(user).obter_completo(captacao_id)


@router.patch("/{captacao_id}", response_model=CaptacaoOut)
def atualizar(
    captacao_id: str,
    payload: CaptacaoUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    changes = somente_preenchidos(payload)
    equipamento_ids = changes.pop("equipamento_ids", None)
    return _service(user).atualizar_com_checklist(captacao_id, changes, equipamento_ids)


@router.patch("/checklist/{item_id}")
def marcar_item(
    item_id: str,
    payload: ChecklistUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """Confere um item do checklist antes de sair do estúdio."""
    return _service(user).marcar_item(item_id, payload.conferido)


@router.delete("/{captacao_id}", status_code=204)
def excluir(captacao_id: str, user: CurrentUser = Depends(get_current_user)):
    _service(user).excluir(captacao_id)
    return None
