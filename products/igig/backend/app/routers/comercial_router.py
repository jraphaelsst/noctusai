"""CRM, Orçamentos e Onboarding — Módulo 1.

  PÚBLICO  POST /api/comercial/leads/publico       pré-qualificação form
  LEADS    /api/comercial/leads …                  triage
  ORÇAMENTO POST /api/comercial/estimar            the escopo calculator
           /api/comercial/orcamentos …             proposals
  CONTRATO POST /api/comercial/contratos/gerar     PDF + signature dispatch
           POST /api/comercial/assinatura/webhook  → activates the client

The lead form is UNAUTHENTICATED by design — it is embedded on the agency's
public site — so it is rate-limited and writes ONLY to `lead`. It cannot touch
`cliente`, cannot read anything, and returns no data beyond an acknowledgement:
an anonymous endpoint that echoed stored records back would be a scraping
surface.

The signature webhook is the spec's Módulo 1 automation: confirmation flips the
client to `ativo` and converts the originating lead. It is idempotent, because
signing providers retry.
"""
# NOTE: no `from __future__ import annotations` — this module IS rate-limited;
# see esteira_router.py for the slowapi/PEP 563 interaction.
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from noctusai_lib.integrations.persistence import RecordNotFound

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.rate_limit import limiter
from app.repositories import Repositorios
from app.schemas.comercial import (
    AssinaturaWebhookIn,
    ContratoDocumentoOut,
    DefinirPrecoFinal,
    EstimativaOut,
    GerarContratoIn,
    ItemEscopoIn,
    LeadOut,
    LeadPublicoIn,
    OrcamentoCreate,
    OrcamentoOut,
)
from app.services.contrato_documento import enviar_para_assinatura, gerar_pdf_contrato
from app.services.orcamento_service import ItemEscopo, OrcamentoService
from app.storage import chave_da_peca, get_storage
from app.store import get_repositorios, get_repositorios_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comercial", tags=["comercial"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _localizar_contrato(repos: Repositorios, external_id: str):
    """Resolve (org_id, contrato) from a signature external id.

    The id is minted as `<org_id>.<resto>` (see
    `services/contrato_documento.enviar_para_assinatura`), so the org comes out
    of the identifier itself and the lookup stays ORG-SCOPED — the same
    technique the approval portal uses, rather than adding a cross-org query
    to the persistence seam for one caller.
    """
    from noctusai_lib.integrations.persistence import Op, QuerySpec

    org_id, separador, resto = external_id.partition(".")
    if not separador or not org_id or not resto:
        return None
    encontrados = repos.contrato.listar(
        org_id, spec=QuerySpec().with_filter("assinatura_external_id", Op.EQ, external_id)
    )
    return (org_id, encontrados[0]) if encontrados else None


# ── PÚBLICO — formulário de pré-qualificação ────────────────────────
@router.post("/leads/publico", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.webhook_rate_limit)
async def capturar_lead(
    request: Request,
    payload: LeadPublicoIn,
    repos: Repositorios = Depends(get_repositorios_admin),
) -> dict:
    """Public lead capture. No auth, write-only, rate-limited.

    Returns only an acknowledgement — never the stored record, and never an
    id. An anonymous endpoint that echoed data back would be a scraping
    surface, and the submitter has no use for it.
    """
    dados = payload.model_dump(exclude_none=True)
    org_id = str(dados.pop("org_id"))
    repos.lead.criar(org_id, dados)
    logger.info("lead capturado org=%s origem=%s", org_id, dados.get("origem"))
    return {"ok": True, "mensagem": "Recebemos seus dados. Entraremos em contato em breve."}


# ── Leads (authed) ──────────────────────────────────────────────────
@router.get("/leads", response_model=list[LeadOut])
async def listar_leads(
    status_filtro: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[LeadOut]:
    org_id = _org(auth)
    linhas = (
        repos.lead.por_status(org_id, status_filtro) if status_filtro else repos.lead.listar(org_id)
    )
    return [LeadOut(**l) for l in linhas]


@router.post("/leads/{lead_id}/converter", response_model=LeadOut)
async def converter_lead(
    lead_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> LeadOut:
    """Turn a lead into a cliente, keeping the funnel link.

    Idempotent: a lead already converted returns its existing cliente rather
    than creating a second one.
    """
    org_id = _org(auth)
    try:
        lead = repos.lead.buscar(org_id, lead_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    if lead.get("cliente_id"):
        return LeadOut(**lead)

    cliente = repos.cliente.criar(org_id, {
        "nome": lead.get("empresa") or lead.get("nome"),
        "nicho": lead.get("nicho"),
        "email": lead.get("email"),
        "telefone": lead.get("telefone"),
        "origem": lead.get("origem"),
    })
    return LeadOut(**repos.lead.converter(org_id, lead_id, str(cliente["id"])))


# ── Calculadora de escopo ───────────────────────────────────────────
@router.post("/estimar", response_model=EstimativaOut)
async def estimar(
    itens: list[ItemEscopoIn],
    margem_alvo: float = 50.0,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> EstimativaOut:
    """Price a scope from the team's REAL hourly costs.

    `alertas` matters as much as the number: with no custo/hora data the
    suggestion is 0, and a caller must be told rather than quoting it.
    """
    try:
        estimativa = OrcamentoService(repos).estimar(
            _org(auth),
            [ItemEscopo(i.formato, i.quantidade, i.horas_unitarias) for i in itens],
            margem_alvo=margem_alvo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # asdict(), not vars(): Estimativa is a slots=True dataclass.
    return EstimativaOut(**asdict(estimativa))


@router.post("/orcamentos", response_model=OrcamentoOut, status_code=status.HTTP_201_CREATED)
async def criar_orcamento(
    payload: OrcamentoCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> OrcamentoOut:
    """Save a proposal with the calculator's numbers baked in.

    The estimate is STORED, not recomputed on read: rates change, and a
    proposal already sent to a client must keep the numbers it was sent with.
    """
    org_id = _org(auth)
    try:
        estimativa = OrcamentoService(repos).estimar(
            org_id,
            [ItemEscopo(i.formato, i.quantidade, i.horas_unitarias) for i in payload.itens],
            margem_alvo=payload.margem_alvo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registro = repos.orcamento.criar(org_id, {
        "titulo": payload.titulo,
        "lead_id": payload.lead_id,
        "cliente_id": payload.cliente_id,
        "escopo": [i.model_dump() for i in payload.itens],
        "horas_estimadas": estimativa.horas,
        "custo_estimado": estimativa.custo,
        "preco_sugerido": estimativa.preco_sugerido,
        "margem_alvo": payload.margem_alvo,
    })
    return OrcamentoOut(**registro)


@router.get("/orcamentos", response_model=list[OrcamentoOut])
async def listar_orcamentos(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[OrcamentoOut]:
    return [OrcamentoOut(**o) for o in repos.orcamento.listar(_org(auth))]


@router.post("/orcamentos/{orcamento_id}/preco", response_model=OrcamentoOut)
async def definir_preco_final(
    orcamento_id: str,
    payload: DefinirPrecoFinal,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> OrcamentoOut:
    """A director's override of the suggested price (spec §M1 business rule).

    Accepted even BELOW the suggestion — the spec explicitly permits ignoring
    the calculator. `preco_sugerido` is kept alongside, so the concession stays
    visible instead of being overwritten.
    """
    org_id = _org(auth)
    try:
        atual = repos.orcamento.atualizar(
            org_id, orcamento_id, {"preco_final": payload.preco_final}
        )
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    if payload.preco_final < float(atual.get("preco_sugerido") or 0):
        logger.info(
            "preço final ABAIXO do sugerido org=%s orcamento=%s final=%s sugerido=%s",
            org_id, orcamento_id, payload.preco_final, atual.get("preco_sugerido"),
        )
    return OrcamentoOut(**atual)


# ── Contrato: PDF + assinatura ──────────────────────────────────────
@router.post("/contratos/gerar", response_model=ContratoDocumentoOut,
             status_code=status.HTTP_201_CREATED)
async def gerar_contrato(
    payload: GerarContratoIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ContratoDocumentoOut:
    """Generate the contract PDF, store it, and dispatch for signature."""
    org_id = _org(auth)
    try:
        cliente = repos.cliente.buscar(org_id, payload.cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    pdf = gerar_pdf_contrato(
        cliente_nome=str(cliente.get("nome") or ""),
        titulo=payload.titulo,
        valor_mensal=payload.valor_mensal,
        posts_por_mes=payload.posts_por_mes,
        vigencia=payload.vigencia,
        clausulas=payload.clausulas,
    )

    contrato = repos.contrato.criar(org_id, {
        "cliente_id": payload.cliente_id,
        "orcamento_id": payload.orcamento_id,
        "valor_mensal": payload.valor_mensal,
        "posts_por_mes": payload.posts_por_mes,
        "status": "aguardando_assinatura",
    })

    chave = chave_da_peca(org_id, f"contratos/{contrato['id']}", "contrato.pdf")
    await get_storage().put(
        bucket=settings.igig_storage_bucket, key=chave,
        data=pdf, content_type="application/pdf",
    )

    try:
        solicitacao = enviar_para_assinatura(
            org_id=org_id,
            provedor=payload.provedor,
            documento_nome=payload.titulo,
            signatario_email=payload.signatario_email,
        )
    except (ValueError, NotImplementedError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repos.contrato.atualizar(org_id, str(contrato["id"]), {
        "documento_key": chave,
        "provedor_assinatura": solicitacao.provedor,
        "assinatura_external_id": solicitacao.external_id,
        "link_assinatura": solicitacao.link_assinatura,
    })
    logger.info(
        "contrato gerado org=%s id=%s dry_run=%s",
        org_id, contrato["id"], solicitacao.dry_run,
    )
    return ContratoDocumentoOut(
        contrato_id=str(contrato["id"]),
        documento_key=chave,
        provedor=solicitacao.provedor,
        link_assinatura=solicitacao.link_assinatura,
        external_id=solicitacao.external_id,
        dry_run=solicitacao.dry_run,
    )


@router.post("/assinatura/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def assinatura_webhook(
    request: Request,
    payload: AssinaturaWebhookIn,
    repos: Repositorios = Depends(get_repositorios_admin),
) -> dict:
    """Signature provider callback — the Módulo 1 automation.

    On `assinado`: the contract goes ativo, the CLIENT goes ativo, and the
    originating lead is marked convertido. Idempotent, because providers retry
    — a second delivery must not re-run the side effects.

    Runs on the service-role client: the caller is a vendor with no noc
    session. The `external_id` is the credential, exactly like the approval
    portal's token.
    """
    encontrado = _localizar_contrato(repos, payload.external_id)
    if encontrado is None:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    org_id, contrato = encontrado

    if contrato.get("status") == "ativo":
        return {"ok": True, "ja_processado": True}

    if payload.evento != "assinado":
        repos.contrato.atualizar(org_id, str(contrato["id"]), {"status": "rascunho"})
        return {"ok": True, "status": "rascunho"}

    repos.contrato.registrar_assinatura(org_id, str(contrato["id"]))
    cliente_id = str(contrato.get("cliente_id") or "")
    if cliente_id:
        repos.cliente.ativar(org_id, cliente_id)
        for lead in repos.lead.listar(org_id):
            if str(lead.get("cliente_id") or "") == cliente_id:
                repos.lead.converter(org_id, str(lead["id"]), cliente_id)
    logger.info("contrato assinado org=%s cliente=%s", org_id, cliente_id)
    # NOC-REMEDIATE[igig-onboarding]: welcome e-mail/WhatsApp + onboarding form
    # dispatch belongs here; needs the Resend/WAHA wiring. — 2026-08-09
    return {"ok": True, "cliente_ativado": bool(cliente_id)}
