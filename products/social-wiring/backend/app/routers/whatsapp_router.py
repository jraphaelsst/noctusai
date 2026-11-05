"""WhatsApp inbound webhook — WAHA forwards messages here.

This router handles incoming WhatsApp events from WAHA on Julia's ONE line (the "One Chat" operator bot is retired, 2026-11-04).
Every event it handles is persisted (``social_wiring.conversation_messages`` + ``whatsapp_chats``, migration 040) BEFORE it is
published on the realtime bus; then the sender is CLASSIFIED (``julia_staff_service.classificar_remetente``): staff (julia_staff
rows + the org members' core phones) is stored with the chat ``categoria='equipe'``, noticed to the admins and never routed;
anyone else is a lead and goes through triage and, when the switch is on and the chat is eligible, to Julia.

Events handled (WAHA webhook subscription list, wired at connection-create
time by ``whatsapp_connections_router.py``):

  ``message`` / ``message.any``
      Inbound text (+ media, resolved to text). Persisted with its ``origem`` (migration 318), folded into
      ``whatsapp_chats`` via ``WhatsAppChatStore.record_message``, and
      published as ``message.new`` + ``chat.upsert``. WAHA fires both
      ``message`` and ``message.any`` for the same inbound — the Redis
      SETNX pre-filter plus the ``UNIQUE(provider_message_id)`` constraint
      guard the race; keep both. The same constraint dedups the ``fromMe`` echo of a message SW wrote itself.
  ``message.ack``
      Delivery/read receipt for a message we sent or received. Applied to
      the matching row by ``provider_message_id`` (globally unique — no
      org/connection context needed) and published as ``message.ack``. An
      ack for a message we haven't recorded yet is a no-op, never an error.
  ``message.reaction``
      Acknowledged (200) but not persisted — no schema column exists yet
      for reactions. See the ``NOC-REMEDIATE[whatsapp-reaction-persistence]``
      marker at the handling site.
  ``session.status``
      QR/login state. Persisted to Redis (no durable column exists on
      ``whatsapp_connections`` for this — see ``_handle_session_status``)
      and published as ``session.status`` so the connection UI can react
      live instead of polling ``GET /connections/{id}/status`` (a ~13s
      live WAHA round-trip).

Auth note: this endpoint does NOT use the standard JWT auth because
WAHA's webhook calls carry no Authorization header. Signature verification
is via ``noctusai_lib.security.webhook_signatures.webhook_endpoint`` (HMAC
``waha`` scheme: ``X-Webhook-Hmac`` + ``X-Webhook-Hmac-Algorithm``, sha512 by default — WAHA's real shape).

One receiver route:

  POST /api/whatsapp/webhook/{token}
      Per-connection token-scoped route. The token is an opaque secret
      minted on connection create; it resolves to a specific connection
      record (org / user / session). Unknown token → generic 404 (no
      token enumeration). The legacy global ``/webhook`` route was deleted (CONTRACT julia-line A2/B3): it had no connection, so
      no line, no org and no routing to speak of.
"""
import anyio
# 🔴 NO `from __future__ import annotations` IN THIS FILE — deliberate.
#
# This module carries `@limiter.limit(...)` routes. slowapi resolves a
# rate-limited endpoint's signature at runtime; under PEP 563 every
# annotation is a STRING, so FastAPI/slowapi can no longer see a Pydantic
# body model and the route breaks. Keeper: `check_slowapi_with_pep563`
# (`mcp/noctusai/tools/noctus/dev/compliance.py`), baseline = zero.
#
# Today's two rate-limited routes take only `request: Request` + a
# `webhook_endpoint(...)` dependency and no body model, so the import was a
# LATENT hazard rather than a live break — it would have detonated the day
# someone added a request body. Removed rather than annotated, matching how
# the other baseline cases were fixed (products/seed .../webhook_router.py,
# products/adconnect .../financial.py both carry no future-import).

import asyncio
from typing import Any
import logging
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from noctusai_lib.integrations.redis import make_redis_client
from noctusai_lib.integrations.whatsapp.inbox.ingest import is_non_conversation_jid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from noctusai_lib.domain.chatbot import QueuedConversationMessage
from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import get_admin_client, get_core_client, get_scoped_admin_client, get_settings
from app.rate_limit import limiter
from app.routers.julia_agente_router import get_agents_client_factory
from app.routers.whatsapp_connections_router import get_waha_client_factory
from app.schemas.whatsapp import WAHAMessage, WAHAMessagePayload, WAHASessionStatusPayload, mensagem_encaminhada
from app.services import julia_agente_service as julia
from app.services.identidade_mascara import ref as ref_log
from app.services import julia_avaliacao_service, julia_conversas_service, julia_origem_service, julia_protecao_service, julia_staff_service, julia_thread_service
from app.services.conversation_module import get_conversation_module
from app.services.media_service import MidiaLead, make_media_service, midia_recusada
from app.services.message_store import DuplicateMessage, MessageStore, StoredMessage
from app.modules.email_marketing.services.contact_service import ContactService
from app.services.waha_response_registry import record_waha_sample
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_identity import resolve_identity
from app.services.whatsapp_entrada import EntradaDaLinha, entrada_da_conexao
from app.services.whatsapp_connection_store import build_whatsapp_connection_store
from app.services.credential_vault import EncryptionNotConfigured
from app.services.whatsapp_realtime import (
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_ACK,
    EVENT_MESSAGE_NEW,
    EVENT_SESSION_STATUS,
    get_whatsapp_bus,
    publish_whatsapp_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# ── Background contact auto-registration ──────────────────────────────────────
# 🔴 BOUNDARY: identity resolution hits WAHA (get_lid_phone + get_contact). It
# MUST NOT run on the inbound reply hot path — a slow WAHA there delayed/killed
# the AI reply (2026-06-24 regression). We fire-and-forget it so the reply is
# dispatched immediately; the resolved {phone, lids, name} lands in
# social_wiring.contacts for the read endpoints. WAHA calls are bounded by the
# seed client's short read timeout; any failure is swallowed with a warning.
_bg_tasks: set = set()


def _cfg_for_request(request: Request):
    """Resolve settings the way FastAPI would, for callables that cannot
    take ``Depends(get_settings)``.

    ``_resolve_waha_secret`` is handed to ``webhook_endpoint(...)`` as a
    plain ``(request, body)`` callable, so its signature is fixed and it
    cannot declare a dependency. Reading the module singleton directly is
    what forced tests to `monkeypatch.setattr(settings, ...)` — the
    self-patch this router regressed on. Consulting
    ``app.dependency_overrides`` honours the SAME `get_settings` seam the
    rest of the product uses, so `override_settings` works here too and
    tests never touch the singleton.

    → KB § PATTERNS/backend/di-test-seam.md (Class-A)
    """
    override = request.app.dependency_overrides.get(get_settings)
    return override() if override is not None else settings


def _fire_and_forget(coro) -> None:
    """Schedule a coroutine without blocking the caller; hold a ref vs GC."""
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:
        # No running loop (e.g. a sync test context) — not hot-path critical.
        coro.close()
        return
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _payload_com_anexo(
    payload: dict | None, *, media_url: str | None, mimetype: str | None, filename: str | None
) -> dict | None:
    """Mark the message as carrying an attachment (CONTRACT §2.1 `Mensagem.anexo`).
    `documento_id` is filled by the document intake once the file is stored."""
    if not media_url:
        return payload
    return {
        **(payload or {}),
        "anexo": {"mime": mimetype, "nome": filename, "documento_id": None},
    }


def _vincular_e_receber_midia(
    *, connection, chat_id: str, stored_message, media_url, mimetype, filename
) -> None:
    """Store the chat<->card link (CONTRACT §2.1) and, when the chat belongs to a
    card and the message carries media, hand the media to the document intake
    (§2.3) detached from the webhook. Best-effort: a failure here must not
    cost the (already durable) message."""
    try:
        from app.modules.card_hub.deps import get_card_hub_client
        from app.services import chat_cliente_link
        from app.services.documento_intake_service import processar_midia_do_webhook

        cliente_id = chat_cliente_link.vincular_chat(
            get_card_hub_client(), connection.org_id, connection.id, chat_id
        )
        if cliente_id and media_url:
            _fire_and_forget(
                processar_midia_do_webhook(
                    connection.org_id, UUID(cliente_id),
                    mensagem_id=stored_message.id, media_url=media_url,
                    mimetype=mimetype, filename=filename,
                )
            )
    except Exception:
        logger.warning(
            "whatsapp: chat link / media intake scheduling failed for chat=%s",
            chat_id, exc_info=True,
        )


async def _register_contact_bg(
    *,
    base_url: str,
    api_key: str | None,
    session: str,
    sender: str,
    push_name: str | None,
    org_id: str,
) -> None:
    """Resolve a sender's WhatsApp identity + upsert a contact. OFF the hot path."""
    try:
        from noctusai_lib.integrations.whatsapp import get_whatsapp_client  # noqa: PLC0415

        waha = get_whatsapp_client(base_url=base_url, api_key=api_key, session=session)
        identity = await resolve_identity(waha, sender)
        if identity.phone:
            ContactService(
                db=get_admin_client(), org_id=org_id
            ).upsert_whatsapp_contact(
                phone=identity.phone,
                lids=identity.lids,
                name=identity.name or push_name or None,
                jid=identity.jid,
            )
    except Exception:
        logger.warning(
            "WhatsApp contact auto-register failed for sender=%s — continuing",
            ref_log(sender),
            exc_info=True,
        )


async def _handle_session_status(envelope: WAHAMessagePayload, *, connection, cfg=None) -> None:
    """Persist + publish a ``session.status`` event.

    No durable column exists on ``whatsapp_connections`` for session state
    — adding one is out of this slice's territory (that table's router +
    schema belong to a peer branch). Redis is the persistence layer
    instead: a ``whatsapp:session_status:{connection_id|session}`` key
    with a 24h TTL, keyed by connection when we have one (token route)
    else by WAHA session name (legacy route). This is what lets a future
    connection-status read replace the current live-WAHA poll
    (``GET /connections/{id}/status``, a ~13s round-trip) — out of THIS
    router's scope, but the durable half of that fix. The realtime publish
    below is the half that's in scope: it lets a subscribed client react
    immediately instead of polling at all.
    """
    cfg = cfg or settings
    payload = envelope.payload
    if not isinstance(payload, WAHASessionStatusPayload):
        return
    status_value = payload.status or ""
    logger.info("WAHA session %s status: %s", envelope.session, status_value)

    key = f"whatsapp:session_status:{connection.id if connection is not None else envelope.session}"
    try:
        _status_redis = make_redis_client(cfg.redis_url, decode_responses=True)
        _status_redis.set(key, status_value, ex=24 * 3600)
    except Exception:
        logger.exception("failed to persist WAHA session status (key=%s)", key)

    if connection is not None:
        bus = get_whatsapp_bus(cfg.redis_url)
        await publish_whatsapp_event(
            bus,
            connection_id=connection.id,
            event=EVENT_SESSION_STATUS,
            payload={"status": status_value, "session": envelope.session},
        )


async def _handle_message_ack(envelope: WAHAMessagePayload, *, connection, cfg=None) -> None:
    """Apply a ``message.ack`` delivery/read receipt and publish it.

    WAHA reuses the message shape for acks (``id`` / ``ack`` / ``from`` /
    ...), so ``envelope.payload`` already resolves to :class:`WAHAMessage`
    — no dedicated ack schema needed.

    ``org_id`` is required to construct a :class:`MessageStore` but is NOT
    used to scope the update (see ``MessageStore.apply_ack``'s docstring —
    ``provider_message_id`` is globally unique): the connection's org when
    known, else the dev-fallback org.
    """
    cfg = cfg or settings
    payload = envelope.payload
    if not isinstance(payload, WAHAMessage):
        return
    provider_message_id = (payload.id or "").strip()
    if not provider_message_id:
        return
    try:
        ack = int(payload.ack) if payload.ack is not None else None
    except (TypeError, ValueError):
        ack = None
    if ack is None:
        logger.debug("WhatsApp ack event with unparseable ack=%r — dropped", payload.ack)
        return

    org_id = connection.org_id if connection is not None else UUID(cfg.local_dev_org_id)
    message_store = MessageStore(admin_supabase=get_admin_client(), org_id=org_id)
    acked_at = datetime.now(timezone.utc).isoformat()
    updated = message_store.apply_ack(
        provider_message_id=provider_message_id, ack=ack, acked_at=acked_at
    )
    if updated is None:
        # Ack arrived before our insert (or for a message this store never
        # recorded) — a no-op, never an error. WAHA will not retry a 200.
        logger.info(
            "WhatsApp ack for unknown message (provider_message_id=%s) — no-op",
            provider_message_id,
        )
        return

    # Scope the publish by the message's OWN connection_id (read back off
    # the row), NOT the webhook route's connection context — an ack can
    # legitimately arrive on the legacy route for a message a token-route
    # connection recorded, and the row is the source of truth for which
    # line owns it.
    if updated.connection_id is not None:
        bus = get_whatsapp_bus(cfg.redis_url)
        await publish_whatsapp_event(
            bus,
            connection_id=updated.connection_id,
            event=EVENT_MESSAGE_ACK,
            payload={
                "chat_id": updated.chat_id,
                "provider_message_id": updated.provider_message_id,
                "ack": updated.ack,
                "acked_at": updated.acked_at,
            },
        )


def _redis_opcional(cfg):
    """A Redis client for the OPTIONAL paths (LID cache, in-flight send flag, notice dedupe), or None. Never raises."""
    try:
        return make_redis_client(cfg.redis_url, decode_responses=True)
    except Exception as exc:
        logger.warning("whatsapp: Redis client unavailable (%s) -- continuing without it", type(exc).__name__)
        return None


def _entrada_da_linha(connection, *, cfg=None, waha_factory=None) -> EntradaDaLinha:
    """The slim inbound helper of the line (canonical id, LID cache, `get_lid_phone`), from the connection record. Redis is optional;
    the decrypted key is read only when a LID has to be resolved or a contact registered."""
    cfg = cfg or settings

    def _registro():
        store = _build_token_webhook_store(cfg)
        return store.get_connection(connection_id=connection.id, org_id=connection.org_id, decrypt=True) if store is not None else None

    return entrada_da_conexao(connection, redis=_redis_opcional(cfg), registro_provider=_registro, waha_factory=waha_factory)


async def _handle_lead_message(
    *, connection, entrada, chat_id: str, sender: str, message_body: str,
    provider_message_id: str, push_name: str | None, cfg,
    midia: dict | None = None, referral: dict | None = None, encaminhada: bool = False,
    mensagem_em: datetime | None = None, avaliacao: bool = False,
) -> bool:
    """The lead path for ONE inbound. Returns True when the message was handled here
    (enqueued for Julia, or deliberately held because a human has the chat), False
    when the chat is NOT Julia's (11.1) so the caller keeps today's behaviour.

    Never calls ChatbotService or any operator tool — it only buffers; the worker
    (`julia_lead_turn_service`) owns the turn.

    `message_body` is what the lead TYPED (or the media caption). The media they sent travels in `midia` (structured, masked,
    already resolved under the lead-path caps) and is buffered beside the text, never merged into it (GUARDRAILS B2)."""

    chat_store = WhatsAppChatStore(admin_supabase=get_admin_client(), org_id=connection.org_id)
    try:
        state = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)
        elegibilidade = julia.avaliar_elegibilidade(
            connection=connection, chat_state=state, mensagem_em=mensagem_em, avaliacao=avaliacao,
        )
    except Exception as exc:
        # Eligibility is a PRIVACY decision (11.1): when it cannot be made, the chat is
        # not Julia's. Logged, never swallowed into a "yes".
        logger.error("Julia eligibility check failed for chat=%s (%s) — treated as NOT eligible", ref_log(chat_id), type(exc).__name__)
        return False
    if not elegibilidade.elegivel:
        logger.info("Julia: chat %s not eligible (%s) — unchanged behaviour", ref_log(chat_id), elegibilidade.motivo)
        return False

    # Conversas v2: a BLOCKED number is dropped; an ARCHIVED contato goes back to Julia (un-paused). A data request
    # ("apagar meus dados") gets no exception: it is recorded for a human by the lead worker like any other message.
    politica = julia_conversas_service.aplicar_politica_inbound(
        get_scoped_admin_client("social_wiring"), chat_store,
        org_id=connection.org_id, connection_id=connection.id, chat_id=chat_id,
    )
    if politica == "bloqueado":
        logger.info("Julia: chat %s is blocked — inbound dropped", ref_log(chat_id))
        return True
    if politica == "devolvido":
        state = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)
    # julia-v2: NO local pause gate here. The per-conversation pause lives in AGENTS (the turn answers
    # `conversa_pausada` and the lead worker sends nothing); `whatsapp_chats.agente_pausado` is only a display mirror.

    module = get_conversation_module()
    if module is None:
        logger.error("Julia: conversation module unavailable — lead message for %s NOT processed", ref_log(chat_id))
        return True
    module.buffer.buffer_inbound(
        QueuedConversationMessage(
            conversation_id=julia.lead_key(connection.id, chat_id),
            text=message_body,
            direction="inbound",
            provider_message_id=provider_message_id or f"sw-{uuid4().hex}",
            metadata={"push_name": push_name, "sender": sender, **({"midia": midia} if midia else {}),
                      **({"referral": referral} if referral else {}), "encaminhada": bool(encaminhada)},
        )
    )
    logger.info("Julia: lead message buffered chat=%s debounce=%ss", ref_log(chat_id), cfg.message_debounce_seconds)
    return True


async def _triar_lead(connection, *, chat_id: str, sender: str, cfg):
    """GUARDRAILS B5: the first question about a LEAD inbound on a Julia line, asked BEFORE any media AI call or agents call: the
    blocklist / per-number rate-limit verdict (`Triagem`). Staff never get here (`_classificar_remetente` decides that first)."""
    client = get_scoped_admin_client("social_wiring")
    try:
        redis = make_redis_client(cfg.redis_url, decode_responses=True)
        return julia_protecao_service.triar_entrada(client, redis, get_core_client(), connection, chat_id=chat_id, sender=sender)
    except Exception as exc:
        logger.error("Julia: inbound triage unavailable conn=%s (%s) -- media AI refused for this inbound", connection.id, type(exc).__name__)
        return julia_protecao_service.Triagem("erro", dict(julia_protecao_service.PADRAO), None, connection.org_id, connection.id)


async def _resolver_midia_do_lead(
    triagem, *, chat_id: str, url, mimetype, filename, legenda: str, cfg,
) -> MidiaLead:
    """The LEAD-path media resolution (GUARDRAILS B2/B5/B8): refused without an AI call for a blocked / over-limit / unreadable
    triage or an exhausted media budget; otherwise streamed under the lead caps and read with the org's
    lead document prompt."""
    codigo = {"bloqueado": "bloqueado", "limitado": "limite_entrada", "erro": "falhou"}.get(triagem.estado)
    if codigo is not None:
        return midia_recusada(mimetype, filename, codigo, legenda=legenda)
    try:
        redis = make_redis_client(cfg.redis_url, decode_responses=True)
        return await make_media_service(org_id=triagem.org_id).resolve_inbound_lead(
            url=url, mimetype=mimetype, filename=filename, legenda=legenda,
            reservar=lambda: triagem.reservar_midia(redis, chat_id),
            prompt_documento=triagem.config.get("prompt_documento_lead"),
        )
    except Exception as exc:  # resolve_inbound_lead never raises; this is the Redis / factory seam
        logger.error("Julia: lead media resolution unavailable (%s)", type(exc).__name__)
        return midia_recusada(mimetype, filename, "falhou", legenda=legenda)


async def _classificar_remetente(connection, *, entrada, chat_id: str, sender: str, agents_client_factory=None, cfg=None):
    """B1 (CONTRACT julia-line): is whoever wrote on the line STAFF of the org that owns it? Staff = active `julia_staff` rows plus the
    phones of the org's active members (core `noctus_users.telefone`); decided by the NUMBER only (a LID is resolved to its phone first,
    and only when the org has any staff number at all), never by what the message says.

    Returns `(remetente, avaliacao)`: `remetente` is the staff verdict (None = a lead); `avaliacao` is True when an org MEMBER is on
    agents' evaluation list while evaluation mode is ON (owner 2026-11-05: the testing phase) -- then the sender is a LEAD (`remetente`
    None) so agents' gate answers it, and the flag lets it past the `equipe` refusal of the eligibility rule. An unreadable controle
    keeps the staff verdict (fail closed, logged). A failed staff lookup treats the sender as a lead (never staff -- logged, ids only)."""
    client = get_scoped_admin_client("social_wiring")
    try:
        core = get_core_client()
        extras = [chat_id, sender]
        if (julia.is_lid(sender) or julia.is_lid(chat_id)) and julia_staff_service.existe_equipe_com_telefone(client, core, connection.org_id):
            resolvido = await entrada.phone_do_lid(chat_id if julia.is_lid(chat_id) else sender)
            if resolvido:
                extras.append(resolvido)
        remetente = julia_staff_service.classificar_remetente(client, core, connection.org_id, julia_staff_service.formas_do_remetente(*extras))
        if remetente is not None and connection.agente_leads_ativo:
            agents = (agents_client_factory or (lambda org_id: julia.resolve_agents_client(org_id, cfg=cfg or settings)))(connection.org_id)
            if await julia_avaliacao_service.membro_em_avaliacao(
                agents, connection.org_id, connection.agente_leads_key or julia.DEFAULT_AGENT_KEY, remetente,
            ):
                logger.info("Julia: member on agents' evaluation list conn=%s -- treated as a lead (testing phase)", connection.id)
                return None, True
        return remetente, False
    except Exception as exc:
        logger.error("Julia: staff lookup failed conn=%s (%s) -- the sender is treated as a lead", connection.id, type(exc).__name__)
        return None, False


async def _bloqueado_pelo_teste(connection, *, entrada, chat_id: str, sender: str, agents_client_factory=None, cfg=None) -> bool:
    """TESTING MODE gate at SW's intake (owner 2026-11-05), asked BEFORE any media AI call and BEFORE agents is called: with agents'
    evaluation mode ON a LEAD who is not on the evaluation list is blocked -- the message is never forwarded to Julia (no agents
    thread/turn/LLM call, nothing stored in her history, no reply, no reroute to the owner). The state is read live on every inbound
    (never cached, never latched); unreadable or undecidable = blocked (fail closed, logged). The SW inbox still shows the message."""
    try:
        extras = [chat_id, sender]
        if julia.is_lid(sender) or julia.is_lid(chat_id):
            resolvido = await entrada.phone_do_lid(chat_id if julia.is_lid(chat_id) else sender)
            if resolvido:
                extras.append(resolvido)
        agents = (agents_client_factory or (lambda org_id: julia.resolve_agents_client(org_id, cfg=cfg or settings)))(connection.org_id)
        motivo = await julia_avaliacao_service.restricao_para_formas(
            agents, get_core_client(), connection.org_id, connection.agente_leads_key or julia.DEFAULT_AGENT_KEY,
            julia_staff_service.formas_do_remetente(*extras),
        )
    except Exception as exc:
        logger.error("Julia: testing-mode gate failed conn=%s (%s) -- inbound blocked", connection.id, type(exc).__name__)
        return True
    if motivo is not None:
        logger.info("Julia: inbound blocked org=%s conn=%s chat=%s reason=%s", connection.org_id, connection.id, ref_log(chat_id), motivo)
        return True
    return False


def _avisar_equipe_na_linha(*, connection, remetente, cfg) -> None:
    """A staff member wrote on Julia's line: the message is stored in the inbox, never enters the lead flow, and the org admins get ONE
    in-app notice an hour per person. Never raises."""
    from noctusai_lib.domain.notifications import write_in_app

    from app.services.julia_notificacoes_service import admins_da_org

    logger.info("Julia: staff message on the line org=%s role=%s origem=%s -- not a lead", connection.org_id, remetente.papel, remetente.origem)
    redis = _redis_opcional(cfg)
    if redis is not None:
        try:
            if not redis.set(f"julia:staff_linha:{connection.org_id}:{remetente.chave}", "1", nx=True, ex=3600):
                return
        except Exception as exc:
            logger.error("Julia: staff notice dedupe unavailable (%s) -- notifying", type(exc).__name__)
    try:
        core = get_core_client()
        admins = admins_da_org(core, connection.org_id)
        if not admins:
            raise RuntimeError("sem_destinatarios")
        write_in_app(
            core, user_ids=admins, kind="julia_staff_na_linha_publica", org_id=connection.org_id,
            title="Mensagem da equipe na linha da Julia",
            message=f"{remetente.nome} ({remetente.papel}) escreveu para a linha. A mensagem não entrou no atendimento da Julia; ela está na conversa.",
            metadata={"product": "social-wiring", "link": "/julia/conversas", "staff_id": remetente.chave},
        )
    except Exception as exc:
        logger.error("Julia: staff notice failed org=%s (%s)", connection.org_id, type(exc).__name__)


async def _apply_human_takeover(
    *, connection, chat_id: str, is_group: bool, provider_message_id: str, cfg, texto: str = "",
    equipe: bool = False, agents_client_factory=None,
) -> None:
    """L3 (contract 10.1): a ``fromMe`` message that is NOT SW's own echo means a human is typing. julia-v2: the
    pause lives in AGENTS -- the human's message is appended to the shared thread (Q5) and the agent is paused in that
    conversation through ``PATCH participantes`` (the attendant recorded as the actor); SW sets no local flag, then
    mirrors agents' answer onto the chat and tells Conversas.

    What is NOT a takeover (CONTRACT julia-line B2): a STAFF chat (`equipe`); a row whose durable `origem` is `julia` (her bubble) or
    `interno` (a system-sent staff notice, pre-written by its sender so this echo deduplicated); and, while a Julia send is in
    flight, WAHA's echo that beat our bookkeeping (the 30 s local echo window + the short Redis flag -- Redis is OPTIONAL: with it down the local window and the durable `origem` decide)."""
    if connection is None or not connection.agente_leads_ativo or is_group or equipe:
        return
    try:
        origem = MessageStore(admin_supabase=get_admin_client(), org_id=connection.org_id).origem_por_provider_id(provider_message_id or None)
    except Exception as exc:
        # Cannot tell SW's own echo from a human: do NOT pause (a wrongly-paused chat silences a lead; agents re-checks every turn).
        logger.error("Julia: own-echo check failed — takeover skipped for chat=%s (%s)", ref_log(chat_id), type(exc).__name__)
        return
    if julia.origem_e_eco_proprio(origem):
        logger.debug("Julia: fromMe echo of SW's own message (origem=%s id=%s) — no takeover", origem, provider_message_id)
        return
    if julia.envio_em_curso(_redis_opcional(cfg), connection_id=connection.id, chat_id=chat_id):
        logger.debug("Julia: fromMe echo while a Julia send is in flight (id=%s) — no takeover", provider_message_id)
        return
    chat_store = WhatsAppChatStore(admin_supabase=get_admin_client(), org_id=connection.org_id)
    try:
        client = (agents_client_factory or (lambda org_id: julia.resolve_agents_client(org_id, cfg=cfg)))(connection.org_id)
        # the author comes from the org STAFF list (name + role); the route that appends it is the staff append, the only one
        # agents lets carry `autor`
        autor = julia_thread_service.autor_humano_info(
            get_scoped_admin_client("social_wiring"), get_core_client(), connection, chat_id)
        resultado = await julia_thread_service.tomada_humana(
            client, chat_store, connection_id=connection.id, chat_id=chat_id,
            agent_key=connection.agente_leads_key or julia.DEFAULT_AGENT_KEY, texto=texto,
            provider_message_id=provider_message_id or None, autor_user_id=autor["user_id"] if autor else None,
            autor={"nome": autor["nome"], "papel": autor["papel"]} if autor else None,
        )
    except Exception as exc:
        logger.error("Julia: could not record the human takeover of chat=%s (%s)", ref_log(chat_id), type(exc).__name__)
        return
    if resultado != "pausado":
        logger.info("Julia: human message in chat %s — nothing to pause at agents (%s)", ref_log(chat_id), resultado)
        return
    logger.info("Julia: human takeover — agent paused in chat %s at agents (conn=%s)", ref_log(chat_id), connection.id)
    try:
        summary = chat_store.get_chat(connection_id=connection.id, chat_id=chat_id)
        payload = {**summary.as_dict(), "agente_pausado": True} if summary else {"chat_id": chat_id, "agente_pausado": True}
    except Exception as exc:
        logger.error("Julia: chat read for the pause event failed chat=%s (%s)", ref_log(chat_id), type(exc).__name__)
        payload = {"chat_id": chat_id, "agente_pausado": True}
    await publish_whatsapp_event(
        get_whatsapp_bus(cfg.redis_url), connection_id=connection.id,
        event=EVENT_CHAT_UPSERT, payload=payload,
    )


#: H5: a SIGNED message event older than this (or further in the future than the skew) is a replay of a captured body, not live traffic.
WEBHOOK_MAX_AGE_S = 300
WEBHOOK_MAX_FUTURE_S = 60


def _epoch_s(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number / 1000.0 if number > 1e11 else number  # WAHA emits seconds or milliseconds depending on the field


def _motivo_envelope_fora_da_janela(body: Any, envelope, *, agora: float | None = None) -> str | None:
    """Why a signed message envelope is outside the freshness window, or None when it is live. The envelope's own `timestamp` (when
    WAHA emitted the event) wins over the message's (when the person sent it): a phone that was offline delivers an old message
    in a fresh event. No timestamp at all on a signed event is refused (`timestamp_ausente`)."""
    import time

    bruto = body.get("timestamp") if isinstance(body, dict) else None
    ts = _epoch_s(bruto)
    if ts is None and isinstance(envelope.payload, WAHAMessage):
        ts = _epoch_s(envelope.payload.timestamp)
    if ts is None:
        return "timestamp_ausente"
    delta = (agora if agora is not None else time.time()) - ts
    if delta > WEBHOOK_MAX_AGE_S:
        return "timestamp_antigo"
    if delta < -WEBHOOK_MAX_FUTURE_S:
        return "timestamp_futuro"
    return None


def _mensagem_em(payload: Any) -> datetime | None:
    """When WhatsApp stamped the message (not when the event was emitted) -- the go-live cut-off compares THIS. None = unreadable."""
    ts = _epoch_s(getattr(payload, "timestamp", None))
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else None


async def _process_waha_body(
    body: dict,
    *,
    connection,
    event_source: str = "webhook",
    cfg=None,
    waha_factory=None,
    agents_client_factory=None,
    signed: bool = False,
) -> Response:
    """Shared WAHA envelope processor for the per-connection route (``POST /api/whatsapp/webhook/{token}``).

    Handles envelope validation, event routing, dedup (Redis SETNX + DB), media resolution, storage and routing on Julia's ONE
    line: ``connection`` is the :class:`WhatsAppConnectionRecord` the token resolved. Routing (CONTRACT julia-line B1/B2):

    * ``fromMe`` -> recorded (``origem`` ``humano``; a duplicate of a row SW wrote is Julia's / an internal send's own echo), then
      the human-takeover rule;
    * a STAFF sender (`julia_staff` rows + org members' core phones, ``classificar_remetente``) -> stored with the chat
      ``categoria='equipe'``, never sent to an agent, the org admins get an in-app notice;
    * anyone else is a lead: triage (blocklist / rate limit), then Julia when the switch is on and the chat is eligible.

    Always returns a ``200 OK`` Response (WAHA doesn't understand our errors and would retry indefinitely on non-200; processing
    failures are logged).
    """
    cfg = cfg or settings
    record_waha_sample(
        source=event_source,
        direction="waha_to_app",
        event_type=str(body.get("event") or "unknown") if isinstance(body, dict) else "unknown",
        payload=body,
        handling_notes=(
            "Webhook envelopes are always 200-acknowledged. Process only inbound "
            "message/message.any payloads with fromMe=false and text body; log "
            "session.status; ignore unknown events safely."
        ),
    )

    try:
        envelope = WAHAMessagePayload.model_validate(body)
    except Exception:
        logger.debug("WhatsApp webhook ignored: unknown WAHA envelope")
        return Response(status_code=status.HTTP_200_OK)

    # WAHA sends several event types; each is handled explicitly so an
    # unrecognized future event falls through to the safe "ignore" branch
    # below rather than silently misrouting into one of these.
    event = envelope.event

    # H5: the envelope must belong to THIS line's WAHA session. A body replayed or forged onto another line's token is refused
    # (the call is still a 200 no-op to WAHA: it would only retry).
    if (envelope.session or "") != (connection.session_name or ""):
        logger.warning(
            "WhatsApp webhook refused: reason=session_divergente conn=%s event=%s", connection.id, event,
        )
        return Response(status_code=status.HTTP_200_OK)

    if event in {"message", "message.any"} and signed:
        motivo = _motivo_envelope_fora_da_janela(body, envelope)
        if motivo is not None:
            logger.warning("WhatsApp webhook refused: reason=%s conn=%s event=%s", motivo, connection.id, event)
            return Response(status_code=status.HTTP_200_OK)

    if event == "session.status":
        await _handle_session_status(envelope, connection=connection, cfg=cfg)
        return Response(status_code=status.HTTP_200_OK)

    if event == "message.ack":
        await _handle_message_ack(envelope, connection=connection, cfg=cfg)
        return Response(status_code=status.HTTP_200_OK)

    if event == "message.reaction":
        # NOC-REMEDIATE[whatsapp-reaction-persistence]: no schema column
        # exists for reactions yet — migration 040 added ack/acked_at/chat_id
        # but not a reactions surface. Ack-and-drop until a product need for
        # reaction data emerges. — 2026-08-03
        logger.debug(
            "WhatsApp reaction event received (session=%s) — acknowledged, not persisted",
            envelope.session,
        )
        return Response(status_code=status.HTTP_200_OK)

    if event not in {"message", "message.any"}:
        return Response(status_code=status.HTTP_200_OK)

    payload = envelope.payload
    if not isinstance(payload, WAHAMessage):
        return Response(status_code=status.HTTP_200_OK)

    # H6: Status posts, broadcast lists and channels are not conversations: nothing is stored, routed or read by an AI call.
    if any(is_non_conversation_jid(j) for j in (payload.chat_id, payload.from_, payload.to)):
        logger.debug("WhatsApp webhook ignored: reason=broadcast_ou_canal conn=%s", connection.id)
        return Response(status_code=status.HTTP_200_OK)

    # Extract sender and message body
    message_body = payload.body or ""
    from_me = bool(payload.from_me)

    if from_me:
        # 🔴 B4 (contract 10.2): a message the line's owner sent from the phone
        # (or that SW itself sent) is RECORDED and then handled by the human-takeover
        # rule (L3) — it never triggers a turn. For `fromMe` the chat is `to`;
        # `from` is our own number.
        sender = payload.to or payload.chat_id
    else:
        sender = payload.from_ or payload.chat_id

    if not sender:
        return Response(status_code=status.HTTP_200_OK)

    # 🔴 H2 (contract 10.1): a GROUP never reaches Julia; `sender` stays the chat (replies, session and memory are per chat).
    is_group = julia.is_group_chat(payload.chat_id or sender)
    chat_id = (sender if from_me else (payload.chat_id or sender))

    # Fast dedup pre-filter — Redis SETNX on the provider_message_id
    # so the SECOND of (message, message.any) doesn't pay the OpenAI
    # cost. Uses its own short-lived Redis connection so we can run
    # this BEFORE any heavy work. The conversation_messages UNIQUE
    # constraint is the durable backstop for restart-survival; this SETNX
    # is purely for cost + latency (Redis is optional here: a failure falls through).
    provider_message_id = (payload.id or "").strip()
    if not provider_message_id and connection.agente_leads_ativo:
        # H5: a message with no id cannot be deduplicated (a replay would run twice) and its fromMe echo cannot be matched to
        # SW's own send (a fake takeover). On Julia's line it is dropped, loudly.
        logger.warning("WhatsApp webhook refused: reason=id_vazio conn=%s event=%s", connection.id, event)
        return Response(status_code=status.HTTP_200_OK)
    if provider_message_id:
        try:
            _setnx_client = make_redis_client(cfg.redis_url, decode_responses=True)
            seen_key = f"whatsapp:msg_seen:{provider_message_id}"
            won = _setnx_client.set(seen_key, "1", ex=5 * 60, nx=True)
            if not won:
                logger.info(
                    "WhatsApp inbound duplicate via SETNX (event=%s, id=%s)",
                    event,
                    provider_message_id,
                )
                return Response(status_code=status.HTTP_200_OK)
        except Exception:
            logger.exception("SETNX dedup check failed; falling through to DB dedup")

    entrada = _entrada_da_linha(connection, cfg=cfg, waha_factory=waha_factory)

    # 🔴 B1 (CONTRACT julia-line): who wrote on the line, asked BEFORE any media AI call or agents call. Staff is decided by the
    # NUMBER only (a LID is resolved to its phone first), against the julia_staff rows + the org members' core phones.
    remetente, avaliacao = None, False
    if not is_group:
        remetente, avaliacao = await _classificar_remetente(
            connection, entrada=entrada, chat_id=chat_id, sender=sender, agents_client_factory=agents_client_factory, cfg=cfg)
    equipe = remetente is not None
    # Testing mode: a lead who is not on agents' evaluation list never reaches Julia (nor a media AI call). A listed member (`avaliacao`)
    # already passed the very same list.
    bloqueado_teste = False
    if connection.agente_leads_ativo and not is_group and not from_me and not equipe and not avaliacao:
        bloqueado_teste = await _bloqueado_pelo_teste(
            connection, entrada=entrada, chat_id=chat_id, sender=sender, agents_client_factory=agents_client_factory, cfg=cfg)

    # Media-aware inbound: if the payload carries media (audio note,
    # photo, video, document), resolve it to enriched text BEFORE the
    # chatbot ever sees the message.
    midia_lead: MidiaLead | None = None
    triagem = None
    legenda_original = message_body
    media_url = None
    media_mimetype = None
    media_filename = None
    if payload.has_media and isinstance(payload.media, object):
        # WAHAMedia is a Pydantic model with .url / .mimetype / .filename;
        # falls back to dict when payload arrives as plain dict shape.
        media_url = getattr(payload.media, "url", None) or (
            payload.media.get("url") if isinstance(payload.media, dict) else None
        )
        media_mimetype = getattr(payload.media, "mimetype", None) or (
            payload.media.get("mimetype") if isinstance(payload.media, dict) else None
        )
        media_filename = getattr(payload.media, "filename", None) or (
            payload.media.get("filename") if isinstance(payload.media, dict) else None
        )
    # GUARDRAILS B5/B8: staff never get a media AI call (they are never a lead); a stranger's media on ANY line (Julia's or not) is
    # triaged (blocklist, per-number rate limit) BEFORE any AI call and resolved under the LEAD caps + the media budget (P1-4).
    # A group / broadcast never gets a media AI call at all.
    if not from_me and not is_group:
        if equipe:
            triagem = julia_protecao_service.Triagem(
                "equipe", dict(julia_protecao_service.PADRAO), None, connection.org_id, connection.id)
        else:
            triagem = await _triar_lead(connection, chat_id=chat_id, sender=sender, cfg=cfg)
    if media_url and not from_me and triagem is not None and triagem.estado != "equipe" and not bloqueado_teste:
        midia_lead = await _resolver_midia_do_lead(
            triagem, chat_id=chat_id, url=media_url, mimetype=media_mimetype, filename=media_filename,
            legenda=legenda_original, cfg=cfg,
        )
        message_body = midia_lead.exibicao()  # SW's own inbox line (masked); agents gets `midia`, never this string
    elif media_url and not from_me and is_group:
        logger.info("WhatsApp: group media stored without reading it (no AI call for a group) conn=%s", connection.id)

    if not message_body and media_url:
        # Media with no caption and no resolvable text (e.g. no Anthropic key):
        # still a message the operator must see and the document intake
        # (CONTRACT §2.3) must process — never dropped silently.
        message_body = "[Anexo recebido]"

    if not message_body:
        # No text, no resolvable media → nothing meaningful to react to. ACK and move on.
        return Response(status_code=status.HTTP_200_OK)

    # Durable dedup oracle — the SETNX pre-filter above caught the
    # in-memory race; the conversation_messages.provider_message_id
    # UNIQUE constraint survives container restarts. Anything that
    # passes SETNX also passes this in 99.9% of cases; the one
    # exception is a 5-minute SETNX TTL expiring before a delayed
    # WAHA retry, in which case the DB catch fires.
    message_store = MessageStore(admin_supabase=get_admin_client(), org_id=connection.org_id)
    direction = "outbound" if from_me else "inbound"
    # `origem` (migration 318): a lead's inbound is `lead`, a staff member's is `interno` (the team channel), a `fromMe` row that
    # was not already written by SW is a person typing (`humano`).
    origem = "humano" if from_me else ("interno" if equipe else "lead")
    stored_message: StoredMessage | None = None
    try:
        stored_message = message_store.record(
            session_id=entrada.canonical_session_id(sender),
            raw_sender=sender,
            direction=direction,
            body=message_body,
            provider_message_id=provider_message_id or None,
            authorized=True,
            structured_payload=_payload_com_anexo(
                midia_lead.structured_payload if midia_lead else None,
                media_url=media_url, mimetype=media_mimetype, filename=media_filename,
            ),
            connection_id=connection.id,
            chat_id=chat_id,
            origem=origem,
        )
    except DuplicateMessage:
        logger.info(
            "WhatsApp inbound duplicate (event=%s, id=%s) — dropped",
            event,
            provider_message_id,
        )
        if from_me:
            # The echo of a message SW already recorded (Julia's bubble, a system staff notice, a send from the Conversas UI). The
            # takeover rule reads the stored `origem`: Julia's own / internal is no takeover; the rest IS a human typing.
            await _apply_human_takeover(
                connection=connection, chat_id=chat_id, is_group=is_group, equipe=equipe,
                provider_message_id=provider_message_id, cfg=cfg, texto=message_body,
                agents_client_factory=agents_client_factory,
            )
        return Response(status_code=status.HTTP_200_OK)
    except Exception:
        # A persistence error must NOT block the line — log loudly and proceed.
        # `stored_message` stays None: there is nothing durable to fold
        # into the chats table or announce on the bus below (never publish
        # a write that didn't happen).
        logger.exception("conversation_messages insert failed; processing anyway")

    # ── Maintain the chats table + publish realtime events ──────────────────
    # Runs AFTER the DB write above — never before, a client must never be told about a message that isn't durable yet — and
    # only when the write actually happened (`stored_message is not None`).
    if stored_message is not None:
        try:
            chat_summary = WhatsAppChatStore(
                admin_supabase=get_admin_client(), org_id=connection.org_id
            ).record_message(
                connection_id=connection.id,
                chat_id=chat_id,
                direction=direction,
                body=message_body,
                created_at=stored_message.created_at or datetime.now(timezone.utc).isoformat(),
                # `pushName` is the only identity the inbound payload itself
                # carries; the store only ever FILLS a title in, never
                # overwrites a resolved one with a worse one (see its
                # docstring) — safe to pass on every message. On a `fromMe`
                # message it is OUR name, never the chat's title.
                title=None if from_me else (getattr(payload, "pushName", None) or None),
                has_media=payload.has_media,
                # the category follows the CURRENT staff list on every 1:1 message (a person removed from staff stops being `equipe`)
                categoria=None if is_group else ("equipe" if equipe else "lead"),
            )
        except Exception:
            logger.exception(
                "whatsapp_chats upsert failed for connection=%s chat=%s — inbox row "
                "may be stale; the message itself is already durable",
                connection.id, chat_id,
            )
            chat_summary = None

        if not from_me:
            _vincular_e_receber_midia(
                connection=connection, chat_id=chat_id, stored_message=stored_message,
                media_url=media_url, mimetype=media_mimetype, filename=media_filename,
            )

        bus = get_whatsapp_bus(cfg.redis_url)
        await publish_whatsapp_event(
            bus,
            connection_id=connection.id,
            event=EVENT_MESSAGE_NEW,
            payload={"chat_id": chat_id, "message": stored_message.as_message_dto()},
        )
        if chat_summary is not None:
            await publish_whatsapp_event(
                bus,
                connection_id=connection.id,
                event=EVENT_CHAT_UPSERT,
                payload=chat_summary.as_dict(),
            )

    if from_me:
        await _apply_human_takeover(
            connection=connection, chat_id=chat_id, is_group=is_group, equipe=equipe,
            provider_message_id=provider_message_id, cfg=cfg, texto=message_body,
            agents_client_factory=agents_client_factory,
        )
        return Response(status_code=status.HTTP_200_OK)

    # 🔴 B1: a staff message is stored (above) and NOTICED, never routed -- no contact registration, no triage, no agent.
    if equipe:
        _avisar_equipe_na_linha(connection=connection, remetente=remetente, cfg=cfg)
        return Response(status_code=status.HTTP_200_OK)

    # ── Best-effort contact auto-registration ────────────────────────────────
    # For every LEAD inbound, resolve the sender's identity and upsert it into social_wiring.contacts. Failure NEVER blocks message
    # ingestion. Fire-and-forget: the WAHA calls happen inside the backgrounded coroutine, never on the reply path.
    try:
        _record = entrada.registro_da_conexao()
        if _record is not None and _record.api_key:
            _fire_and_forget(
                _register_contact_bg(
                    base_url=connection.base_url,
                    api_key=_record.api_key,
                    session=connection.session_name,
                    sender=sender,
                    push_name=getattr(payload, "pushName", None),
                    org_id=str(connection.org_id),
                )
            )
    except Exception:
        logger.warning(
            "WhatsApp contact auto-register scheduling failed for sender=%s — continuing",
            ref_log(sender),
            exc_info=True,
        )

    # ── Julia routing (contract section 5, 10.1 H3, 10.2 B3, 11.1) ──────────────
    # AFTER dedup / media→text / record, a LEAD only: blocked / over-limit senders stop here; otherwise Julia answers when the
    # switch is on and the chat is eligible. Anything else is stored and left alone (the One Chat operator bot is retired).
    if connection.agente_leads_ativo and not is_group and not bloqueado_teste:
        if triagem is not None and triagem.estado in ("bloqueado", "limitado"):
            # recorded above (it is in the inbox); never reaches agents or an AI call (GUARDRAILS B5)
            return Response(status_code=status.HTTP_200_OK)
        await _handle_lead_message(
            connection=connection, entrada=entrada, chat_id=chat_id, sender=sender,
            message_body=legenda_original if midia_lead is not None else message_body,
            provider_message_id=provider_message_id,
            push_name=getattr(payload, "pushName", None), cfg=cfg,
            midia=midia_lead.para_agents() if midia_lead is not None else None,
            referral=julia_origem_service.extrair_referral_ctwa(body),
            encaminhada=mensagem_encaminhada(payload),
            mensagem_em=_mensagem_em(payload), avaliacao=avaliacao,
        )
    return Response(status_code=status.HTTP_200_OK)


def _avisar_assinatura_desativada(cfg: Any, rota: str) -> None:
    """L2: with the HMAC secret SET the `webhook_endpoint` dependency already refuses an unsigned or badly signed call (strict 401).
    With it UNSET in a deploy context the call is accepted -- the shared WAHA does not sign yet -- but loudly: ERROR once per process
    (`webhook_hmac_desativado`) and `/api/health` `startup_hook_error`. → `app.webhook_hmac`, NOC-REMEDIATE[waha-hmac-prod]."""
    from app import webhook_hmac

    webhook_hmac.avisar_uma_vez(cfg, rota)


async def _resolve_waha_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Per-request lookup of the WAHA webhook HMAC secret.

    Reads ``waha_webhook_hmac_secret`` at REQUEST time (not
    import time) so test-time settings overrides are honored — the
    import-time-capture trap ``KB § PATTERNS/security/webhook-signatures.md``
    warns about. ``or None`` collapses an empty string to the unset path
    so ``bypass_when_unset=True`` engages below, preserving this router's
    pre-existing dev behavior: no secret configured → accept without
    verification, loudly logged.
    """
    cfg = _cfg_for_request(request)
    return ResolvedSecret(secret=cfg.waha_webhook_hmac_secret or None)


def _build_token_webhook_store(cfg=None):
    """Plain builder — for callers that already hold a settings object.

    Split out of :func:`get_token_webhook_store` so internal call sites
    inside ``_process_waha_body`` can pass the request's resolved ``cfg``
    instead of reaching for the module singleton (the read that forced
    tests to monkeypatch ``settings.encryption_key``).
    """
    cfg = cfg or settings
    try:
        return build_whatsapp_connection_store(
            get_admin_client(), encryption_key=cfg.encryption_key
        )
    except EncryptionNotConfigured:
        return None


def get_token_webhook_store(cfg=Depends(get_settings)):
    """DI seam for the token-webhook store (service-role admin client; no JWT).

    Returns ``None`` when encryption isn't configured so the route can 404
    without leaking config state. This is the injectable seam tests override
    (``app.dependency_overrides[get_token_webhook_store]``) — never patch the
    module-level factory (that trips the no-monkey-patch-internals rule and
    stops exercising the real wiring). ``cfg`` flows from the same
    ``get_settings`` seam, so ``override_settings`` reaches it too.
    """
    return _build_token_webhook_store(cfg)


@router.post("/webhook/{token}")
@limiter.limit(settings.webhook_rate_limit)
async def whatsapp_webhook_by_token(
    token: str,
    request: Request,
    cfg=Depends(get_settings),
    store=Depends(get_token_webhook_store),
    waha_factory=Depends(get_waha_client_factory),
    agents_client_factory=Depends(get_agents_client_factory),
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_waha_secret,
        scheme="waha",
        bypass_when_unset=True,
        log_prefix="whatsapp-webhook-token",
    ),
) -> Response:
    """Per-connection token-scoped WAHA webhook endpoint.

    Resolves the connection via the opaque ``token`` path parameter.
    Unknown token → 404 (generic, no token enumeration). Delegates
    to the shared ``_process_waha_body`` pipeline — identical processing
    to the legacy ``/webhook`` route.

    HMAC check uses the same global ``waha_webhook_hmac_secret`` when
    configured (``store`` and ``verified`` are independent ``Depends`` —
    both resolve regardless of order; a signature mismatch still 401s
    before this body runs). No JWT — WAHA calls carry no Authorization
    header.
    """
    # Store is built by the get_token_webhook_store DI seam (service-role admin
    # client; no JWT — this is a public webhook endpoint). It returns None on a
    # config gap (encryption unconfigured) → 404, so we never leak config state
    # to unauthenticated callers. Unknown token → 404. Token lookup is plaintext.
    if store is None:
        logger.warning(
            "whatsapp_webhook_by_token: encryption not configured, cannot resolve token"
        )
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    connection = (await anyio.to_thread.run_sync(lambda: store.get_by_webhook_token(token)))
    if connection is None:
        # Do NOT log the token value — it's a secret routing credential.
        logger.debug("whatsapp_webhook_by_token: unknown token (404)")
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    logger.debug(
        "whatsapp_webhook_by_token: resolved connection id=%s session=%s",
        connection.id,
        connection.session_name,
    )

    _avisar_assinatura_desativada(cfg, "whatsapp_webhook_by_token")
    # 🔴 H1 (contract 10.1): with Julia on for THIS connection a missing/invalid
    # signature is 401 before any routing. An invalid one already 401s in the
    # `webhook_endpoint` dependency; what is left is the unset-secret bypass.
    if connection.agente_leads_ativo and not (cfg.waha_webhook_hmac_secret or "").strip():
        logger.error(
            "whatsapp_webhook_by_token: unsigned call refused — Julia is on for connection=%s "
            "and no HMAC secret is set", connection.id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="webhook secret not configured")

    try:
        body = json.loads(verified.body.decode("utf-8")) if verified.body else {}
    except Exception:
        return Response(status_code=status.HTTP_200_OK)

    return await _process_waha_body(
        body,
        cfg=cfg,
        event_source=f"webhook/{connection.id}",
        connection=connection,
        waha_factory=waha_factory,
        agents_client_factory=agents_client_factory,
        signed=bool((cfg.waha_webhook_hmac_secret or "").strip()),
    )


__all__ = ["router"]
