"""PUBLIC lead-source webhooks — vendors, no noc session (contract §E2).

  POST /api/webhooks/waha/{token}      WAHA inbound → first message of an unknown
                                       chat creates lead (origem whatsapp) + negócio
  GET  /api/webhooks/meta/leadgen      Meta's one-time subscription handshake
  POST /api/webhooks/meta/leadgen      Meta Lead Ads delivery → lead (origem
                                       meta_ads) + negócio

Auth, BEFORE any side effect:

* WAHA — the per-org opaque `{token}` (minted by the setup PUT, compared in
  constant time; an unknown token is a generic 404, no enumeration) AND the
  HMAC of the raw body under the platform's `IGIG_WAHA_WEBHOOK_HMAC_SECRET`
  (`X-Webhook-Hmac-SHA256`) — exactly social-wiring's `/webhook/{token}`,
  including its unset-secret affordance (accepted with a WARNING; the token
  still gates).
* Meta — `X-Hub-Signature-256` under the Meta APP SECRET of the org that owns
  the delivery's Page (org-stored, else `IGIG_META_APP_SECRET`). No secret ⇒
  401, never a bypass: a forged POST would write lead PII (social-wiring's
  deliberate `bypass_when_unset=False`, same reasoning). The handshake echoes
  `hub.challenge` only when `hub.verify_token` matches an org's stored token.

Both answer 200 for everything past authentication (malformed bodies, ignored
events, duplicates, per-lead failures): a vendor retries non-2xx and Meta can
disable the subscription. Per-lead failures are therefore RECORDED where an
operator sees them — `integracao.ultimo_erro` of the org's channel, plus an
ERROR log — and reported in the response body; never swallowed.

Runs on the igig service-role client (`get_portas_automacao_admin`); `org_id`
comes from the verified token / Page and is filtered on every query.
"""
# NOTE: deliberately NO `from __future__ import annotations` — the routes are
# wrapped by `@limiter.limit(...)` (see esteira_router.py for the failure mode).
import asyncio
import hmac
import json
import logging
import uuid
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from noctusai_lib.integrations.meta import MetaGraphError, get_meta_adapter
from noctusai_lib.integrations.meta.leadgen_webhook import (
    leadgen_challenge_response,
    parse_leadgen_webhook,
)
from noctusai_lib.integrations.whatsapp import (
    WhatsAppIgnoredEvent,
    WhatsAppPayloadError,
    parse_waha_inbound_message,
)
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.automacoes_deps import get_portas_automacao_admin
from app.config import get_settings, settings
from app.pipelines import get_admin_db
from app.rate_limit import limiter
from app.services import canais_org, fontes_lead
from app.services.automacoes import PortasAutomacao
from app.services.canais_org import CanalNaoConfigurado

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["lead-webhooks"])


def _cfg(request: Request) -> Any:
    """Settings as FastAPI would resolve them, for the `(request, body)`
    secret resolvers that cannot declare a dependency — honours
    `app.dependency_overrides[get_settings]` (social-wiring's
    `_cfg_for_request`, KB § PATTERNS/backend/di-test-seam.md Class-A)."""
    override = request.app.dependency_overrides.get(get_settings)
    return override() if override is not None else settings


def _admin_db(request: Request) -> Any:
    """The service-role client for the resolvers — same override-honouring
    read as `_cfg` (the resolver runs before the route's own dependencies)."""
    override = request.app.dependency_overrides.get(get_admin_db)
    return override() if override is not None else get_admin_db()


def get_meta_adapter_factory() -> Callable[[str], Any]:
    """`page_access_token -> MetaAdapter`. A dependency so tests hand the route
    a seeded `FakeMetaAdapter` instead of patching the seed factory. The Page
    token is used as the adapter's token: `GET /{leadgen_id}` with the owning
    Page's token is exactly the read Meta's docs prescribe."""
    return lambda token: get_meta_adapter(system_user_token=token)


# ── WAHA ─────────────────────────────────────────────────────────────
async def _segredo_waha(request: Request, body: bytes) -> ResolvedSecret:
    return ResolvedSecret(secret=_cfg(request).igig_waha_webhook_hmac_secret or None)


def _org_do_token(token: str) -> str | None:
    """The org half of `<org_uuid>.<secret>`, or `None` for a malformed token —
    checked BEFORE it reaches a query (a non-UUID would surface as a 500 from
    the `uuid` cast, i.e. an oracle on the token shape)."""
    org_id, _sep, resto = token.partition(".")
    if not org_id or not resto:
        return None
    try:
        return str(uuid.UUID(org_id))
    except ValueError:
        return None


@router.post("/waha/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def waha_webhook(
    token: str,
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_segredo_waha,
        scheme="sha256_hex",
        bypass_when_unset=True,
        log_prefix="igig-waha-webhook",
    ),
    portas: PortasAutomacao = Depends(get_portas_automacao_admin),
) -> JSONResponse:
    org_id = _org_do_token(token)
    row = canais_org.integracao(portas.db, org_id, "whatsapp") if org_id else None
    esperado = str(((row or {}).get("config") or {}).get("webhook_token") or "")
    if not row or not row.get("ativo") or not esperado or not hmac.compare_digest(esperado, token):
        # Never log the token — it is a routing credential.
        logger.debug("igig-waha-webhook: token desconhecido (404)")
        return JSONResponse({"detail": "Not Found"}, status_code=status.HTTP_404_NOT_FOUND)

    try:
        corpo = json.loads(verified.body or b"{}")
    except (ValueError, TypeError):
        logger.warning("igig-waha-webhook: corpo não é JSON org=%s — ignorado", org_id)
        return JSONResponse({"status": "ignorado", "motivo": "json_invalido"})
    if not isinstance(corpo, dict):
        return JSONResponse({"status": "ignorado", "motivo": "nao_objeto"})
    evento = corpo.get("payload") if isinstance(corpo.get("payload"), dict) else corpo
    if evento.get("fromMe") is True:
        # The agency's own outgoing message is not a lead arriving.
        return JSONResponse({"status": "ignorado", "motivo": "mensagem_propria"})
    try:
        mensagem = parse_waha_inbound_message(corpo)
    except WhatsAppIgnoredEvent as exc:
        return JSONResponse({"status": "ignorado", "motivo": str(exc)})
    except WhatsAppPayloadError as exc:
        logger.warning("igig-waha-webhook: payload inválido org=%s: %s", org_id, exc)
        return JSONResponse({"status": "ignorado", "motivo": str(exc)})

    try:
        resultado = await fontes_lead.lead_do_whatsapp(portas, org_id, mensagem)
    except Exception as exc:  # noqa: BLE001 — recorded on the channel + logged; WAHA gets 200
        logger.exception("igig-waha-webhook: falha ao criar lead org=%s", org_id)
        canais_org.registrar_erro(portas.db, org_id, "whatsapp",
                                  f"Falha ao criar lead do WhatsApp: {type(exc).__name__}: {exc}")
        return JSONResponse({"status": "erro", "detalhe": f"{type(exc).__name__}"})
    return JSONResponse(resultado)


# ── Meta Lead Ads ────────────────────────────────────────────────────
def _paginas_do_corpo(body: bytes) -> list[str]:
    """Page ids in an (unverified) delivery — ROUTING ONLY: they pick whose
    app secret verifies the signature; nothing is written before that check."""
    try:
        corpo = json.loads(body or b"{}")
    except (ValueError, TypeError):
        return []
    if not isinstance(corpo, dict):
        return []
    return [str(e.get("id")) for e in corpo.get("entry") or [] if isinstance(e, dict) and e.get("id")]


def _configs_por_pagina(db: Any, cfg: Any) -> dict[str, canais_org.ConfigMetaLeads]:
    saida: dict[str, canais_org.ConfigMetaLeads] = {}
    for row in canais_org.listar_por_canal(db, "meta_leads"):
        try:
            config = canais_org.meta_leads_da_linha(row, cfg)
        except CanalNaoConfigurado as exc:
            logger.error("meta-leadgen: config ilegível org=%s: %s", row.get("org_id"), exc)
            continue
        if config.page_id:
            saida[config.page_id] = config
    return saida


async def _segredo_meta(request: Request, body: bytes) -> ResolvedSecret:
    cfg = _cfg(request)
    configs = _configs_por_pagina(_admin_db(request), cfg)
    paginas = [p for p in _paginas_do_corpo(body) if p in configs]
    segredo = configs[paginas[0]].app_secret if paginas else None
    # One app signs the whole delivery; a known Page without its own secret
    # falls back to the platform app secret (already folded in by
    # `meta_leads_da_linha`). An unknown Page still verifies against the
    # platform secret so a genuine-but-unrouted delivery is not a 401 storm.
    return ResolvedSecret(
        secret=segredo or cfg.igig_meta_app_secret or None,
        extras={"configs": configs},
    )


@router.get("/meta/leadgen", response_class=PlainTextResponse)
@limiter.limit(settings.webhook_rate_limit)
async def meta_leadgen_verificar(
    request: Request,
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    admin_db: Any = Depends(get_admin_db),
    cfg: Any = Depends(get_settings),
) -> PlainTextResponse:
    """Echo `hub.challenge` (as an opaque string) iff the token matches an
    org's stored verify token — constant-time, via the seed helper."""
    for config in _configs_por_pagina(admin_db, cfg).values():
        desafio = leadgen_challenge_response(
            mode=hub_mode, verify_token=hub_verify_token, challenge=hub_challenge,
            expected_token=config.verify_token,
        )
        if desafio is not None:
            return PlainTextResponse(desafio)
    # Uniform refusal: never distinguish "unset" from "mismatch".
    logger.warning("meta-leadgen: handshake recusado (mode=%r)", hub_mode)
    return PlainTextResponse("forbidden", status_code=status.HTTP_403_FORBIDDEN)


@router.post("/meta/leadgen")
@limiter.limit(settings.webhook_rate_limit)
async def meta_leadgen_receber(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_segredo_meta,
        scheme="sha256_prefixed",
        signature_header="X-Hub-Signature-256",
        bypass_when_unset=False,
        log_prefix="igig-meta-leadgen-webhook",
    ),
    portas: PortasAutomacao = Depends(get_portas_automacao_admin),
    adaptador_para: Callable[[str], Any] = Depends(get_meta_adapter_factory),
) -> JSONResponse:
    try:
        corpo = json.loads(verified.body or b"{}")
    except (ValueError, TypeError):
        logger.warning("meta-leadgen: corpo verificado não é JSON — ignorado")
        return JSONResponse({"status": "ignorado", "motivo": "json_invalido", "resultados": []})
    eventos = parse_leadgen_webhook(corpo) if isinstance(corpo, dict) else []
    configs: dict[str, canais_org.ConfigMetaLeads] = (verified.extras or {}).get("configs") or {}
    resultados = []
    for evento in eventos:
        config = configs.get(str(evento.page_id))
        if config is None:
            logger.error("meta-leadgen: página %s não conectada a nenhuma organização — lead %s "
                         "não importado", evento.page_id, evento.leadgen_id)
            resultados.append({"leadgen_id": evento.leadgen_id, "status": "pagina_desconhecida"})
            continue
        resultados.append(await _importar(portas, config, evento, adaptador_para))
    return JSONResponse({"status": "ok", "eventos": len(eventos), "resultados": resultados})


async def _importar(
    portas: PortasAutomacao, config: canais_org.ConfigMetaLeads, evento: Any,
    adaptador_para: Callable[[str], Any],
) -> dict:
    org_id = config.org_id
    existente = fontes_lead.lead_existente(portas.db, org_id, "meta_lead_id", evento.leadgen_id)
    if existente is not None:
        return {"leadgen_id": evento.leadgen_id, "status": "existente", "lead_id": str(existente["id"])}
    try:
        if not config.page_access_token:
            raise CanalNaoConfigurado("Meta Lead Ads sem token de acesso da Página.")
        # The adapter is synchronous HTTP — off the event loop.
        adaptador = adaptador_para(config.page_access_token)
        lead_meta = await asyncio.to_thread(adaptador.get_lead, evento.leadgen_id)
        resultado = await fontes_lead.lead_da_meta(portas, org_id, evento.leadgen_id, lead_meta)
    except (MetaGraphError, CanalNaoConfigurado) as exc:
        logger.error("meta-leadgen: lead %s não importado org=%s: %s", evento.leadgen_id, org_id, exc)
        canais_org.registrar_erro(portas.db, org_id, "meta_leads",
                                  f"Lead {evento.leadgen_id} não importado: {exc}")
        return {"leadgen_id": evento.leadgen_id, "status": "erro", "detalhe": str(exc)}
    except Exception as exc:  # noqa: BLE001 — recorded on the channel + logged; Meta gets 200
        logger.exception("meta-leadgen: falha inesperada lead=%s org=%s", evento.leadgen_id, org_id)
        canais_org.registrar_erro(portas.db, org_id, "meta_leads",
                                  f"Lead {evento.leadgen_id} não importado: {type(exc).__name__}: {exc}")
        return {"leadgen_id": evento.leadgen_id, "status": "erro", "detalhe": type(exc).__name__}
    return {"leadgen_id": evento.leadgen_id, **resultado}
