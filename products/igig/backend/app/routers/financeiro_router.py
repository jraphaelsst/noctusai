"""Financeiro e Gestão de Contratos — Módulo 6.

  FATURAS      /api/financeiro/faturas …              CRUD + lines + mark paid
  FECHAMENTO   /api/financeiro/faturas/gerar-competencia   monthly close, idempotent
  RESUMO       /api/financeiro/resumo                 a receber/recebido/inadimplente/MRR
  EXCEDENTES   /api/financeiro/excedentes/{comp}      delivered vs contracted
  DRE          /api/financeiro/dre                    revenue vs real hour-cost
  COBRANÇA     /api/financeiro/inadimplentes          overdue, with days late

**What is real vs pending.** Invoicing, line items, totals, excedente
computation, the DRE and the overdue report are all real and tested. The
payment GATEWAY (Asaas/Iugu) and NFS-e issuance are not — those need
credentials and municipal homologation, so `gateway_id`/`nfse_id` stay null
and no endpoint pretends to charge anyone.

The dunning sequence and the Módulo 4 portal block read
`/inadimplentes` rather than being triggered here: blocking a client's
approval portal is a business decision, not a side effect of running a report.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.persistence import PersistenceError, RecordNotFound

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.financeiro import (
    DREOut,
    ExcedenteOut,
    FaturaCreate,
    FaturaItemCreate,
    FaturaItemOut,
    FaturaOut,
    GerarCompetenciaIn,
    GerarCompetenciaOut,
    InadimplenteOut,
    ResumoFinanceiroOut,
)
from app.services.financeiro_service import FinanceiroService
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])

#: Statuses an invoice cannot add lines to.
_FATURA_FECHADA = frozenset({"paga", "cancelada"})


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


# ── Faturas ─────────────────────────────────────────────────────────
@router.get("/faturas", response_model=list[FaturaOut])
async def listar_faturas(
    cliente_id: str | None = None,
    competencia: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[FaturaOut]:
    org_id = _org(auth)
    if cliente_id:
        linhas = repos.fatura.do_cliente(org_id, cliente_id)
    elif competencia:
        linhas = repos.fatura.da_competencia(org_id, competencia)
    else:
        linhas = repos.fatura.listar(org_id)
    return [FaturaOut(**f) for f in linhas]


@router.post("/faturas", response_model=FaturaOut, status_code=status.HTTP_201_CREATED)
async def criar_fatura(
    payload: FaturaCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Open an invoice for a contract's month.

    A second invoice for the same contract+competência is a 409, enforced by a
    unique index: re-running the monthly close must be idempotent, not a way
    to double-bill a client.
    """
    org_id = _org(auth)
    try:
        repos.cliente.buscar(org_id, payload.cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    try:
        registro = repos.fatura.criar(org_id, payload.model_dump(exclude_none=True))
    except PersistenceError:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe fatura para este contrato em {payload.competencia}",
        )
    return FaturaOut(**registro)


@router.get("/faturas/{fatura_id}/itens", response_model=list[FaturaItemOut])
async def listar_itens(
    fatura_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[FaturaItemOut]:
    return [FaturaItemOut(**i) for i in repos.fatura_item.da_fatura(_org(auth), fatura_id)]


@router.post("/faturas/{fatura_id}/itens", response_model=FaturaOut,
             status_code=status.HTTP_201_CREATED)
async def adicionar_item(
    fatura_id: str,
    payload: FaturaItemCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Add a line and RETURN THE INVOICE, with its total recomputed.

    Returning the invoice rather than the line means a caller cannot end up
    holding a stale total — the number the client will see is the one that
    comes back.

    A `paga`/`cancelada` invoice is closed: adding a line to it would change
    a number a client already paid (or that was voided), silently.
    """
    org_id = _org(auth)
    try:
        fatura = repos.fatura.buscar(org_id, fatura_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.get("status") in _FATURA_FECHADA:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": f"Fatura {fatura['status']} não aceita novos itens.",
                "code": "fatura_fechada",
            },
        )
    repos.fatura_item.criar(org_id, {"fatura_id": fatura_id, **payload.model_dump()})
    itens = repos.fatura_item.da_fatura(org_id, fatura_id)
    return FaturaOut(**repos.fatura.recalcular_total(org_id, fatura_id, itens))


@router.post("/faturas/{fatura_id}/pagar", response_model=FaturaOut)
async def marcar_paga(
    fatura_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Mark an invoice paid.

    Manual today: the gateway webhook that will do this automatically needs
    credentials that do not exist yet. An explicit endpoint beats a fake
    integration that silently marks things paid.
    """
    org_id = _org(auth)
    try:
        return FaturaOut(**repos.fatura.marcar_paga(org_id, fatura_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")


@router.post("/faturas/gerar-competencia", response_model=GerarCompetenciaOut,
             status_code=status.HTTP_200_OK)
async def gerar_competencia(
    payload: GerarCompetenciaIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> GerarCompetenciaOut:
    """Close the month: open an invoice for every active contract at once.

    Safe to re-run — a contract that already has an invoice for this
    competência comes back under `existentes`, never billed twice. See
    `FinanceiroService.gerar_faturas_da_competencia`.
    """
    org_id = _org(auth)
    try:
        resultado = FinanceiroService(repos).gerar_faturas_da_competencia(
            org_id, payload.competencia
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GerarCompetenciaOut(
        criadas=[FaturaOut(**f) for f in resultado["criadas"]],
        existentes=[FaturaOut(**f) for f in resultado["existentes"]],
    )


@router.get("/resumo", response_model=ResumoFinanceiroOut)
async def resumo(
    competencia: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ResumoFinanceiroOut:
    """A receber, recebido, inadimplente e MRR — o retrato financeiro atual.

    `competencia` scopes a_receber/recebido/inadimplente; MRR is always the
    current active book (see `FinanceiroService.resumo`).
    """
    resultado = FinanceiroService(repos).resumo(_org(auth), competencia)
    return ResumoFinanceiroOut(**asdict(resultado))


# ── Excedentes ──────────────────────────────────────────────────────
@router.get("/excedentes/{competencia}", response_model=list[ExcedenteOut])
async def excedentes(
    competencia: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[ExcedenteOut]:
    """Delivered vs contracted for a month, with the charge and WHERE it lands.

    `competencia_cobranca` is the month AFTER the work, per the spec — billing
    it in the same month would invoice work before the retainer for it.
    """
    try:
        linhas = FinanceiroService(repos).excedentes(_org(auth), competencia)
    except ValueError as exc:
        # A malformed month is the caller's error, not a server fault.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # asdict(), not vars(): these are slots=True dataclasses and have no __dict__.
    return [ExcedenteOut(**asdict(e)) for e in linhas]


# ── DRE ─────────────────────────────────────────────────────────────
@router.get("/dre", response_model=list[DREOut])
async def dre(
    competencia: str | None = Query(default=None, description="Filtra a RECEITA"),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[DREOut]:
    """Revenue vs real hour-cost, per client.

    Cost comes from the same `BIService` the Módulo 5 screen uses, so the two
    can never disagree about a client. `alertas` warns when the margin is
    OVERSTATED because some hours could not be costed.
    """
    linhas = FinanceiroService(repos).dre(_org(auth), competencia)
    return [
        DREOut(
            cliente_id=l.cliente_id, cliente_nome=l.cliente_nome,
            receita=l.receita, custo=l.custo,
            margem=l.margem, margem_percentual=l.margem_percentual,
            alertas=l.alertas,
        )
        for l in linhas
    ]


# ── Régua de cobrança ───────────────────────────────────────────────
@router.get("/inadimplentes", response_model=list[InadimplenteOut])
async def inadimplentes(
    hoje: str | None = Query(default=None, description="ISO date; padrão = hoje"),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[InadimplenteOut]:
    """Overdue invoices, worst first.

    Feeds the WhatsApp/e-mail dunning sequence and the Módulo 4 portal block.
    Read-only by design — see the module docstring.
    """
    referencia = date.fromisoformat(hoje) if hoje else None
    linhas = FinanceiroService(repos).inadimplentes(_org(auth), hoje=referencia)
    return [InadimplenteOut(**f) for f in linhas]
