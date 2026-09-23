"""Per-org channel credentials in `igig.integracao` — the READ/WRITE half the
automations and lead sources share.

One row per `(org_id, canal)` (unique index, migration 010). Since 018 a row
carries TWO kinds of data, and they are kept apart on purpose:

* `config` (JSONB) — NON-secret settings (host, port, page id, session…),
  returned to the setup screen as-is;
* secrets — Fernet ciphertext under `IGIG_COFRE_KEY`: the channel's primary
  secret in `token_cifrado`, any extra secret as a `*_cifrado` key inside
  `config`. Nothing here ever returns a secret to an HTTP caller; the routers
  report `*_configurado: bool` instead.

Canais used here:

    whatsapp    token_cifrado = WAHA api key;
                config = {base_url, session, webhook_token}
    meta_leads  token_cifrado = Page access token;
                config = {page_id, verify_token_cifrado, app_secret_cifrado?}

SMTP is NOT here: slice B owns it (`app/services/email_config.py` —
`resolver_smtp`, the one reader + the one platform fallback); the automation
engine consumes that.

Every function takes the PostgREST client explicitly: the authenticated setup
routes pass the caller's RLS client, the public webhooks and the SLA job pass
the igig-pinned service-role client. `org_id` is filtered on every query
either way (the service-role path's tenant boundary).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.security.encrypted_tokens import decrypt, encrypt

logger = logging.getLogger(__name__)

__all__ = [
    "CanalNaoConfigurado",
    "ConfigMetaLeads",
    "ConfigWaha",
    "cifrar",
    "chave_cofre",
    "decifrar",
    "integracao",
    "listar_por_canal",
    "meta_leads_da_linha",
    "meta_leads_da_org",
    "registrar_erro",
    "salvar_integracao",
    "waha_da_org",
]


class CanalNaoConfigurado(Exception):
    """A channel an action needs is not configured for this org (or the
    stored secret cannot be read). The message is pt-BR and user-facing — the
    automation log shows it verbatim."""


# ── crypto ───────────────────────────────────────────────────────────
def chave_cofre(cfg: Any) -> Optional[bytes]:
    """`IGIG_COFRE_KEY` as bytes, or `None` when unset (callers refuse)."""
    chave = getattr(cfg, "igig_cofre_key", "") or ""
    return chave.encode("utf-8") if chave else None


def cifrar(valor: str, chave: Optional[bytes]) -> str:
    if not chave:
        raise CanalNaoConfigurado(
            "Criptografia não configurada: defina IGIG_COFRE_KEY. "
            "Nenhum segredo é gravado em texto puro."
        )
    return encrypt(valor, chave)


def decifrar(cifrado: Optional[str], chave: Optional[bytes], *, rotulo: str) -> Optional[str]:
    """Plaintext of a stored secret; `None` when nothing is stored.

    A stored secret that cannot be decrypted (rotated/missing key) raises —
    reading it as "not configured" would hide a broken vault behind a
    misleading setup screen.
    """
    if not cifrado:
        return None
    if not chave:
        raise CanalNaoConfigurado(
            f"{rotulo}: existe um segredo gravado, mas IGIG_COFRE_KEY não está definida."
        )
    try:
        return decrypt(str(cifrado), chave)
    except ValueError as exc:
        raise CanalNaoConfigurado(
            f"{rotulo}: o segredo gravado não pôde ser lido (chave do cofre trocada?)."
        ) from exc


# ── rows ─────────────────────────────────────────────────────────────
def integracao(db: Any, org_id: str, canal: str) -> Optional[dict]:
    linhas = (
        db.table("integracao").select("*").eq("org_id", org_id).eq("canal", canal)
        .execute().data or []
    )
    return linhas[0] if linhas else None


def listar_por_canal(db: Any, canal: str) -> list[dict]:
    """Every org's row for `canal` — SERVICE-ROLE callers only (the Meta
    webhook routes by page id / verify token before it knows the org).

    One row per org per canal, so the set is bounded by the number of orgs
    that configured this channel — never a product-data scan.
    """
    return list(
        db.table("integracao").select("*").eq("canal", canal).eq("ativo", True).execute().data
        or []
    )


def salvar_integracao(
    db: Any,
    org_id: str,
    canal: str,
    *,
    config: dict,
    token_cifrado: Optional[str] = None,
    conta_externa: Optional[str] = None,
) -> dict:
    """Create or replace the org's row for `canal`.

    `token_cifrado=None` KEEPS the stored secret (the setup form omits a
    password it does not want to change) — the contract's "omitted ⇒ keep".
    """
    valores: dict[str, Any] = {
        "config": config,
        "conta_externa": conta_externa,
        "ativo": True,
        "ultimo_erro": None,
        "conectado_em": datetime.now(timezone.utc).isoformat(),
    }
    if token_cifrado is not None:
        valores["token_cifrado"] = token_cifrado
    atual = integracao(db, org_id, canal)
    if atual is not None:
        linhas = (
            db.table("integracao").update(valores).eq("id", atual["id"]).eq("org_id", org_id)
            .execute().data or []
        )
    else:
        linhas = (
            db.table("integracao").insert({"org_id": org_id, "canal": canal, **valores})
            .execute().data or []
        )
    if not linhas:
        raise RuntimeError(f"gravação de integracao ({canal}) não retornou a linha")
    return linhas[0]


def registrar_erro(db: Any, org_id: str, canal: str, erro: str) -> None:
    """Stamp `ultimo_erro` so the Integrações card can say what failed.

    Best-effort by design — it runs INSIDE an error path; a failure to record
    is logged at ERROR with the original error, never raised over it.
    """
    try:
        atual = integracao(db, org_id, canal)
        if atual is None:
            logger.error("erro de %s sem integração gravada org=%s: %s", canal, org_id, erro)
            return
        db.table("integracao").update({"ultimo_erro": erro[:1000]}).eq("id", atual["id"]).eq(
            "org_id", org_id
        ).execute()
    except Exception:  # noqa: BLE001 — the caller is already handling `erro`
        logger.exception("falha ao gravar ultimo_erro org=%s canal=%s erro=%s", org_id, canal, erro)


# ── WhatsApp (WAHA) ──────────────────────────────────────────────────
@dataclass(frozen=True)
class ConfigWaha:
    base_url: str
    api_key: Optional[str]
    session: str
    webhook_token: Optional[str]


def waha_da_org(db: Any, org_id: str, cfg: Any) -> ConfigWaha:
    """The org's WAHA connection, decrypted. Raises `CanalNaoConfigurado`."""
    row = integracao(db, org_id, "whatsapp")
    config = (row or {}).get("config") or {}
    if row is None or not row.get("ativo") or not config.get("base_url"):
        raise CanalNaoConfigurado(
            "WhatsApp (WAHA) não configurado — Integrações › WhatsApp."
        )
    return ConfigWaha(
        base_url=str(config["base_url"]),
        api_key=decifrar(row.get("token_cifrado"), chave_cofre(cfg), rotulo="WhatsApp"),
        session=str(config.get("session") or "default"),
        webhook_token=config.get("webhook_token"),
    )


# ── Meta Lead Ads ────────────────────────────────────────────────────
@dataclass(frozen=True)
class ConfigMetaLeads:
    org_id: str
    page_id: str
    page_access_token: Optional[str]
    verify_token: Optional[str]
    app_secret: Optional[str]
    #: "org" | "plataforma" | "nenhuma" — where `app_secret` came from.
    app_secret_origem: str


def meta_leads_da_linha(row: dict, cfg: Any) -> ConfigMetaLeads:
    config = row.get("config") or {}
    chave = chave_cofre(cfg)
    app_secret = decifrar(config.get("app_secret_cifrado"), chave, rotulo="Meta Lead Ads")
    origem = "org" if app_secret else "nenhuma"
    if not app_secret and getattr(cfg, "igig_meta_app_secret", ""):
        app_secret = cfg.igig_meta_app_secret
        origem = "plataforma"
    return ConfigMetaLeads(
        org_id=str(row["org_id"]),
        page_id=str(config.get("page_id") or ""),
        page_access_token=decifrar(row.get("token_cifrado"), chave, rotulo="Meta Lead Ads"),
        verify_token=decifrar(config.get("verify_token_cifrado"), chave, rotulo="Meta Lead Ads"),
        app_secret=app_secret,
        app_secret_origem=origem,
    )


def meta_leads_da_org(db: Any, org_id: str, cfg: Any) -> ConfigMetaLeads:
    row = integracao(db, org_id, "meta_leads")
    if row is None or not row.get("ativo"):
        raise CanalNaoConfigurado("Meta Lead Ads não configurado — Integrações › Meta Lead Ads.")
    return meta_leads_da_linha(row, cfg)
