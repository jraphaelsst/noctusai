"""Lead-source setup — the Integrações cards for WhatsApp (WAHA) and Meta Lead Ads
(contract §E2).

  GET /api/integracoes/leads/whatsapp    status + the webhook URL to paste in WAHA
  PUT /api/integracoes/leads/whatsapp    {base_url, api_key?, session?}   (org admins)
  GET /api/integracoes/leads/meta        status + the callback URL for the Meta app
  PUT /api/integracoes/leads/meta        {page_id, verify_token?, page_access_token?, app_secret?}
                                         (org admins)

WAHA is configured like social-wiring's connection (base url + api key +
session; the inbound webhook is `/api/webhooks/waha/{token}` with a per-org
opaque token, HMAC under the platform's `IGIG_WAHA_WEBHOOK_HMAC_SECRET`).

**No response ever carries a secret** — only `*_configurado` booleans, the same
rule as `integracoes_router`. Secrets are Fernet-encrypted under
`IGIG_COFRE_KEY`; with no key the PUT refuses (409) rather than store
plaintext. A secret omitted on PUT keeps the stored one.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.primitives.responses import success_response

from app.config import get_settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import exigir_admin_da_org, get_admin_db, get_db
from app.schemas.automacoes import LeadsMetaIn, LeadsWhatsappIn
from app.services import canais_org
from app.services.canais_org import CanalNaoConfigurado

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integracoes/leads", tags=["integracoes-leads"])

#: The product slug `resolve_product_url` keys on (`PRODUCT_URL_IGIG`).
_PRODUCT_SLUG = "igig"
_WAHA_WEBHOOK = "/api/webhooks/waha/{token}"
_META_WEBHOOK = "/api/webhooks/meta/leadgen"


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _url_publica(caminho: str) -> tuple[str | None, str | None]:
    """`(url, erro)` — the absolute webhook URL, or why it cannot be built.

    A missing `PRODUCT_URL_IGIG` is surfaced to the setup screen as a message,
    never replaced by a guessed host (a wrong URL pasted into WAHA/Meta fails
    silently on THEIR side).
    """
    try:
        return f"{resolve_product_url(_PRODUCT_SLUG)}{caminho}", None
    except ValueError as exc:
        logger.warning("integrações-leads: URL pública indisponível: %s", exc)
        return None, "URL pública do IgIg não configurada (PRODUCT_URL_IGIG)."


def _conflito(exc: CanalNaoConfigurado) -> HTTPException:
    return HTTPException(status_code=409, detail={"detail": str(exc), "code": "cofre_nao_configurado"})


# ── WhatsApp (WAHA) ──────────────────────────────────────────────────
def _whatsapp_out(row: dict | None, cfg: Any) -> dict:
    config = (row or {}).get("config") or {}
    token = config.get("webhook_token")
    url, erro_url = _url_publica(_WAHA_WEBHOOK.format(token=token)) if token else (None, None)
    return {
        "configurado": bool(row and row.get("ativo") and config.get("base_url")),
        "base_url": config.get("base_url"),
        "session": config.get("session") or "default",
        "api_key_configurada": bool((row or {}).get("token_cifrado")),
        "webhook_url": url,
        "webhook_url_erro": erro_url,
        "hmac_configurado": bool(cfg.igig_waha_webhook_hmac_secret),
        "cofre_configurado": bool(cfg.igig_cofre_key),
        "conectado_em": (row or {}).get("conectado_em"),
        "ultimo_erro": (row or {}).get("ultimo_erro"),
    }


@router.get("/whatsapp")
async def obter_whatsapp(
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    cfg: Any = Depends(get_settings),
) -> dict:
    return success_response(_whatsapp_out(canais_org.integracao(db, _org(auth), "whatsapp"), cfg))


@router.put("/whatsapp", dependencies=[Depends(exigir_admin_da_org)])
async def salvar_whatsapp(
    payload: LeadsWhatsappIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    cfg: Any = Depends(get_settings),
) -> dict:
    org_id = _org(auth)
    atual = canais_org.integracao(db, org_id, "whatsapp")
    config_atual = (atual or {}).get("config") or {}
    try:
        token_cifrado = (
            canais_org.cifrar(payload.api_key, canais_org.chave_cofre(cfg)) if payload.api_key else None
        )
    except CanalNaoConfigurado as exc:
        raise _conflito(exc) from exc
    # The routing token is minted ONCE and kept across edits: rotating it on
    # every save would silently break the URL already pasted into WAHA.
    # `<org_id>.<secret>` — the org rides in the token so the public webhook
    # resolves its tenant without a cross-org scan (the approval-portal shape).
    webhook_token = config_atual.get("webhook_token") or f"{org_id}.{secrets.token_urlsafe(32)}"
    row = canais_org.salvar_integracao(
        db, org_id, "whatsapp",
        config={
            "base_url": payload.base_url.rstrip("/"),
            "session": payload.session,
            "webhook_token": webhook_token,
        },
        token_cifrado=token_cifrado,
        conta_externa=payload.session,
    )
    logger.info("whatsapp (leads) configurado org=%s", org_id)
    return success_response(_whatsapp_out(row, cfg))


# ── Meta Lead Ads ────────────────────────────────────────────────────
def _meta_out(row: dict | None, cfg: Any) -> dict:
    config = (row or {}).get("config") or {}
    url, erro_url = _url_publica(_META_WEBHOOK)
    if config.get("app_secret_cifrado"):
        origem = "org"
    elif cfg.igig_meta_app_secret:
        origem = "plataforma"
    else:
        origem = "nenhuma"
    return {
        "configurado": bool(row and row.get("ativo") and config.get("page_id") and row.get("token_cifrado")),
        "page_id": config.get("page_id"),
        "verify_token_configurado": bool(config.get("verify_token_cifrado")),
        "page_access_token_configurado": bool((row or {}).get("token_cifrado")),
        "app_secret_configurado": origem != "nenhuma",
        "app_secret_origem": origem,
        "webhook_url": url,
        "webhook_url_erro": erro_url,
        "cofre_configurado": bool(cfg.igig_cofre_key),
        "conectado_em": (row or {}).get("conectado_em"),
        "ultimo_erro": (row or {}).get("ultimo_erro"),
    }


@router.get("/meta")
async def obter_meta(
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    cfg: Any = Depends(get_settings),
) -> dict:
    return success_response(_meta_out(canais_org.integracao(db, _org(auth), "meta_leads"), cfg))


@router.put("/meta", dependencies=[Depends(exigir_admin_da_org)])
async def salvar_meta(
    payload: LeadsMetaIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    admin_db: Any = Depends(get_admin_db),
    cfg: Any = Depends(get_settings),
) -> dict:
    org_id = _org(auth)
    atual = canais_org.integracao(db, org_id, "meta_leads")
    config_atual = (atual or {}).get("config") or {}
    if not payload.verify_token and not config_atual.get("verify_token_cifrado"):
        raise HTTPException(
            status_code=422,
            detail={"detail": "Informe o verify token (usado uma vez pela Meta para validar a URL).",
                    "code": "verify_token_obrigatorio"},
        )
    if not payload.page_access_token and not (atual or {}).get("token_cifrado"):
        raise HTTPException(
            status_code=422,
            detail={"detail": "Informe o token de acesso da Página (lê os dados do lead).",
                    "code": "page_access_token_obrigatorio"},
        )
    # A Page belongs to ONE org here: the webhook routes a delivery to its org
    # by page id, so two orgs claiming the same Page would make that ambiguous.
    # Cross-org by necessity → the service-role client (RLS would only show
    # the caller's own row); it reads page ids only, nothing is returned.
    for outra in canais_org.listar_por_canal(admin_db, "meta_leads"):
        if (
            str(outra.get("org_id")) != org_id
            and str((outra.get("config") or {}).get("page_id")) == payload.page_id
        ):
            raise HTTPException(
                status_code=409,
                detail={"detail": "Esta Página já está conectada a outra organização.",
                        "code": "pagina_em_uso"},
            )
    chave = canais_org.chave_cofre(cfg)
    try:
        config = {
            "page_id": payload.page_id,
            "verify_token_cifrado": (
                canais_org.cifrar(payload.verify_token, chave) if payload.verify_token
                else config_atual.get("verify_token_cifrado")
            ),
            "app_secret_cifrado": (
                canais_org.cifrar(payload.app_secret, chave) if payload.app_secret
                else config_atual.get("app_secret_cifrado")
            ),
        }
        token_cifrado = (
            canais_org.cifrar(payload.page_access_token, chave) if payload.page_access_token else None
        )
    except CanalNaoConfigurado as exc:
        raise _conflito(exc) from exc
    row = canais_org.salvar_integracao(
        db, org_id, "meta_leads", config=config, token_cifrado=token_cifrado,
        conta_externa=payload.page_id,
    )
    logger.info("meta lead ads configurado org=%s page=%s", org_id, payload.page_id)
    return success_response(_meta_out(row, cfg))
