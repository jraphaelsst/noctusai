"""Integrações → E-mail: the org's SMTP account + Gmail mailbox (slice B).

  GET    /api/integracoes/email/smtp                 status (NEVER the password)
  PUT    /api/integracoes/email/smtp                 create/replace (password omitted ⇒ kept)
  DELETE /api/integracoes/email/smtp                 remove the org account
  POST   /api/integracoes/email/smtp/testar {para}   send a test e-mail
  GET    /api/integracoes/email/gmail                connection + watch status
  GET    /api/integracoes/email/gmail/oauth/start    {url} — Google consent
  GET    /api/integracoes/email/gmail/oauth/callback PUBLIC — Google redirects here
  DELETE /api/integracoes/email/gmail                disconnect (+ stop the watch)

Credentials are stored in ``igig.integracao`` (canais ``smtp`` / ``gmail``),
secrets Fernet-encrypted with the cofre — see ``app/services/email_config.py``.

The OAuth callback is the one unauthenticated route: the browser arrives from
Google without a bearer token, so the org it writes to comes from the HMAC-
signed ``state`` issued by ``/oauth/start`` (10-minute TTL), never from a
query parameter the caller controls.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers (FastAPI resolves the dependency annotations at import).
import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from noctusai_lib.integrations.gmail import OAuthGmailCredentials
from noctusai_lib.security.oauth import OAuthProvider

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.email_deps import (
    EmailSenderFactory,
    GmailClientFactory,
    GmailProfileFetcher,
    get_email_sender_factory,
    get_email_settings,
    get_gmail_client_factory,
    get_gmail_oauth_provider,
    get_gmail_profile_fetcher,
)
from app.repositories import Repositorios
from app.repositories.email import repositorios_email
from app.schemas.email import SmtpIn, SmtpTesteIn
from app.services import email_config, orcamento_email
from app.services.email_config import EmailSettings
from app.services.regras import RegraViolada, http_de
from app.store import get_repositorios, get_repositorios_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integracoes/email", tags=["integracoes"])

_CALLBACK_PATH = "/api/integracoes/email/gmail/oauth/callback"


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _url_publica(cfg: EmailSettings) -> str:
    """The product's public origin (PRODUCT_URL_IGIG / PRODUCT_URL_PATTERN)."""
    if not cfg.public_url:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "URL pública do produto não configurada: defina PRODUCT_URL_IGIG "
                          "(ou PRODUCT_URL_PATTERN).",
                "code": "url_publica_ausente",
            },
        )
    return cfg.public_url.rstrip("/")


# ── SMTP ─────────────────────────────────────────────────────────────
@router.get("/smtp")
async def obter_smtp(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    return {"data": email_config.status_smtp(repos, _org(auth), cfg)}


@router.put("/smtp")
async def salvar_smtp(
    payload: SmtpIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    try:
        status = email_config.salvar_smtp(
            repos, _org(auth), cfg,
            host=payload.host, port=payload.port, username=payload.username,
            password=payload.password, security=payload.security,
            from_email=payload.from_email, from_name=payload.from_name,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return {"data": status}


@router.delete("/smtp")
async def remover_smtp(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    org_id = _org(auth)
    if not repos.integracao.desconectar(org_id, email_config.CANAL_SMTP):
        raise HTTPException(
            status_code=404,
            detail={"detail": "Nenhum SMTP próprio configurado.", "code": "smtp_nao_configurado"},
        )
    logger.info("smtp removido org=%s", org_id)
    return {"data": email_config.status_smtp(repos, org_id, cfg)}


@router.post("/smtp/testar")
async def testar_smtp(
    payload: SmtpTesteIn,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    sender_factory: EmailSenderFactory = Depends(get_email_sender_factory),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    try:
        message_id = await orcamento_email.enviar_teste(
            repos, _org(auth), payload.para, sender_factory=sender_factory, settings=cfg,
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro
    return {"data": {"message_id": message_id}}


# ── Gmail ────────────────────────────────────────────────────────────
@router.get("/gmail")
async def obter_gmail(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    return {
        "data": email_config.status_gmail(repos, repositorios_email(repos.store), _org(auth), cfg)
    }


@router.get("/gmail/oauth/start")
async def iniciar_oauth_gmail(
    auth: tuple = Depends(get_current_user_org),
    provider: Optional[OAuthProvider] = Depends(get_gmail_oauth_provider),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "OAuth do Google não configurado: defina GOOGLE_OAUTH_CLIENT_ID "
                          "e GOOGLE_OAUTH_CLIENT_SECRET.",
                "code": "oauth_nao_configurado",
            },
        )
    user, _token, _raw = auth
    try:
        state = email_config.emitir_state(_org(auth), str(user.id), cfg)
    except RegraViolada as erro:
        raise http_de(erro) from erro
    autorizacao = await provider.authorization_url(
        state=state,
        scopes=email_config.GMAIL_OAUTH_SCOPES,
        redirect_uri=f"{_url_publica(cfg)}{_CALLBACK_PATH}",
    )
    return {"data": {"url": autorizacao.url}}


def _voltar(base: str, resultado: str, motivo: Optional[str] = None) -> RedirectResponse:
    query = {"gmail": resultado}
    if motivo:
        query["motivo"] = motivo
    return RedirectResponse(url=f"{base}/integracoes?{urlencode(query)}", status_code=302)


@router.get("/gmail/oauth/callback")
async def callback_oauth_gmail(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    repos: Repositorios = Depends(get_repositorios_admin),
    provider: Optional[OAuthProvider] = Depends(get_gmail_oauth_provider),
    gmail_factory: GmailClientFactory = Depends(get_gmail_client_factory),
    fetch_profile: GmailProfileFetcher = Depends(get_gmail_profile_fetcher),
    cfg: EmailSettings = Depends(get_email_settings),
) -> RedirectResponse:
    """PUBLIC. Exchanges the code, stores the mailbox, starts the watch."""
    base = _url_publica(cfg)
    if error:
        logger.warning("gmail oauth: Google devolveu erro=%s", error)
        return _voltar(base, "erro", "consentimento_negado")
    if not code or not state:
        return _voltar(base, "erro", "parametros_ausentes")
    try:
        org_id, user_id = email_config.ler_state(state, cfg)
    except RegraViolada:
        logger.warning("gmail oauth: state inválido/expirado")
        return _voltar(base, "erro", "state_invalido")
    if provider is None:
        logger.error("gmail oauth callback sem GOOGLE_OAUTH_CLIENT_ID/SECRET org=%s", org_id)
        return _voltar(base, "erro", "oauth_nao_configurado")

    try:
        tokens = await provider.exchange_code(
            code=code, state=state, redirect_uri=f"{base}{_CALLBACK_PATH}",
        )
    except Exception:  # noqa: BLE001 — surfaced as ?gmail=erro + logged
        logger.exception("gmail oauth: troca do code falhou org=%s", org_id)
        return _voltar(base, "erro", "troca_falhou")
    if not tokens.refresh_token:
        logger.error("gmail oauth: Google não devolveu refresh_token org=%s", org_id)
        return _voltar(base, "erro", "sem_refresh_token")
    scopes = list(tokens.scope or email_config.GMAIL_OAUTH_SCOPES)
    if not email_config.pode_observar(scopes):
        logger.error("gmail oauth: escopo de leitura não concedido org=%s scopes=%s", org_id, scopes)
        return _voltar(base, "erro", "escopo_insuficiente")

    creds = OAuthGmailCredentials(
        refresh_token=tokens.refresh_token,
        client_id=cfg.google_oauth_client_id,
        client_secret=cfg.google_oauth_client_secret,
        token=tokens.access_token,
        scopes=scopes,
    )
    try:
        email = (await fetch_profile(creds)).strip().lower()
    except Exception:  # noqa: BLE001 — surfaced as ?gmail=erro + logged
        logger.exception("gmail oauth: leitura do perfil falhou org=%s", org_id)
        return _voltar(base, "erro", "perfil_falhou")
    if not email:
        return _voltar(base, "erro", "perfil_falhou")

    try:
        email_config.salvar_gmail(
            repos, org_id, cfg, email=email, refresh_token=tokens.refresh_token,
            access_token=tokens.access_token, scopes=scopes,
        )
    except RegraViolada as erro:
        logger.error("gmail oauth: não gravado org=%s — %s", org_id, erro.mensagem)
        return _voltar(base, "erro", erro.code)
    logger.info("gmail conectado org=%s por user=%s mailbox=%s", org_id, user_id, email)
    await orcamento_email.iniciar_watch(
        repos, repositorios_email(repos.store), org_id, email, gmail_factory(creds), cfg,
    )
    return _voltar(base, "ok")


@router.delete("/gmail")
async def desconectar_gmail(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
    gmail_factory: GmailClientFactory = Depends(get_gmail_client_factory),
    cfg: EmailSettings = Depends(get_email_settings),
) -> dict:
    org_id = _org(auth)
    erepos = repositorios_email(repos.store)
    resolvido = email_config.credenciais_gmail(repos, org_id, cfg)
    if resolvido is None and repos.integracao.por_canal(org_id, email_config.CANAL_GMAIL) is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Gmail não conectado.", "code": "gmail_nao_conectado"},
        )
    if resolvido is not None:
        try:
            await gmail_factory(resolvido[0]).stop()
        except Exception:  # noqa: BLE001 — disconnect proceeds; the watch lapses in ≤7d
            logger.exception("gmail stop falhou org=%s — o watch expira sozinho em até 7 dias", org_id)
    erepos.watches.remover_da_org(org_id)
    repos.integracao.desconectar(org_id, email_config.CANAL_GMAIL)
    logger.info("gmail desconectado org=%s", org_id)
    return {"data": email_config.status_gmail(repos, erepos, org_id, cfg)}
