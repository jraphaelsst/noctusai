"""E-mail configuration for an org — SMTP account + Gmail mailbox (slice B).

Everything here is FastAPI-free (routers, the renewal job and tests call it
alike) and raises :class:`RegraViolada` for a refusal the UI must see.

SMTP — stored in ``integracao`` canal ``smtp``:
  * ``config`` (non-secret JSONB): host, port, username, security, from_email,
    from_name;
  * ``token_cifrado``: the password, Fernet-encrypted with the cofre key.
  Resolution is org row → EXPLICIT platform fallback (``SMTP_HOST/PORT/USER/
  PASSWORD``) → refusal. The fallback is logged at WARNING on every use and
  surfaced as ``origem: "plataforma"`` so an operator can see whose account a
  lead's e-mail actually leaves from — never a silent substitution.

Gmail — stored in ``integracao`` canal ``gmail``:
  * ``token_cifrado``: Fernet(JSON ``{refresh_token, access_token, scopes}``);
  * ``conta_externa`` / ``config.email``: the mailbox address.
  The OAuth client id/secret are NOT in the bundle — they belong to the GCP
  OAuth app and come from config (same rule as social-wiring's
  ``build_gmail_client_for``: a credential built from the bundle alone cannot
  refresh and dies an hour later).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.email import SmtpConfig
from noctusai_lib.integrations.email.errors import EmailNotConfigured
from noctusai_lib.integrations.gmail import (
    GMAIL_METADATA_SCOPE,
    GMAIL_READONLY_SCOPE,
    GMAIL_SEND_SCOPE,
    OAuthGmailCredentials,
)
from noctusai_lib.security.encrypted_tokens import decrypt, encrypt

from app.repositories import Repositorios
from app.repositories.email import RepositoriosEmail
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = [
    "GMAIL_OAUTH_SCOPES",
    "EmailSettings",
    "GmailPushConfig",
    "chave_cofre",
    "status_smtp",
    "salvar_smtp",
    "resolver_smtp",
    "gcp_config",
    "salvar_gmail",
    "credenciais_gmail",
    "status_gmail",
    "emitir_state",
    "ler_state",
]

CANAL_SMTP = "smtp"
CANAL_GMAIL = "gmail"

#: `gmail.readonly` covers watch/history/metadata; `gmail.send` keeps the
#: grant aligned with social-wiring's connect flow (same consent screen).
GMAIL_OAUTH_SCOPES = [GMAIL_SEND_SCOPE, GMAIL_READONLY_SCOPE]
_WATCH_SCOPES = frozenset({GMAIL_READONLY_SCOPE, GMAIL_METADATA_SCOPE})

_STATE_TTL_SECONDS = 600
_STATE_CONTEXTO = b"igig.gmail.oauth.state.v1|"


# ── settings snapshot (the DI seam) ──────────────────────────────────
@dataclass(frozen=True)
class EmailSettings:
    """Everything this slice reads from config, as one injected value.

    Routers receive it through ``app.email_deps.get_email_settings`` (tests
    override THAT dependency); the renewal job builds it the same way. No
    function here reads the global settings object directly.
    """

    cofre_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    gmail_push_gcp_project: str = ""
    gmail_push_topic: str = ""
    gmail_push_audience: str = ""
    gmail_push_service_account: str = ""
    #: The product's public origin (PRODUCT_URL_IGIG / PRODUCT_URL_PATTERN);
    #: None when unresolvable — the OAuth routes answer 503 then.
    public_url: str | None = None

    @classmethod
    def de(cls, settings: Any, public_url: str | None) -> "EmailSettings":
        return cls(
            cofre_key=settings.igig_cofre_key,
            smtp_host=settings.smtp_host,
            smtp_port=int(settings.smtp_port or 465),
            smtp_user=settings.smtp_user,
            smtp_password=settings.smtp_password,
            smtp_security=settings.smtp_security,
            smtp_from_email=settings.smtp_from_email,
            smtp_from_name=settings.smtp_from_name,
            google_oauth_client_id=settings.google_oauth_client_id,
            google_oauth_client_secret=settings.google_oauth_client_secret,
            gmail_push_gcp_project=settings.gmail_push_gcp_project,
            gmail_push_topic=settings.gmail_push_topic,
            gmail_push_audience=settings.gmail_push_audience,
            gmail_push_service_account=settings.gmail_push_service_account,
            public_url=public_url,
        )


# ── cofre ────────────────────────────────────────────────────────────
def chave_cofre(settings: EmailSettings) -> bytes:
    """The Fernet key, or a loud 409 — same contract as the Cofre."""
    if not settings.cofre_key:
        raise RegraViolada(
            409, "cofre_nao_configurado",
            "Criptografia não configurada: defina IGIG_COFRE_KEY. "
            "Nenhuma credencial é gravada em texto puro.",
        )
    return settings.cofre_key.encode("utf-8")


# ── SMTP ─────────────────────────────────────────────────────────────
def _seguranca_padrao(porta: int) -> str:
    return "ssl" if int(porta) == 465 else "starttls"


def _smtp_plataforma(settings: EmailSettings) -> dict[str, Any] | None:
    """The platform fallback, as `SmtpConfig.from_credentials` keys — or None."""
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        return None
    porta = int(settings.smtp_port or 465)
    return {
        "smtp_host": settings.smtp_host,
        "smtp_port": porta,
        "smtp_username": settings.smtp_user,
        "smtp_password": settings.smtp_password,
        "smtp_security": (settings.smtp_security or _seguranca_padrao(porta)).lower(),
        "email_from": settings.smtp_from_email or settings.smtp_user,
        "email_from_name": settings.smtp_from_name,
    }


def _publico(configurado: bool, origem: str, cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = cfg or {}
    return {
        "configurado": configurado,
        "origem": origem,
        "host": cfg.get("host"),
        "port": cfg.get("port"),
        "username": cfg.get("username"),
        "security": cfg.get("security"),
        "from_email": cfg.get("from_email"),
        "from_name": cfg.get("from_name"),
    }


def status_smtp(repos: Repositorios, org_id: str, settings: EmailSettings) -> dict[str, Any]:
    """The GET shape. NEVER carries the password."""
    registro = repos.integracao.por_canal(org_id, CANAL_SMTP)
    if registro is not None and registro.get("token_cifrado"):
        return _publico(bool(registro.get("ativo")), "org", registro.get("config") or {})
    plataforma = _smtp_plataforma(settings)
    if plataforma is not None:
        return _publico(True, "plataforma", {
            "host": plataforma["smtp_host"],
            "port": plataforma["smtp_port"],
            "username": plataforma["smtp_username"],
            "security": plataforma["smtp_security"],
            "from_email": plataforma["email_from"],
            "from_name": plataforma["email_from_name"] or None,
        })
    return _publico(False, "nenhuma", None)


def salvar_smtp(
    repos: Repositorios,
    org_id: str,
    settings: EmailSettings,
    *,
    host: str,
    port: int,
    username: str,
    password: str | None,
    security: str,
    from_email: str,
    from_name: str | None,
) -> dict[str, Any]:
    """Create or replace the org's SMTP account. ``password=None`` keeps it."""
    chave = chave_cofre(settings)
    config = {
        "host": host.strip(),
        "port": int(port),
        "username": username.strip(),
        "security": security,
        "from_email": from_email.strip(),
        "from_name": (from_name or "").strip() or None,
    }
    atual = repos.integracao.por_canal(org_id, CANAL_SMTP)
    if password:
        atual = repos.integracao.conectar(
            org_id, CANAL_SMTP, token=password, chave=chave, conta_externa=config["from_email"],
        )
    elif atual is None or not atual.get("token_cifrado"):
        raise RegraViolada(422, "senha_obrigatoria", "Informe a senha do SMTP.")
    repos.integracao.atualizar(org_id, str(atual["id"]), {
        "config": config, "conta_externa": config["from_email"], "ativo": True, "ultimo_erro": None,
    })
    logger.info("smtp configurado org=%s host=%s", org_id, config["host"])
    return status_smtp(repos, org_id, settings)


def resolver_smtp(
    repos: Repositorios, org_id: str, settings: EmailSettings
) -> tuple[SmtpConfig, str]:
    """``(SmtpConfig, origem)`` for a send, or a 409 naming what is missing."""
    registro = repos.integracao.por_canal(org_id, CANAL_SMTP)
    if registro is not None and registro.get("token_cifrado") and registro.get("ativo"):
        cfg = registro.get("config") or {}
        senha = decrypt(str(registro["token_cifrado"]), chave_cofre(settings))
        credenciais = {
            "smtp_host": cfg.get("host"),
            "smtp_port": cfg.get("port"),
            "smtp_username": cfg.get("username"),
            "smtp_password": senha,
            "smtp_security": cfg.get("security"),
            "email_from": cfg.get("from_email"),
            "email_from_name": cfg.get("from_name"),
        }
        origem = "org"
    else:
        credenciais = _smtp_plataforma(settings)
        if credenciais is None:
            raise RegraViolada(
                409, "smtp_nao_configurado",
                "Nenhum SMTP configurado: cadastre uma conta em Integrações → E-mail.",
            )
        logger.warning(
            "smtp: org=%s sem SMTP próprio — usando o SMTP da PLATAFORMA (%s)",
            org_id, credenciais["smtp_host"],
        )
        origem = "plataforma"
    try:
        return SmtpConfig.from_credentials(credenciais), origem
    except (EmailNotConfigured, ValueError) as erro:
        raise RegraViolada(409, "smtp_nao_configurado", f"SMTP incompleto: {erro}") from erro


# ── Gmail ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GmailPushConfig:
    project: str
    topic: str  # full resource name
    audience: str
    service_account: str


def gcp_config(settings: EmailSettings) -> GmailPushConfig | None:
    """The Pub/Sub push config, or None when ANY piece is missing."""
    projeto = settings.gmail_push_gcp_project.strip()
    topico = settings.gmail_push_topic.strip()
    audience = settings.gmail_push_audience.strip()
    conta = settings.gmail_push_service_account.strip()
    if not (projeto and topico and audience and conta):
        return None
    if not topico.startswith("projects/"):
        topico = f"projects/{projeto}/topics/{topico}"
    return GmailPushConfig(project=projeto, topic=topico, audience=audience, service_account=conta)


def gcp_faltando(settings: EmailSettings) -> list[str]:
    """Env names still unset — for the loud log / status message."""
    return [
        nome for nome, valor in (
            ("GMAIL_PUSH_GCP_PROJECT", settings.gmail_push_gcp_project),
            ("GMAIL_PUSH_TOPIC", settings.gmail_push_topic),
            ("GMAIL_PUSH_AUDIENCE", settings.gmail_push_audience),
            ("GMAIL_PUSH_SERVICE_ACCOUNT", settings.gmail_push_service_account),
        ) if not valor.strip()
    ]


def oauth_configurado(settings: EmailSettings) -> bool:
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def salvar_gmail(
    repos: Repositorios,
    org_id: str,
    settings: EmailSettings,
    *,
    email: str,
    refresh_token: str,
    access_token: str | None,
    scopes: list[str],
) -> dict[str, Any]:
    chave = chave_cofre(settings)
    bundle = json.dumps({
        "refresh_token": refresh_token, "access_token": access_token, "scopes": scopes,
    })
    registro = repos.integracao.conectar(
        org_id, CANAL_GMAIL, token=bundle, chave=chave, conta_externa=email.lower(),
    )
    return repos.integracao.atualizar(org_id, str(registro["id"]), {
        "config": {"email": email.lower(), "scopes": scopes},
    })


def credenciais_gmail(
    repos: Repositorios, org_id: str, settings: EmailSettings
) -> tuple[OAuthGmailCredentials, str] | None:
    """``(credentials, mailbox)`` for the org's connected Gmail, else None.

    None when not connected OR when the OAuth app is not configured (a
    credential without client id/secret cannot refresh — logged).
    """
    registro = repos.integracao.por_canal(org_id, CANAL_GMAIL)
    if registro is None or not registro.get("token_cifrado") or not registro.get("ativo"):
        return None
    if not oauth_configurado(settings):
        logger.warning(
            "gmail: org=%s conectado mas GOOGLE_OAUTH_CLIENT_ID/SECRET ausentes — "
            "credencial não renovável, caixa indisponível", org_id,
        )
        return None
    bundle = json.loads(decrypt(str(registro["token_cifrado"]), chave_cofre(settings)))
    scopes = list(bundle.get("scopes") or GMAIL_OAUTH_SCOPES)
    creds = OAuthGmailCredentials(
        refresh_token=bundle["refresh_token"],
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        token=bundle.get("access_token"),
        scopes=scopes,
    )
    email = str((registro.get("config") or {}).get("email") or registro.get("conta_externa") or "")
    return creds, email


def pode_observar(scopes: list[str]) -> bool:
    return bool(_WATCH_SCOPES.intersection(scopes))


def status_gmail(
    repos: Repositorios, erepos: RepositoriosEmail, org_id: str, settings: EmailSettings
) -> dict[str, Any]:
    registro = repos.integracao.por_canal(org_id, CANAL_GMAIL)
    conectado = bool(registro and registro.get("token_cifrado") and registro.get("ativo"))
    email = None
    watch_ativo = False
    expira_em = None
    if conectado and registro is not None:
        email = (registro.get("config") or {}).get("email") or registro.get("conta_externa")
        watch = erepos.watches.por_email(org_id, str(email)) if email else None
        if watch is not None and watch.get("expiration"):
            expira_em = str(watch["expiration"])
            watch_ativo = _parse_dt(expira_em) > datetime.now(timezone.utc)
    return {
        "conectado": conectado,
        "email": email,
        "watch_ativo": watch_ativo,
        "expira_em": expira_em,
        "configuracao_gcp_ok": gcp_config(settings) is not None,
        "ultimo_erro": registro.get("ultimo_erro") if registro else None,
    }


def _parse_dt(valor: str) -> datetime:
    dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── OAuth state — stateless, signed, expiring ────────────────────────
def _assinar(payload: bytes, chave: bytes) -> str:
    mac = hmac.new(chave, _STATE_CONTEXTO + payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def emitir_state(org_id: str, user_id: str, settings: EmailSettings) -> str:
    """``<payload>.<mac>`` binding org + user, valid for 10 minutes.

    The callback is PUBLIC (Google redirects the browser, which carries no
    bearer token), so the org it writes to must come from something the
    caller cannot forge — an HMAC under the cofre key, not a plain
    ``{org_id}:{nonce}`` string.
    """
    corpo = json.dumps({
        "o": org_id, "u": user_id, "n": secrets.token_urlsafe(12),
        "e": int(time.time()) + _STATE_TTL_SECONDS,
    }, separators=(",", ":")).encode("utf-8")
    payload = base64.urlsafe_b64encode(corpo).rstrip(b"=").decode("ascii")
    return f"{payload}.{_assinar(payload.encode('ascii'), chave_cofre(settings))}"


def ler_state(state: str, settings: EmailSettings) -> tuple[str, str]:
    """``(org_id, user_id)`` from a state this service issued. Raises
    :class:`RegraViolada` (400 ``state_invalido``) on anything else."""
    invalido = RegraViolada(400, "state_invalido", "Estado OAuth inválido ou expirado.")
    payload, sep, mac = (state or "").partition(".")
    if not sep or not payload or not mac:
        raise invalido
    if not hmac.compare_digest(mac, _assinar(payload.encode("ascii"), chave_cofre(settings))):
        raise invalido
    try:
        corpo = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError) as erro:
        raise invalido from erro
    if int(corpo.get("e", 0)) < int(time.time()):
        raise invalido
    return str(corpo["o"]), str(corpo["u"])
