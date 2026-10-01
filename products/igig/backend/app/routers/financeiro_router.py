"""Financeiro e Gestão de Contratos — Módulo 6.

  FATURAS      /api/financeiro/faturas …              CRUD + lines + mark paid/cancelled
  FECHAMENTO   /api/financeiro/faturas/gerar-competencia   monthly close, idempotent
  RESUMO       /api/financeiro/resumo                 a receber/recebido/inadimplente/MRR
  EXCEDENTES   /api/financeiro/excedentes/{comp}      delivered vs contracted
  DRE          /api/financeiro/dre                    revenue vs real hour-cost
  COBRANÇA     /api/financeiro/inadimplentes          overdue, with days late

`pagar`/`cancelar`/`gerar-competencia` are ADMIN-ONLY (`exigir_admin_da_org`):
each moves money or bills the whole active book — a different trust level
than reading a report or opening a one-off invoice.

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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.persistence import RecordNotFound, UniqueViolation

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.email_deps import EmailSenderFactory, get_email_sender_factory, get_email_settings
from app.pipelines import exigir_admin_da_org, get_core_db
from app.repositories import Repositorios, valor_da_linha_fatura
from app.schemas.financeiro import (
    DREOut,
    EnviarFaturaOut,
    ExcedenteOut,
    FaturaCreate,
    FaturaItemCreate,
    FaturaItemOut,
    FaturaItemUpdate,
    FaturaOut,
    FaturaUpdate,
    GerarCompetenciaIn,
    GerarCompetenciaOut,
    InadimplenteOut,
    ResumoFinanceiroOut,
)
from app.services.documentos_pdf import nome_da_agencia
from app.services.email_config import EmailSettings
from app.services.financeiro_service import FATURA_FECHADA, FinanceiroService, enviar_fatura
from app.services.regras import RegraViolada, http_de
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financeiro", tags=["financeiro"])

#: Statuses an invoice cannot add lines to / be re-sent from.
_FATURA_FECHADA = FATURA_FECHADA


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

    `contrato_id` is OPTIONAL — an avulsa (one-off) charge has no contract to
    point at — but when the caller DOES pick one, a second invoice for the
    same contract+competência is a 409, enforced by the same unique index
    `gerar_competencia` relies on: manual and generated invoices share ONE
    idempotency guarantee, not two (finding #4, 2026-09 audit).
    """
    org_id = _org(auth)
    try:
        repos.cliente.buscar(org_id, payload.cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if payload.contrato_id:
        try:
            repos.contrato.buscar(org_id, payload.contrato_id)
        except RecordNotFound:
            # Validated BEFORE the insert so a bad id 404s cleanly instead of
            # surfacing as a foreign-key violation mislabelled below as
            # "duplicate invoice" (finding #7).
            raise HTTPException(status_code=404, detail="Contrato não encontrado")
    valores = payload.model_dump(exclude_none=True)
    if payload.vencimento is not None:
        valores["vencimento"] = payload.vencimento.isoformat()
    try:
        registro = repos.fatura.criar(org_id, valores)
    except UniqueViolation:
        # The specific member, not `PersistenceError` — a different
        # constraint failure here must surface as a real error, not this
        # message (finding #7's root cause: the broad catch could not tell
        # the two apart).
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

    A `desconto` line SUBTRACTS from the total (finding #3, 2026-09 audit —
    it used to add like every other line); a discount big enough to push the
    total negative is refused (422) rather than persisted, since a negative
    invoice has no real-world meaning here.
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
    itens_atuais = repos.fatura_item.da_fatura(org_id, fatura_id)
    novo_item = payload.model_dump()
    prospectivo = sum(valor_da_linha_fatura(i) for i in itens_atuais) + valor_da_linha_fatura(novo_item)
    if round(prospectivo, 2) < 0:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": "Este desconto deixaria o total da fatura negativo.",
                "code": "total_negativo",
            },
        )
    repos.fatura_item.criar(org_id, {"fatura_id": fatura_id, **novo_item})
    itens = repos.fatura_item.da_fatura(org_id, fatura_id)
    return FaturaOut(**repos.fatura.recalcular_total(org_id, fatura_id, itens))


def _fatura_aberta(repos: Repositorios, org_id: str, fatura_id: str) -> dict:
    """Load an org-scoped invoice and refuse (409) once it is `paga`/`cancelada`
    — editing a closed invoice would silently change a number already paid or voided."""
    try:
        fatura = repos.fatura.buscar(org_id, fatura_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.get("status") in _FATURA_FECHADA:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": f"Fatura {fatura['status']} não pode ser editada.",
                "code": "fatura_fechada",
            },
        )
    return fatura


def _item_da_fatura(repos: Repositorios, org_id: str, fatura_id: str, item_id: str) -> dict:
    try:
        item = repos.fatura_item.buscar(org_id, item_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    if str(item.get("fatura_id")) != str(fatura_id):
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return item


@router.patch(
    "/faturas/{fatura_id}", response_model=FaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def editar_fatura(
    fatura_id: str,
    payload: FaturaUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Edit competência / vencimento of an open invoice. Admin-only; 409 on
    `paga`/`cancelada`; 409 if the new competência collides with the
    contract's existing invoice (same unique index as creation)."""
    org_id = _org(auth)
    atual = _fatura_aberta(repos, org_id, fatura_id)
    valores = payload.model_dump(exclude_unset=True)
    if valores.get("vencimento") is not None:
        valores["vencimento"] = valores["vencimento"].isoformat()
    if not valores:
        return FaturaOut(**atual)
    try:
        return FaturaOut(**repos.fatura.atualizar(org_id, fatura_id, valores))
    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe fatura para este contrato em {valores.get('competencia')}",
        )


@router.patch(
    "/faturas/{fatura_id}/itens/{item_id}", response_model=FaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def editar_item(
    fatura_id: str,
    item_id: str,
    payload: FaturaItemUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Edit a line of an open invoice and RETURN the invoice with the total
    recomputed (same `recalcular_total` + negative-total guard as adding)."""
    org_id = _org(auth)
    _fatura_aberta(repos, org_id, fatura_id)
    item = _item_da_fatura(repos, org_id, fatura_id, item_id)
    valores = payload.model_dump(exclude_none=True)
    if valores:
        itens = repos.fatura_item.da_fatura(org_id, fatura_id)
        prospectivo = sum(
            valor_da_linha_fatura({**i, **valores} if i["id"] == item["id"] else i)
            for i in itens
        )
        if round(prospectivo, 2) < 0:
            raise HTTPException(
                status_code=422,
                detail={
                    "detail": "Esta alteração deixaria o total da fatura negativo.",
                    "code": "total_negativo",
                },
            )
        repos.fatura_item.atualizar(org_id, item_id, valores)
    itens = repos.fatura_item.da_fatura(org_id, fatura_id)
    return FaturaOut(**repos.fatura.recalcular_total(org_id, fatura_id, itens))


@router.delete(
    "/faturas/{fatura_id}/itens/{item_id}", response_model=FaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def remover_item(
    fatura_id: str,
    item_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Delete a line of an open invoice; returns the invoice, total recomputed."""
    org_id = _org(auth)
    _fatura_aberta(repos, org_id, fatura_id)
    item = _item_da_fatura(repos, org_id, fatura_id, item_id)
    itens_restantes = [
        i for i in repos.fatura_item.da_fatura(org_id, fatura_id) if i["id"] != item["id"]
    ]
    if round(sum(valor_da_linha_fatura(i) for i in itens_restantes), 2) < 0:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": "Remover este item deixaria o total da fatura negativo.",
                "code": "total_negativo",
            },
        )
    repos.fatura_item.remover(org_id, item_id)
    return FaturaOut(**repos.fatura.recalcular_total(org_id, fatura_id, itens_restantes))


@router.post(
    "/faturas/{fatura_id}/pagar", response_model=FaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def marcar_paga(
    fatura_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Mark an invoice paid. Admin-only — a money movement, not a status label.

    Manual today: the gateway webhook that will do this automatically needs
    credentials that do not exist yet. An explicit endpoint beats a fake
    integration that silently marks things paid.

    Idempotent on an already-`paga` invoice (returns it unchanged — `pago_em`
    is never overwritten by a second click); refuses a `cancelada` one
    outright, since "paying" a voided invoice would contradict the voiding
    (finding #9, 2026-09 audit).
    """
    org_id = _org(auth)
    try:
        fatura = repos.fatura.buscar(org_id, fatura_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.get("status") == "cancelada":
        raise HTTPException(
            status_code=409,
            detail={"detail": "Fatura cancelada não pode ser paga.", "code": "fatura_cancelada"},
        )
    if fatura.get("status") == "paga":
        return FaturaOut(**fatura)
    return FaturaOut(**repos.fatura.marcar_paga(org_id, fatura_id))


@router.post(
    "/faturas/{fatura_id}/cancelar", response_model=FaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def cancelar_fatura(
    fatura_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Void an invoice. Admin-only.

    Voiding frees the contract+competência slot the unique index guards (the
    SAME index `gerar_competencia` reads), so a mistaken close can be undone
    with a real re-close rather than a manual edit. A `paga` invoice refuses —
    voiding money already received is a refund, a different (unbuilt)
    process, not a status flip; cancelling an already-`cancelada` invoice is a
    no-op (returns it unchanged), not an error.
    """
    org_id = _org(auth)
    try:
        fatura = repos.fatura.buscar(org_id, fatura_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    if fatura.get("status") == "paga":
        raise HTTPException(
            status_code=409,
            detail={"detail": "Fatura paga não pode ser cancelada.", "code": "fatura_paga"},
        )
    if fatura.get("status") == "cancelada":
        return FaturaOut(**fatura)
    return FaturaOut(**repos.fatura.cancelar(org_id, fatura_id))


@router.post(
    "/faturas/{fatura_id}/enviar", response_model=EnviarFaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def enviar_fatura_endpoint(
    fatura_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    core_db: Any = Depends(get_core_db),
    sender_factory: EmailSenderFactory = Depends(get_email_sender_factory),
    cfg: EmailSettings = Depends(get_email_settings),
) -> EnviarFaturaOut:
    """E-mail the fatura's PDF to the cliente. Admin-only — a client-facing
    financial communication, same trust level as `pagar`/`cancelar`.

    409 `smtp_nao_configurado` with nothing usable configured (same as
    orçamentos); 422 `email_destinatario_ausente` when the cliente has no
    e-mail on file; 409 `fatura_fechada` on a `paga`/`cancelada` invoice.
    """
    org_id = _org(auth)
    try:
        atualizada, message_id = await enviar_fatura(
            repos, org_id, fatura_id,
            sender_factory=sender_factory, settings=cfg,
            agencia=nome_da_agencia(core_db, org_id),
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return EnviarFaturaOut(fatura=FaturaOut(**atualizada), message_id=message_id)


@router.post(
    "/faturas/{fatura_id}/marcar-enviada", response_model=FaturaOut,
    dependencies=[Depends(exigir_admin_da_org)],
)
async def marcar_fatura_enviada(
    fatura_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> FaturaOut:
    """Manual "sent outside the system" flag — e.g. the agency e-mailed the
    fatura itself, or handed it over in person. Same status + `enviada_em`
    the "Enviar fatura" action sets, without actually sending anything.
    Admin-only; refuses on a `paga`/`cancelada` invoice (`fatura_fechada`).
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
                "detail": f"Fatura {fatura['status']} não pode ser marcada como enviada.",
                "code": "fatura_fechada",
            },
        )
    return FaturaOut(**repos.fatura.marcar_enviada(org_id, fatura_id))


@router.post(
    "/faturas/gerar-competencia", response_model=GerarCompetenciaOut,
    status_code=status.HTTP_200_OK, dependencies=[Depends(exigir_admin_da_org)],
)
async def gerar_competencia(
    payload: GerarCompetenciaIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> GerarCompetenciaOut:
    """Close the month: open an invoice for every active contract at once.
    Admin-only — it bills the whole active book at once.

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
    custo_por_competencia: bool = Query(
        default=False,
        description=(
            "Quando true, o custo TAMBÉM é filtrado pela competência (horas "
            "apontadas naquele mês) em vez do histórico completo — usado "
            "pelo Dashboard para a margem do mês; exige `competencia`."
        ),
    ),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[DREOut]:
    """Revenue vs real hour-cost, per client.

    Cost comes from the same `BIService` the Módulo 5 screen uses, so the two
    can never disagree about a client. `alertas` warns when the margin is
    OVERSTATED because some hours could not be costed.
    """
    try:
        linhas = FinanceiroService(repos).dre(
            _org(auth), competencia, custo_por_competencia=custo_por_competencia
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    referencia: date | None = None
    if hoje:
        try:
            referencia = date.fromisoformat(hoje)
        except ValueError:
            # A malformed query param is the caller's error, not a server
            # fault (finding #8, 2026-09 audit — this used to 500).
            raise HTTPException(status_code=422, detail=f"data inválida: {hoje!r}; esperado AAAA-MM-DD")
    linhas = FinanceiroService(repos).inadimplentes(_org(auth), hoje=referencia)
    return [InadimplenteOut(**f) for f in linhas]
