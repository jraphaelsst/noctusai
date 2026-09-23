"""Orçamentos — wave-2 slice A (roadmap R4–R7, R12).

  GET   /api/orcamentos?aba=&status=&negocio_id=&lead_id=&cliente_id=&q=
  POST  /api/orcamentos/calcular          pure preview (no write)
  GET   /api/orcamentos/{id}
  POST  /api/orcamentos                   201, versao = max + 1 for the negócio
  PATCH /api/orcamentos/{id}              rascunho|enviado only
  POST  /api/orcamentos/{id}/nova-versao  201, previous → substituido
  POST  /api/orcamentos/{id}/aceitar      the funnel's fechado transition + pautas
  POST  /api/orcamentos/{id}/recusar
  POST  /api/orcamentos/{id}/pdf          render + store, returns a signed URL
  GET   /api/orcamentos/{id}/pdf          signed URL of the stored PDF
  POST  /api/orcamentos/{id}/contrato     aceito only; modalidade digital|fisica

Rules live in `app/services/orcamentos.py` / `contratos.py`; this router maps
HTTP to them. Success = `{"data": ...}`; refusals = `{"detail", "code"}`.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, Query, status
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.responses import success_response

from app.automacoes_deps import get_portas_automacao
from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_core_db, get_db
from app.repositories import Repositorios
from app.schemas.orcamento import (
    CalcularIn,
    GerarContratoIn,
    OrcamentoCreate,
    OrcamentoUpdate,
    RecusarIn,
)
from app.services import automacoes
from app.services import contratos as contratos_svc
from app.services import orcamentos as svc
from app.services.documentos_pdf import nome_da_agencia, renderizar_orcamento_pdf
from app.services.orcamento_service import OrcamentoService
from app.services.regras import RegraViolada, http_de
from app.storage import get_storage
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orcamentos", tags=["orcamentos"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _chave_pdf(org_id: str, orcamento: dict) -> str:
    return f"{org_id}/orcamentos/{orcamento['id']}/v{int(orcamento.get('versao') or 1)}.pdf"


@router.get("")
async def listar_orcamentos(
    aba: Literal["ativos", "aceitos", "recusados"] | None = None,
    status_filtro: str | None = Query(default=None, alias="status"),
    negocio_id: str | None = None,
    lead_id: str | None = None,
    cliente_id: str | None = None,
    q: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    """Newest first. `aba`: ativos (rascunho|enviado) · aceitos · recusados
    (recusado|expirado|substituido); `q` searches título, lead and empresa."""
    return success_response(svc.listar(
        db, _org(auth), aba=aba, status=status_filtro, negocio_id=negocio_id,
        lead_id=lead_id, cliente_id=cliente_id, q=q,
    ))


@router.post("/calcular")
async def calcular(
    payload: CalcularIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    """Live totals for the modal — nothing is written.

    `alertas` (additive to the contract's Totais) is non-empty when the team's
    custo/hora is incomplete: the margin is then not trustworthy, and the UI
    must say so rather than show a confident number.
    """
    org_id = _org(auth)
    custo_hora, alertas = OrcamentoService(repos).custo_hora_medio(org_id)
    try:
        itens = svc.normalizar_itens(i.model_dump() for i in payload.itens)
        produtos = svc.produtos_dos_itens(db, org_id, itens)
        totais = svc.calcular_totais(
            itens, desconto=payload.desconto,
            horas_por_produto=svc.horas_por_produto(produtos), custo_hora=custo_hora,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return success_response({**totais, "itens": itens, "custo_hora_medio": custo_hora,
                             "alertas": alertas})


@router.get("/{orcamento_id}")
async def obter_orcamento(
    orcamento_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    return success_response(svc.obter(db, _org(auth), orcamento_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar_orcamento(
    payload: OrcamentoCreate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    org_id = _org(auth)
    custo_hora, _alertas = OrcamentoService(repos).custo_hora_medio(org_id)
    dados = payload.model_dump()
    dados["itens"] = [i.model_dump() for i in payload.itens]
    try:
        return success_response(svc.criar(db, org_id, dados, custo_hora=custo_hora))
    except RegraViolada as erro:
        raise http_de(erro) from erro


@router.patch("/{orcamento_id}")
async def atualizar_orcamento(
    orcamento_id: str,
    payload: OrcamentoUpdate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    org_id = _org(auth)
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise http_de(RegraViolada(422, "sem_campos", "Nenhum campo para atualizar."))
    if payload.itens is not None:
        dados["itens"] = [i.model_dump() for i in payload.itens]
    custo_hora, _alertas = OrcamentoService(repos).custo_hora_medio(org_id)
    try:
        return success_response(
            svc.atualizar(db, org_id, orcamento_id, dados, custo_hora=custo_hora)
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro


@router.post("/{orcamento_id}/nova-versao", status_code=status.HTTP_201_CREATED)
async def nova_versao(
    orcamento_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    try:
        return success_response(svc.nova_versao(db, _org(auth), orcamento_id))
    except RegraViolada as erro:
        raise http_de(erro) from erro


@router.post("/{orcamento_id}/aceitar")
async def aceitar(
    orcamento_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    portas: automacoes.PortasAutomacao = Depends(get_portas_automacao),
) -> dict:
    """Accept: negócio → fechado stage (ganho), Cliente created, pautas generated.

    Entering Fechado fires that stage's automations like any board move. The
    engine keys each execution on the ENTRY row, so a re-accept (no new
    transition) never fires twice."""
    try:
        resultado = svc.aceitar(db, _org(auth), orcamento_id, user_id=str(auth[0].id))
    except RegraViolada as erro:
        raise http_de(erro) from erro
    await automacoes.ao_entrar_etapa(portas, _org(auth), pipeline="comercial", card_id=str(resultado["negocio"]["id"]), user_id=str(auth[0].id))
    return success_response(resultado)


@router.post("/{orcamento_id}/recusar")
async def recusar(
    orcamento_id: str,
    payload: RecusarIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    try:
        return success_response(svc.recusar(db, _org(auth), orcamento_id, payload.motivo))
    except RegraViolada as erro:
        raise http_de(erro) from erro


@router.post("/{orcamento_id}/pdf")
async def gerar_pdf(
    orcamento_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    core_db: Any = Depends(get_core_db),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    """Render the proposal PDF into the private bucket; answer a signed URL."""
    org_id = _org(auth)
    hoje = svc.hoje_local()
    orcamento = svc.obter(db, org_id, orcamento_id, hoje=hoje)
    agencia = nome_da_agencia(core_db, org_id)
    pdf = await anyio.to_thread.run_sync(
        lambda: renderizar_orcamento_pdf(orcamento, agencia=agencia, emitido_em=hoje)
    )
    chave = _chave_pdf(org_id, orcamento)
    await storage.put(bucket=settings.igig_storage_bucket, key=chave, data=pdf,
                      content_type="application/pdf")
    db.table("orcamento").update({"pdf_key": chave}).eq("id", orcamento_id).eq(
        "org_id", org_id
    ).execute()
    url = await storage.signed_url(bucket=settings.igig_storage_bucket, key=chave,
                                   expires_in_seconds=contratos_svc.URL_TTL_SEGUNDOS)
    logger.info("pdf de orcamento gerado org=%s orcamento=%s bytes=%d", org_id, orcamento_id, len(pdf))
    return success_response({"pdf_key": chave, "url": url})


@router.get("/{orcamento_id}/pdf")
async def url_pdf(
    orcamento_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    orcamento = svc.carregar(db, _org(auth), orcamento_id)
    if not orcamento.get("pdf_key"):
        raise http_de(RegraViolada(
            409, "pdf_nao_gerado", "O PDF deste orçamento ainda não foi gerado."
        ))
    url = await storage.signed_url(
        bucket=settings.igig_storage_bucket, key=orcamento["pdf_key"],
        expires_in_seconds=contratos_svc.URL_TTL_SEGUNDOS,
    )
    return success_response({"url": url})


@router.post("/{orcamento_id}/contrato", status_code=status.HTTP_201_CREATED)
async def gerar_contrato(
    orcamento_id: str,
    payload: GerarContratoIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    core_db: Any = Depends(get_core_db),
    storage: StorageBackend = Depends(get_storage),
) -> dict:
    """Contrato from an aceito orçamento. `digital` → signature dry-run path;
    `fisica` → printable PDF with signature lines + "N vias" (roadmap R12)."""
    org_id = _org(auth)
    try:
        resultado = await contratos_svc.gerar(
            db, org_id, orcamento_id,
            modalidade=payload.modalidade_assinatura,
            dia_vencimento=payload.dia_vencimento,
            vias=payload.vias,
            signatario_email=payload.signatario_email,
            agencia=nome_da_agencia(core_db, org_id),
            storage=storage,
            bucket=settings.igig_storage_bucket,
            hoje=svc.hoje_local(),
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return success_response(resultado)
