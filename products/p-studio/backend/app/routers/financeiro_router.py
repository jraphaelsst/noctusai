"""Gestão financeira (spec § 7)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_current_user, get_provedor_cobranca
from app.providers.tipos import ProvedorCobranca
from app.schemas.financeiro import (
    STATUS_LABELS,
    CobrancaCreate,
    LancamentoBaixa,
    LancamentoCreate,
    LancamentoOut,
    LancamentoUpdate,
    ResumoFinanceiro,
)
from app.services.base import somente_preenchidos
from app.services.financeiro_service import FinanceiroService

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])


def _service(
    user: CurrentUser, provedor: Optional[ProvedorCobranca] = None
) -> FinanceiroService:
    """O provedor tem default para as rotas de leitura não mudarem — e para
    integração mal configurada não derrubar a tela inteira, só a emissão."""
    return FinanceiroService(user.db, user.org_id, provedor)


@router.get("/status")
def listar_status():
    return [{"id": k, "label": v} for k, v in STATUS_LABELS.items()]


@router.get("/resumo", response_model=ResumoFinanceiro)
def resumo(user: CurrentUser = Depends(get_current_user)):
    """Cabeçalho da tela: total, recebido, em aberto, atrasado, ticket médio."""
    return _service(user).resumo()


@router.get("/por-cliente")
def receita_por_cliente(user: CurrentUser = Depends(get_current_user)):
    return _service(user).receita_por_cliente()


@router.get("", response_model=list[LancamentoOut])
def listar(
    status: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
):
    """Lançamentos, opcionalmente filtrados pelo status exibido.

    O filtro roda sobre o status EXIBIDO, não o armazenado: quem pede
    `?status=atrasado` quer os vencidos, que no banco constam como `faturado`.
    """
    return _service(user).listar_completo(status)


@router.post("", response_model=LancamentoOut, status_code=201)
def criar(payload: LancamentoCreate, user: CurrentUser = Depends(get_current_user)):
    service = _service(user)
    lancamento = service.criar(payload.model_dump(mode="json"))
    return service.obter_completo(lancamento["id"])


@router.get("/{lancamento_id}", response_model=LancamentoOut)
def obter(lancamento_id: str, user: CurrentUser = Depends(get_current_user)):
    return _service(user).obter_completo(lancamento_id)


@router.patch("/{lancamento_id}", response_model=LancamentoOut)
def atualizar(
    lancamento_id: str,
    payload: LancamentoUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    service = _service(user)
    service.atualizar(lancamento_id, somente_preenchidos(payload))
    return service.obter_completo(lancamento_id)


@router.post("/{lancamento_id}/cobranca", response_model=LancamentoOut, status_code=201)
def emitir_cobranca(
    lancamento_id: str,
    payload: CobrancaCreate,
    user: CurrentUser = Depends(get_current_user),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Emite a cobrança no provedor e devolve o lançamento já com a fatura.

    201 mesmo quando reaproveita uma cobrança existente: a semântica é "existe
    uma cobrança para este lançamento", e distinguir criou/reaproveitou faria o
    cliente ter que tratar dois caminhos para o mesmo resultado.
    """
    return _service(user, provedor).emitir_cobranca(lancamento_id, payload.forma)


@router.post("/{lancamento_id}/sincronizar", response_model=LancamentoOut)
def sincronizar_cobranca(
    lancamento_id: str,
    user: CurrentUser = Depends(get_current_user),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Reconsulta o provedor. É o caminho que o Banco do Brasil vai usar —
    lá a conciliação é por consulta, não por webhook."""
    return _service(user, provedor).sincronizar_cobranca(lancamento_id)


@router.post("/{lancamento_id}/baixa", response_model=LancamentoOut)
def dar_baixa(
    lancamento_id: str,
    payload: LancamentoBaixa,
    user: CurrentUser = Depends(get_current_user),
):
    """Registra o recebimento. `pago_em` ausente = hoje."""
    return _service(user).dar_baixa(
        lancamento_id, payload.pago_em, payload.forma_pagamento
    )


@router.delete("/{lancamento_id}", status_code=204)
def excluir(lancamento_id: str, user: CurrentUser = Depends(get_current_user)):
    _service(user).excluir(lancamento_id)
    return None
