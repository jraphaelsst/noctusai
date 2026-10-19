"""Julia (Lais lead agent) -- connection/chat policy, shared by the webhook
router, the lead worker and the `/api/lais/agente` routes.

Contract: products/social-wiring/projects/lais/specs/julia-agent-contract.md
(precedence section 11 > 10 > 1-9). Everything here is either pure or takes its
IO collaborators as arguments, so the webhook, the worker and the tests share ONE
implementation of each rule:

  * routing keys / buffer key                       (section 5, 10.2 B2)
  * the switch: invariants + the 11.1 snapshot      (5, 10.1 H1/H3, 11.1)
  * eligibility of a chat for Julia                 (11.1)
  * the sliding-window limiter                      (10.1 M4)
  * own-echo registry for human takeover            (10.1 L3, 10.2 B4)
  * disclosure bubble                               (11.3)
  * handoff notification target + notification      (11.4)
  * deletion on request                             (10.1 M5)
  * the org's `agents` token + link-health memory   (section 4/5, 3.1 table)
"""
from __future__ import annotations

import html
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.api.auth.session.scopes import ADMIN_ORG_ROLES, resolve_org_membership
from noctusai_lib.config.deploy_config import is_deploy_context
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.integrations.redis import make_redis_client
from noctusai_lib.primitives.accents import fold_accents_ascii
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import AgentsClient, make_agents_client
from app.services import lais_aviso_service, lais_contatos_service

logger = logging.getLogger(__name__)

SCHEMA = "social_wiring"
DEFAULT_AGENT_KEY = "lead-imob"
AGENTS_KEY_NAME = "agents"  # `api_key:agents` in the per-org credentials store
HANDOFF_KIND = "lais_handoff"
MOTIVO_MAX = 280

SNAPSHOT_TABLE = "lais_agente_chats_preexistentes"
SNAPSHOT_PAGE = 100
SNAPSHOT_MAX_PAGES = 500
_INSERT_BATCH = 500

LEAD_PREFIX = "lead:"

#: Deletion-on-request phrase (accent/case-insensitive "contains").
_DELETION_RE = re.compile(r"\bapagar\s+(meus|os)\s+dados\b")


# ── buffer key / chat identity ──────────────────────────────────────────────
def lead_key(connection_id: UUID | str, chat_id: str) -> str:
    return f"{LEAD_PREFIX}{connection_id}:{chat_id}"


def parse_lead_key(key: str) -> Optional[tuple[UUID, str]]:
    """`lead:<connection_id>:<chat_id>` -> (connection_id, chat_id); None if foreign."""
    if not key.startswith(LEAD_PREFIX):
        return None
    rest = key[len(LEAD_PREFIX):]
    cid, sep, chat_id = rest.partition(":")
    if not sep or not chat_id:
        return None
    try:
        return UUID(cid), chat_id
    except ValueError:
        return None


def is_group_chat(chat_id: str | None) -> bool:
    return (chat_id or "").strip().lower().endswith("@g.us")


def is_lid(chat_id: str) -> bool:
    return (chat_id or "").strip().lower().endswith("@lid")


def phone_digits(chat_id: str) -> Optional[str]:
    """Digits of a phone-form chat id (`<digits>@c.us` / `@s.whatsapp.net`), else None."""
    raw = (chat_id or "").strip().lower()
    for suffix in ("@c.us", "@s.whatsapp.net"):
        if raw.endswith(suffix):
            digits = raw[: -len(suffix)].lstrip("+")
            return digits if digits.isdigit() else None
    return None


def digits_of_phone_like(value: str) -> Optional[str]:
    """Digits of `+5511...`, `5511...` or a phone JID; None for anything else."""
    d = phone_digits(value)
    if d:
        return d
    bare = (value or "").strip().lstrip("+")
    return bare if bare.isdigit() else None


def phone_forms(digits: str) -> tuple[str, str]:
    return f"{digits}@c.us", f"{digits}@s.whatsapp.net"


def chat_aliases(chat_id: str) -> set[str]:
    """Every identifier form of the SAME chat that needs no network: the id itself
    plus its other phone-JID suffix."""
    out = {chat_id}
    d = phone_digits(chat_id)
    if d:
        out.update(phone_forms(d))
    return out


def is_deletion_request(text: str) -> bool:
    return bool(_DELETION_RE.search(fold_accents_ascii(text or "").lower()))


def sanitize_motivo(motivo: str | None) -> str:
    """Plain text <= 280 chars, control characters dropped (contract 10.1 M3)."""
    cleaned = "".join(ch for ch in (motivo or "") if ch.isprintable() or ch in "\n\t")
    return " ".join(cleaned.split())[:MOTIVO_MAX]


#: The CLOSED vocabulary of a human handoff's reason (maya-blocks CONTRACT §3.2): the `handoff` Lais event carries
#: one of these, never the model's free text. Owner-refinable; a new code is a new entry here.
MOTIVOS_HANDOFF: tuple[str, ...] = ("pedido_do_lead", "fora_do_escopo", "reclamacao", "outro")
#: First match wins, in this order (a complaint that also asks for a person is a complaint).
_MOTIVO_HANDOFF_SINAIS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reclamacao", ("reclam", "insatisf", "procon", "absurd", "pessimo", "descaso", "irritad", "revoltad")),
    ("pedido_do_lead", ("pediu", "pedido do lead", "pede para", "quer falar", "falar com", "humano", "atendente",
                        "corretor", "uma pessoa", "alguem")),
    ("fora_do_escopo", ("escopo", "nao sei", "nao consigo", "nao posso", "fora d", "sem informac", "nao tenho")),
)


def motivo_codigo_do_handoff(motivo: str | None) -> str:
    """Map the agent's free-text handoff reason onto `MOTIVOS_HANDOFF` (accent/case-insensitive); else `outro`."""
    texto = fold_accents_ascii(motivo or "").lower()
    for codigo, sinais in _MOTIVO_HANDOFF_SINAIS:
        if any(s in texto for s in sinais):
            return codigo
    return "outro"


# ── the org's `agents` token + agents client factory ────────────────────────
def agents_token_for_org(org_id: UUID | str, *, cfg: Any = None, store: Any = None) -> Optional[str]:
    """The org's LOCAL `api_key:agents` token, or None. Local tier ONLY -- a
    platform/env fallback would let one org's token answer for another's."""
    from app.services import api_keys_store
    from app.services.credential_vault import EncryptionNotConfigured

    if store is None:
        try:
            store = api_keys_store.build_api_key_store(
                encryption_key=getattr(cfg, "encryption_key", None) if cfg is not None else None
            )
        except EncryptionNotConfigured:
            logger.warning("lais: ENCRYPTION_KEY unusable -- cannot read the agents token")
            return None
    stored = api_keys_store.read_local_api_key(store, str(org_id), AGENTS_KEY_NAME)
    return ((stored.tokens or {}).get("value") if stored else None) or None


def agents_base_url() -> Optional[str]:
    try:
        return resolve_product_url("agents")
    except ValueError:
        logger.warning("lais: cannot resolve the agents base URL (PRODUCT_URL_AGENTS unset)")
        return None


def resolve_agents_client(org_id: UUID | str, *, cfg: Any = None, store: Any = None) -> Optional[AgentsClient]:
    """The org's `AgentsClient`: real when token + URL exist; the Fake in a dev
    process (no deploy markers); `None` in prod when not configured."""
    return make_agents_client(
        token=agents_token_for_org(org_id, cfg=cfg, store=store),
        base_url=agents_base_url(),
        allow_fake=not is_deploy_context(),
    )


async def nome_do_agente(client: Optional[AgentsClient], agent_key: str = DEFAULT_AGENT_KEY) -> Optional[str]:
    """The agent's own status name (the per-org swappable persona; page 0 shows it as `status_agente.nome`).
    None when there is no client or the status call fails -- callers fall back to the default persona."""
    if client is None:
        return None
    try:
        nome = (await client.agent_status(agent_key)).nome
    except Exception as exc:  # status is cosmetic here: never block a save / render on the agents link
        logger.warning("lais: nome do agente indisponivel (%s)", type(exc).__name__)
        return None
    return (nome or "").strip() or None


# ── link health memory (what Lais > Agente shows as `erro`) ─────────────────
_LINK_ERROR_TTL_S = 7 * 24 * 3600
LINK_ERROR_MESSAGES = {
    "token_invalido": "Token do agente inválido ou expirado. Gere um novo no produto agents e cole aqui.",
    "agent_not_found": "Agente não encontrado para esta organização.",
    "agent_unavailable": "Agente inativo ou sem versão publicada.",
    "llm_not_configured": "Chave do provedor de IA ausente no produto agents.",
    "nao_configurado": "Token do agente ainda não configurado.",
    # PUT /token stored the channel token but could not hand agents its tools token (contract 2.2).
    "ferramentas_indisponiveis": "Ferramentas da Julia indisponíveis — reenvie o token.",
}


def _redis(cfg: Any):
    return make_redis_client(cfg.redis_url, decode_responses=True)


def _link_key(org_id: UUID | str) -> str:
    return f"lais:agente:link_erro:{org_id}"


def registrar_erro_link(org_id: UUID | str, codigo: str, *, cfg: Any) -> None:
    try:
        _redis(cfg).set(_link_key(org_id), codigo, ex=_LINK_ERROR_TTL_S)
    except Exception:
        logger.exception("lais: could not record the link error for org=%s", org_id)


def limpar_erro_link(org_id: UUID | str, *, cfg: Any) -> None:
    try:
        _redis(cfg).delete(_link_key(org_id))
    except Exception:
        logger.exception("lais: could not clear the link error for org=%s", org_id)


def ler_erro_link(org_id: UUID | str, *, cfg: Any) -> Optional[str]:
    try:
        codigo = _redis(cfg).get(_link_key(org_id))
    except Exception:
        logger.exception("lais: could not read the link error for org=%s", org_id)
        return None
    return LINK_ERROR_MESSAGES.get(codigo or "") if codigo else None


# ── H1 / H3 / 11.x: what must hold before Julia can be switched on ──────────
def julia_ativa_em_alguma_conexao(client: Any) -> bool:
    """True when ANY connection has Julia on. FAIL CLOSED: a lookup error answers
    True (the legacy global webhook then refuses an unsigned call — H1)."""
    try:
        rows = (
            client.table("whatsapp_connections").select("id")
            .eq("agente_leads_ativo", True).limit(1).execute().data
        )
    except Exception:
        logger.exception("lais: cannot tell whether Julia is on anywhere — failing closed")
        return True
    return bool(rows)


def exigir_hmac_configurado(cfg: Any) -> None:
    """H1: Julia never runs on an unsigned webhook. The WAHA HMAC secret is the
    product-level `waha_webhook_hmac_secret` (there is no per-connection secret)."""
    if not (getattr(cfg, "waha_webhook_hmac_secret", "") or "").strip():
        raise AppException(
            "webhook_hmac_required",
            "Configure o segredo HMAC do webhook do WAHA antes de ligar a Julia.",
            status_code=409,
        )


def exigir_autorizados(authorized_numbers: list[str] | None) -> None:
    """H3: today an empty list means 'everyone is authorized' -- Julia on over an
    empty list would hand every lead to the operator bot and its tools."""
    if not [n for n in (authorized_numbers or []) if str(n).strip()]:
        raise AppException(
            "authorized_numbers_required",
            "Informe ao menos um número autorizado (One Chat) antes de ligar a Julia.",
            status_code=409,
        )


def exigir_aviso_completo(aviso_row: dict[str, Any]) -> None:
    """11.3: the disclosure needs the controller's name; the link needs the slug."""
    if not (aviso_row.get("empresa_nome") or "").strip():
        raise AppException(
            "aviso_incompleto",
            "Preencha o nome da empresa no aviso de privacidade antes de ligar a Julia.",
            status_code=409,
        )
    if not lais_aviso_service.contem_link(aviso_row.get("mensagem_inicial") or ""):
        raise AppException(
            "aviso_incompleto",
            "A mensagem inicial precisa conter {link}.",
            status_code=409,
        )


def public_privacy_link(aviso_row: dict[str, Any]) -> str:
    """`<SW public base URL>/privacidade/<slug>` -- base URL from the product URL
    resolver, never a hard-coded domain."""
    try:
        base = resolve_product_url("social-wiring")
    except ValueError as exc:
        raise AppException(
            "url_publica_indisponivel",
            "Não foi possível resolver a URL pública do social-wiring (PRODUCT_URL_SOCIAL_WIRING).",
            status_code=409,
        ) from exc
    return f"{base.rstrip('/')}/privacidade/{aviso_row['slug']}"


def mensagem_inicial_pronta(aviso_row: dict[str, Any]) -> str:
    """11.3: the deterministic disclosure bubble, placeholders filled by SW."""
    empresa = (aviso_row.get("empresa_nome") or "").strip()
    return (
        (aviso_row.get("mensagem_inicial") or lais_aviso_service.MENSAGEM_INICIAL_PADRAO)
        .replace("{empresa}", empresa)
        .replace("{link}", public_privacy_link(aviso_row))
    )


# ── 11.4: handoff target ────────────────────────────────────────────────────
def usuario_e_admin_da_org(core_client: Any, org_id: UUID | str, user_id: UUID | str) -> bool:
    """Trusted-DB check (`public.noctus_users`, never `user_metadata`): the user is a
    member of THIS org with core role owner/admin."""
    try:
        membership = resolve_org_membership(core_client, str(user_id))
    except Exception:
        logger.exception("lais: org membership lookup failed for user=%s", user_id)
        return False
    return bool(
        membership
        and str(membership.get("org_id")) == str(org_id)
        and membership.get("org_role") in ADMIN_ORG_ROLES
    )


def exigir_destinatario_valido(core_client: Any, org_id: UUID | str, user_id: UUID | str, *, dono_id: UUID | str) -> None:
    """11.4: the connection owner is always allowed; anyone else must be owner/admin."""
    if str(user_id) == str(dono_id):
        return
    if not usuario_e_admin_da_org(core_client, org_id, user_id):
        raise AppException(
            "destinatario_invalido",
            "O destinatário do handoff precisa ser owner ou admin da organização.",
            status_code=422,
        )


def destinatario_do_handoff(core_client: Any, connection: Any) -> UUID:
    """Re-checked AT SEND TIME (11.4): a configured user who is no longer owner/admin
    (or left the org) falls back to the connection owner, and it is logged."""
    configurado = connection.agente_handoff_notificar_user_id
    if configurado is None or str(configurado) == str(connection.user_id):
        return connection.user_id
    if usuario_e_admin_da_org(core_client, connection.org_id, configurado):
        return configurado
    logger.error(
        "lais: handoff target %s is no longer owner/admin of org %s (connection %s) -- "
        "notifying the connection owner instead",
        configurado, connection.org_id, connection.id,
    )
    return connection.user_id


def notificar_handoff(
    core_client: Any, *, connection: Any, chat_id: str, titulo_chat: str | None, motivo: str | None,
    responsavel_user_id: UUID | str | None = None,
) -> int:
    """In-app notification (`write_in_app`, kind `lais_handoff`) to the target: chat
    name + escaped motivo (<= 280) + deep link. Never to the lead, never broadcast."""
    # Wave 11: when distribution already picked an attendant (BEFORE notifying), they get it -- same
    # responsavel-first tier as the wave-6 sink; otherwise the configured handoff target (11.4).
    destinatario = responsavel_user_id or destinatario_do_handoff(core_client, connection)
    nome = html.escape((titulo_chat or chat_id).strip() or chat_id)
    motivo_limpo = html.escape(sanitize_motivo(motivo))
    mensagem = f"A Julia passou a conversa com {nome} para atendimento humano."
    if motivo_limpo:
        mensagem += f" Motivo: {motivo_limpo}"
    from urllib.parse import quote

    return write_in_app(
        core_client,
        user_ids=[destinatario],
        kind=HANDOFF_KIND,
        title="Atendimento humano solicitado",
        message=mensagem,
        metadata={
            "link": f"/lais/conversas?chat={quote(chat_id, safe='')}",
            "connection_id": str(connection.id),
            "chat_id": chat_id,
        },
        org_id=connection.org_id,
    )


# ── 11.1: snapshot of chats that existed when Julia was switched on ─────────
class SnapshotFalhou(Exception):
    """The WAHA chat listing failed or could not be proven complete."""


def _jid_of_chat(chat: Any) -> Optional[str]:
    """WAHA shapes: `{"id": "<jid>"}` or `{"id": {"_serialized": "<jid>"}}`."""
    if not isinstance(chat, dict):
        return None
    raw = chat.get("id")
    if isinstance(raw, dict):
        raw = raw.get("_serialized")
    raw = (raw or "").strip() if isinstance(raw, str) else ""
    return raw or None


async def listar_todos_os_chats(waha: Any, *, page_size: int = SNAPSHOT_PAGE, max_pages: int = SNAPSHOT_MAX_PAGES) -> list[str]:
    """Every chat id of the WAHA session, paged to the END. Fails CLOSED: any listing
    error, an entry with no id, a server that ignores `offset` (a full page of ids
    already seen) or running out of pages raises `SnapshotFalhou`."""
    seen: dict[str, None] = {}
    for page_no in range(max_pages):
        try:
            page = await waha.list_chats(limit=page_size, offset=page_no * page_size)
        except Exception as exc:  # noqa: BLE001 -- any failure => fail closed, named below
            raise SnapshotFalhou(f"WAHA chat listing failed: {type(exc).__name__}") from exc
        if not isinstance(page, list):
            raise SnapshotFalhou("WAHA chat listing returned a non-list body")
        ids = [_jid_of_chat(c) for c in page]
        if any(i is None for i in ids):
            raise SnapshotFalhou("WAHA returned a chat with no id")
        fresh = [i for i in ids if i not in seen]
        if page and not fresh:
            raise SnapshotFalhou("WAHA ignored the pagination offset (page already seen)")
        for i in fresh:
            seen[i] = None
        if len(page) < page_size:
            return list(seen)
    raise SnapshotFalhou(f"chat listing not exhausted after {max_pages} pages")


def expandir_aliases(chat_ids: list[str], lids: list[dict[str, Any]]) -> list[str]:
    """Snapshot ids + the other phone suffix + the `@lid`/phone twin WAHA exposes
    (`list_lids`: `{lid, pn}`), de-duplicated, order-preserving."""
    lid_to_pn: dict[str, str] = {}
    pn_to_lids: dict[str, list[str]] = {}
    for entry in lids or []:
        lid = str((entry or {}).get("lid") or "").strip()
        pn = str((entry or {}).get("pn") or "").strip()
        d = phone_digits(pn) if pn else None
        if lid and d:
            lid_to_pn[lid] = d
            pn_to_lids.setdefault(d, []).append(lid)
    out: dict[str, None] = {}
    for cid in chat_ids:
        out[cid] = None
        d = phone_digits(cid)
        if d is None and is_lid(cid):
            d = lid_to_pn.get(cid)
        if d:
            for form in phone_forms(d):
                out[form] = None
            for lid in pn_to_lids.get(d, []):
                out[lid] = None
    return list(out)


def gravar_snapshot(client: Any, *, org_id: UUID, connection_id: UUID, chat_ids: list[str]) -> int:
    """Insert the ids not yet in the snapshot (PK (connection_id, chat_id)); returns the
    number inserted. Existing rows stay -- a chat excluded once stays excluded."""
    existing = {
        r["chat_id"]
        for r in iter_paged_rows(
            lambda a, b: client.table(SNAPSHOT_TABLE).select("chat_id")
            .eq("connection_id", str(connection_id)).order("chat_id").range(a, b).execute().data,
            id_key="chat_id", label="lais snapshot",
        )
    }
    novos = [c for c in chat_ids if c not in existing]
    now = datetime.now(timezone.utc).isoformat()
    for i in range(0, len(novos), _INSERT_BATCH):
        client.table(SNAPSHOT_TABLE).insert([
            {"org_id": str(org_id), "connection_id": str(connection_id), "chat_id": c, "capturado_em": now}
            for c in novos[i : i + _INSERT_BATCH]
        ]).execute()
    return len(novos)


def snapshot_contem(client: Any, connection_id: UUID, candidatos: set[str]) -> bool:
    if not candidatos:
        return False
    resp = (
        client.table(SNAPSHOT_TABLE).select("chat_id")
        .eq("connection_id", str(connection_id)).in_("chat_id", sorted(candidatos)).limit(1).execute()
    )
    return bool(resp.data)


# ── 11.1: eligibility ───────────────────────────────────────────────────────
def _ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Elegibilidade:
    elegivel: bool
    motivo: str  # owned | new | snapshot | chat_anterior | sem_ativado_em


async def avaliar_elegibilidade(
    *,
    client: Any,
    connection: Any,
    chat_id: str,
    chat_state: Optional[dict[str, Any]],
    resolver_alias: Optional[Callable[[str], Any]] = None,
) -> Elegibilidade:
    """Is this chat Julia's? (contract 11.1)

    * a chat Julia already owns (`agente_conversation_id`) stays eligible;
    * not in the snapshot (by ANY of its identifier forms, including the phone a
      `@lid` resolves to) AND
    * its `whatsapp_chats` row was not created before `agente_leads_ativado_em`.
    Anything uncertain (no `ativado_em`) is NOT eligible -- fail closed.
    """
    if chat_state and chat_state.get("agente_conversation_id"):
        return Elegibilidade(True, "owned")
    ativado = _ts(connection.agente_leads_ativado_em)
    if ativado is None:
        return Elegibilidade(False, "sem_ativado_em")
    candidatos = chat_aliases(chat_id)
    if is_lid(chat_id) and resolver_alias is not None:
        phone = resolver_alias(chat_id)
        if hasattr(phone, "__await__"):
            phone = await phone
        d = digits_of_phone_like(str(phone)) if phone else None
        if d:
            candidatos.update(phone_forms(d))
    if snapshot_contem(client, connection.id, candidatos):
        return Elegibilidade(False, "snapshot")
    criado = _ts((chat_state or {}).get("created_at"))
    if criado is not None and criado < ativado:
        return Elegibilidade(False, "chat_anterior")
    return Elegibilidade(True, "new")


# ── 10.1 M4: sliding-window limiter (works on the buffer's redis surface) ───
class SlidingWindowLimiter:
    """ZSET sliding window using only zadd/zrangebyscore/zrem/expire -- the surface
    the seed buffer's Redis Protocol already guarantees (real redis, FakeRedis)."""

    def __init__(self, redis: Any, *, clock: Callable[[], float] = time.time):
        self._r = redis
        self._clock = clock

    def allow(self, key: str, *, limit: int, window_s: int) -> bool:
        """Count one event if under `limit` in the last `window_s`; False = over."""
        now = self._clock()
        stale = self._r.zrangebyscore(key, "-inf", now - window_s)
        if stale:
            self._r.zrem(key, *stale)
        current = self._r.zrangebyscore(key, now - window_s, "+inf")
        if len(current) >= limit:
            return False
        self._r.zadd(key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
        self._r.expire(key, window_s + 60)
        return True


def permitir_turno(redis: Any, *, connection_id: UUID, chat_id: str, cfg: Any) -> bool:
    """Per-chat (about 10/hour) and per-connection (N/minute) limits, BEFORE agents."""
    limiter = SlidingWindowLimiter(redis)
    por_chat = limiter.allow(
        f"lais:rl:chat:{connection_id}:{chat_id}",
        limit=cfg.lais_agente_max_turns_per_chat_hour, window_s=3600,
    )
    if not por_chat:
        return False
    return limiter.allow(
        f"lais:rl:conn:{connection_id}",
        limit=cfg.lais_agente_max_turns_per_connection_minute, window_s=60,
    )


# ── 10.1 L3 / 10.2 B4: Julia's own echo vs a human typing from the phone ────
_SENDING_TTL_S = 120
_SENDING_GRACE_S = 15
_OWN_ID_TTL_S = 3600


def _sending_key(connection_id: UUID | str, chat_id: str) -> str:
    return f"lais:julia_sending:{connection_id}:{chat_id}"


def marcar_envio_em_curso(r: Any, connection_id: UUID | str, chat_id: str) -> None:
    r.set(_sending_key(connection_id, chat_id), "1", ex=_SENDING_TTL_S)


def encerrar_envio(r: Any, connection_id: UUID | str, chat_id: str) -> None:
    """Keep the flag alive a few seconds: WAHA's `fromMe` echo can trail the send."""
    r.expire(_sending_key(connection_id, chat_id), _SENDING_GRACE_S)


def registrar_envio_proprio(r: Any, provider_message_id: str | None) -> None:
    if provider_message_id:
        r.set(f"lais:julia_out:{provider_message_id}", "1", ex=_OWN_ID_TTL_S)


def eh_eco_proprio(r: Any, *, connection_id: UUID | str, chat_id: str, provider_message_id: str | None) -> bool:
    if provider_message_id and r.get(f"lais:julia_out:{provider_message_id}"):
        return True
    return bool(r.get(_sending_key(connection_id, chat_id)))


# ── 10.1 M5: deletion on request (SW side) ──────────────────────────────────
@dataclass(frozen=True)
class ResultadoApagar:
    sw_mensagens: int
    sw_contatos: int
    agents_ok: bool
    agents_apagou: bool
    lais_contatos: int = 0  # `lais_contatos` rows (+ interacoes/acoes/eventos) of the chat, contract 17


async def apagar_dados_do_chat(
    *,
    client: Any,
    connection: Any,
    chat_id: str,
    agents_client: Optional[AgentsClient],
    agent_key: str,
    buffer: Any = None,
) -> ResultadoApagar:
    """Remove SW's rows for the chat (messages, WhatsApp-sourced contact, inbox row,
    debounce memory) AND ask agents to drop its conversation + contact.

    SW's own rows are deleted regardless of what agents answers (the request is the
    data subject's); `agents_ok=False` tells the caller the agents half still has
    to be retried -- it is never swallowed."""
    from app.clients.agents import AgentsClientError, DeletionRequest

    agents_ok, agents_apagou = True, False
    if agents_client is None:
        agents_ok = False
        logger.error("lais: deletion for chat=%s -- no agents client; agents half NOT done", chat_id)
    else:
        try:
            res = await agents_client.delete_conversation_data(
                DeletionRequest(agent_key=agent_key, connection_id=str(connection.id), chat_id=chat_id)
            )
            agents_apagou = res.deleted
        except AgentsClientError:
            agents_ok = False
            logger.exception("lais: agents deletion failed for chat=%s", chat_id)

    alias = sorted(chat_aliases(chat_id))
    removed = 0
    for col in ("chat_id", "raw_sender"):
        rows = (
            client.table("conversation_messages").delete()
            .eq("connection_id", str(connection.id)).in_(col, alias).execute().data or []
        )
        removed += len(rows)

    contatos = 0
    d = phone_digits(chat_id)
    if d:
        rows = (
            client.table("contacts").delete()
            .eq("org_id", str(connection.org_id)).eq("source", "whatsapp").eq("whatsapp_phone", d)
            .execute().data or []
        )
        contatos = len(rows)

    client.table("whatsapp_chats").delete().eq("connection_id", str(connection.id)).eq(
        "org_id", str(connection.org_id)
    ).in_("chat_id", alias).execute()

    # Lais foundation rows (contato + episodes + applied actions + events): the data subject's
    # right covers them too. Not swallowed -- a failure here must be loud, the request is not done.
    lais_contatos = lais_contatos_service.apagar_do_chat(client, connection.org_id, connection.id, alias)

    if buffer is not None:
        for a in alias:
            buffer.clear_conversation(lead_key(connection.id, a))

    logger.info(
        "lais: deletion on request done conn=%s chat=%s sw_messages=%s sw_contacts=%s lais_contatos=%s agents_ok=%s",
        connection.id, chat_id, removed, contatos, lais_contatos, agents_ok,
    )
    return ResultadoApagar(removed, contatos, agents_ok, agents_apagou, lais_contatos)


MENSAGEM_APAGADO = (
    "Pronto! Apaguei os dados desta conversa. Se precisar de algo, é só escrever de novo. 🙂"
)
MENSAGEM_APAGADO_PARCIAL = (
    "Recebi seu pedido de apagar os dados. Já removi o histórico desta conversa e estou "
    "concluindo o restante com a equipe."
)


__all__ = [
    "DEFAULT_AGENT_KEY", "Elegibilidade", "HANDOFF_KIND", "LEAD_PREFIX", "MENSAGEM_APAGADO", "MOTIVOS_HANDOFF",
    "MENSAGEM_APAGADO_PARCIAL", "ResultadoApagar", "SlidingWindowLimiter", "SnapshotFalhou",
    "agents_token_for_org", "apagar_dados_do_chat", "avaliar_elegibilidade", "chat_aliases",
    "destinatario_do_handoff", "eh_eco_proprio", "encerrar_envio", "exigir_autorizados",
    "exigir_aviso_completo", "exigir_destinatario_valido", "exigir_hmac_configurado",
    "expandir_aliases", "gravar_snapshot", "is_deletion_request", "is_group_chat", "is_lid",
    "lead_key", "limpar_erro_link", "listar_todos_os_chats", "ler_erro_link",
    "marcar_envio_em_curso", "mensagem_inicial_pronta", "motivo_codigo_do_handoff", "notificar_handoff", "parse_lead_key",
    "permitir_turno", "phone_digits", "public_privacy_link", "registrar_envio_proprio",
    "registrar_erro_link", "resolve_agents_client", "sanitize_motivo", "snapshot_contem",
    "usuario_e_admin_da_org",
]
