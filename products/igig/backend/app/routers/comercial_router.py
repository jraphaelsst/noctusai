"""CRM, Orçamentos e Onboarding — Módulo 1.

  PÚBLICO  POST /api/comercial/leads/publico       pré-qualificação form
  LEADS    /api/comercial/leads …                  triage
  CONTRATO POST /api/comercial/assinatura/webhook  → activates the client (SIGNED)

The funnel board (negócios, stages, mover-etapa) is `comercial_funil_router`.
Orçamentos, the catalogue and contract generation are `orcamento_router` /
`produto_router` / `contrato_router` (wave 2 — the old `estimar`,
`orcamentos*` and `contratos/gerar` endpoints here were replaced by them).

The lead form is UNAUTHENTICATED by design — it is embedded on the agency's
public site — so it is rate-limited and writes ONLY the lead and its funnel
card (roadmap R2: a form lead appears in the funnel's first stage). It cannot
touch `cliente`, cannot read anything, and returns no data beyond an
acknowledgement: an anonymous endpoint that echoed stored records back would be
a scraping surface.

The signature webhook is the spec's Módulo 1 automation: confirmation flips the
client to `ativo` and converts the originating lead. It is idempotent, because
signing providers retry — and it is HMAC-verified before anything runs (smoke
finding 2: it used to accept any caller holding a guessable id).
"""
# NOTE: no `from __future__ import annotations` — this module IS rate-limited;
# see esteira_router.py for the slowapi/PEP 563 interaction.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from noctusai_lib.integrations.persistence import RecordNotFound
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)
from pydantic import ValidationError

from app.config import get_settings, settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_admin_db
from app.rate_limit import limiter
from app.repositories import Repositorios
from app.schemas.comercial import AssinaturaWebhookIn, LeadOut, LeadPatchIn, LeadPublicoIn
from app.services import comercial_funil
from app.services.regras import RegraViolada
from app.store import get_repositorios, get_repositorios_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comercial", tags=["comercial"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _cfg(request: Request) -> Any:
    """Settings as FastAPI would resolve them, for the `(request, body)`
    secret resolver below — it cannot declare a dependency. Honours
    `app.dependency_overrides[get_settings]` instead of reading the module
    singleton directly, the same Class-A seam `lead_webhooks_router._cfg`
    uses (KB § PATTERNS/backend/di-test-seam.md)."""
    override = request.app.dependency_overrides.get(get_settings)
    return override() if override is not None else settings


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
    db: Any = Depends(get_admin_db),
) -> dict:
    """Public lead capture. No auth, write-only, rate-limited.

    The lead lands with `origem='formulario'` (the CHANNEL); the form's own
    free-text `origem` field — "como nos conheceu" — is stored as
    `como_conheceu`, so the public form's contract is unchanged. Its funnel
    card is opened at the entry stage in the same request.

    Returns only an acknowledgement — never the stored record, and never an
    id. An anonymous endpoint that echoed data back would be a scraping
    surface, and the submitter has no use for it.
    """
    dados = payload.model_dump(exclude_none=True)
    org_id = str(dados.pop("org_id"))
    como_conheceu = dados.pop("origem", None)
    linhas = (
        db.table("lead").insert(
            {**dados, "org_id": org_id, "origem": "formulario", "como_conheceu": como_conheceu}
        ).execute().data or []
    )
    if not linhas:
        raise RuntimeError("insert de lead não retornou a linha criada")
    try:
        comercial_funil.abrir_negocio(db, org_id, lead_id=str(linhas[0]["id"]))
    except RegraViolada:
        # The lead IS stored; only its card could not be placed (an org that
        # deactivated every funnel stage). Loud, but the visitor's submission
        # must not be rejected for the agency's configuration.
        logger.error("lead %s sem card no funil org=%s — funil sem etapas ativas",
                     linhas[0]["id"], org_id)
    logger.info("lead capturado org=%s como_conheceu=%s", org_id, como_conheceu)
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


@router.patch("/leads/{lead_id}")
async def atualizar_lead(
    lead_id: str,
    payload: LeadPatchIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    """Edit a lead's contact data — the negócio card's "Lead" subpage.

    org-scoped by :class:`LeadRepository`'s `atualizar` (`BaseRepository`,
    every write scoped to `org_id`); a 404 for a lead outside this org."""
    org_id = _org(auth)
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")
    try:
        lead = repos.lead.atualizar(org_id, lead_id, dados)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return success_response(LeadOut(**lead).model_dump())


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
        "lead_id": lead_id,
    })
    return LeadOut(**repos.lead.converter(org_id, lead_id, str(cliente["id"])))


async def _segredo_assinatura(request: Request, body: bytes) -> ResolvedSecret:
    """Per-request read so a rotated secret (or a test's value) is honoured.
    Empty collapses to "unset", which `bypass_when_unset=False` refuses."""
    return ResolvedSecret(secret=_cfg(request).igig_assinatura_webhook_secret or None)


@router.post("/assinatura/webhook")
@limiter.limit(settings.webhook_rate_limit)
async def assinatura_webhook(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_segredo_assinatura,
        scheme="sha256_hex",
        # FAIL-CLOSED: with no secret configured every call is a 401. An
        # unsigned endpoint that ACTIVATES CONTRACTS is the hole this closes
        # (smoke finding 2) — there is no early-dev bypass here.
        bypass_when_unset=False,
        log_prefix="igig-assinatura-webhook",
    ),
    repos: Repositorios = Depends(get_repositorios_admin),
) -> dict:
    """Signature provider callback — the Módulo 1 automation.

    On `assinado`: the contract goes ativo, the CLIENT goes ativo, and the
    originating lead is marked convertido. Idempotent, because providers retry
    — a second delivery must not re-run the side effects.

    Auth is the HMAC-SHA256 of the raw body under
    `IGIG_ASSINATURA_WEBHOOK_SECRET` (header `X-Webhook-Hmac-SHA256`), checked
    BEFORE any read. The body is parsed from the VERIFIED bytes. Runs on the
    service-role client: the caller is a vendor with no noc session.
    """
    try:
        payload = AssinaturaWebhookIn.model_validate_json(verified.body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc
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
