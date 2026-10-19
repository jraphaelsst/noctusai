"""The lead worker: one debounced batch of a lead's messages -> one agents turn.

Called by `conversation_module._build_processor` for buffer keys
`lead:<connection_id>:<chat_id>` (contract 10.2 B2). It NEVER touches
`ChatbotService`, the intake state machine or any operator tool (section 5 safety
rules): the only things it can do for a lead are `AgentsClient.run_turn`, send
the returned bubbles, and the deletion / handoff side effects.

Everything the worker needs is injected through `LeadDeps` (Fake+Real+factory,
DI-test-seam): the agents client factory, the WAHA client factory, the stores and
the buffer. Defaults wire the real thing.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.chatbot import QueuedConversationMessage
from noctusai_lib.integrations.redis import make_redis_client

from app.clients.agents import (
    MAX_BATCH_MESSAGES,
    MAX_MESSAGE_CHARS,
    AgentNotFound,
    AgentsBadRequest,
    AgentsClient,
    AgentsClientError,
    AgentsNotConfigured,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
    AgentUnavailable,
    CapacityExceeded,
    IdempotencyConflict,
    LlmNotConfigured,
    TurnInProgress,
    TurnMessage,
    TurnRequest,
    TurnResult,
)
from app.config import settings as _default_settings
from app.services import lais_acoes_service, lais_conhecimento_service, lais_contatos_service, lais_contexto_service, lais_conversas_service
from app.services import lais_equipes_service  # registers the `estado.atendente_nome` provider on import
from app.services import lais_agente_service as lais
from app.services import lais_aviso_service, lais_capi_service, lais_envio_gate, lais_eventos_service
from app.services.message_store import DuplicateMessage, MessageStore
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_connection_store import WhatsAppConnectionRecord
from app.services.whatsapp_outbound import send_paragraphs
from app.services.whatsapp_realtime import (
    EVENT_CHAT_UPSERT,
    EVENT_MESSAGE_NEW,
    get_whatsapp_bus,
    publish_whatsapp_event,
)

logger = logging.getLogger(__name__)

TURN_TIMEOUT_S = 65.0  # the client budget is 60 s (section 3.1); this is the outer guard
REQUEUE_IN_PROGRESS_S = 5
MAX_REQUEUE_IN_PROGRESS = 1
MAX_REQUEUE_CAPACITY = 3
_RETRY_TTL_S = 900


# ── injected collaborators ──────────────────────────────────────────────────
def _default_connection_lookup(cfg: Any) -> Callable[[UUID], Optional[WhatsAppConnectionRecord]]:
    from app.dependencies import get_admin_client
    from app.services.whatsapp_connection_store import build_whatsapp_connection_store

    def lookup(connection_id: UUID) -> Optional[WhatsAppConnectionRecord]:
        store = build_whatsapp_connection_store(get_admin_client(), encryption_key=cfg.encryption_key)
        return store.get_by_id(connection_id, decrypt=True)

    return lookup


def _default_job_repository() -> Any:
    """The `social_wiring.jobs` queue over the admin client; None (logged) when there is none -- the
    re-engagement timers are a side effect of a reply, never a precondition for sending it."""
    from noctusai_lib.domain.jobs import make_job_repository

    from app.dependencies import get_admin_client

    admin = get_admin_client()
    if admin is None:
        logger.warning("lais: no admin client -- re-engagement timers will not be armed")
        return None
    try:
        return make_job_repository(supabase_client=admin, schema_name="social_wiring")
    except Exception:
        logger.exception("lais: could not build the job repository -- re-engagement timers will not be armed")
        return None


@dataclass
class LeadDeps:
    buffer: Any
    admin: Any  # unscoped service-role client (`.schema(...)`), as the stores take it
    cfg: Any = field(default_factory=lambda: _default_settings)
    scoped: Any = None  # schema-scoped service-role client (`.table(...)`)
    core_client: Any = None
    agents_client_factory: Optional[Callable[[UUID], Optional[AgentsClient]]] = None
    waha_factory: Optional[Callable[..., Any]] = None
    cloud_client_factory: Optional[Callable[..., Any]] = None  # seed `get_meta_cloud_client` by default (wave 12)
    connection_lookup: Optional[Callable[[UUID], Optional[WhatsAppConnectionRecord]]] = None
    chat_store_factory: Callable[[UUID], Any] = None  # type: ignore[assignment]
    message_store_factory: Callable[[UUID], Any] = None  # type: ignore[assignment]
    redis: Any = None
    bus: Any = None
    jobs: Any = None  # seed `JobRepository` (re-engagement timers); built lazily, None = no timers
    sleep: Callable[[float], Any] = asyncio.sleep
    turn_timeout_s: float = TURN_TIMEOUT_S

    def __post_init__(self) -> None:
        from app.dependencies import get_admin_client, get_core_client, get_scoped_admin_client
        from noctusai_lib.integrations.whatsapp import get_whatsapp_client

        if self.scoped is None:
            self.scoped = get_scoped_admin_client("social_wiring")
        if self.core_client is None:
            self.core_client = get_core_client()
        if self.agents_client_factory is None:
            self.agents_client_factory = lambda org_id: lais.resolve_agents_client(org_id, cfg=self.cfg)
        if self.waha_factory is None:
            self.waha_factory = get_whatsapp_client
        if self.connection_lookup is None:
            self.connection_lookup = _default_connection_lookup(self.cfg)
        if self.chat_store_factory is None:
            self.chat_store_factory = lambda org_id: WhatsAppChatStore(admin_supabase=get_admin_client(), org_id=org_id)
        if self.message_store_factory is None:
            self.message_store_factory = lambda org_id: MessageStore(admin_supabase=get_admin_client(), org_id=org_id)
        if self.redis is None:
            self.redis = make_redis_client(self.cfg.redis_url, decode_responses=True)
        if self.bus is None:
            self.bus = get_whatsapp_bus(self.cfg.redis_url)
        if self.jobs is None:
            self.jobs = _default_job_repository()


# ── the buffer run: which inbound messages are still unanswered ─────────────
def unprocessed_run(memory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inbound items whose `provider_message_id` no processed-marker has claimed.

    Position-independent on purpose: an inbound that lands WHILE a turn is running
    sits after the marker we append at the end -- an "everything before the last
    outbound" cut would silently swallow it."""
    processed: set[str] = set()
    for item in memory:
        if item.get("direction") == "outbound":
            ids = (item.get("metadata") or {}).get("processed_ids") or []
            processed.update(str(i) for i in ids)
    return [
        i for i in memory
        if i.get("direction") == "inbound" and str(i.get("provider_message_id") or "") not in processed
        and str(i.get("text") or "").strip()
    ]


def close_run(buffer: Any, key: str, run: list[dict[str, Any]]) -> None:
    ids = [str(i["provider_message_id"]) for i in run if i.get("provider_message_id")]
    buffer.append_to_memory(
        QueuedConversationMessage(
            conversation_id=key, text="[processado]", direction="outbound",
            metadata={"processed_ids": ids},
        )
    )


def trim_batch(run: list[dict[str, Any]], *, max_chars: int) -> list[dict[str, Any]]:
    """Newest-first: at most 20 messages, each cut to 8000 chars, total <= `max_chars`
    (contract 10.1 M4: a batch is capped at 16k). Dropped ones are the OLDEST."""
    kept: list[dict[str, Any]] = []
    total = 0
    for item in reversed(run):
        text = str(item.get("text") or "")[:MAX_MESSAGE_CHARS]
        if kept and (len(kept) >= MAX_BATCH_MESSAGES or total + len(text) > max_chars):
            break
        kept.append({**item, "text": text})
        total += len(text)
    kept.reverse()
    return kept


def _as_datetime(ts: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


# ── sending through the connection's own WAHA client ────────────────────────
class LeadSender:
    """`send_paragraphs`' `intake` seam for the lead path: sends via the CONNECTION's
    WAHA credentials (the operator intake is bound to the global WAHA session),
    records the outbound, publishes realtime, and registers the message id as
    Julia's own so its `fromMe` echo is never mistaken for a human (L3)."""

    def __init__(self, *, connection: WhatsAppConnectionRecord, waha: Any, deps: LeadDeps, liberacao: lais_envio_gate.Liberacao):
        self._c = connection
        self._waha = waha
        self._d = deps
        self._liberacao = liberacao

    async def send_reply(self, sender: str, text: str) -> None:
        from app.schemas.whatsapp import extract_waha_message_id

        lais_envio_gate.conferir(self._liberacao, self._c.id)  # the outbound gate (two gates) passed for this line
        result = await self._waha.send_text(sender, text)
        provider_message_id = extract_waha_message_id(result) if isinstance(result, dict) else None
        lais.registrar_envio_proprio(self._d.redis, provider_message_id)
        now = datetime.now(timezone.utc).isoformat()
        stored = None
        try:
            stored = self._d.message_store_factory(self._c.org_id).record(
                session_id=sender, raw_sender=sender, direction="outbound", body=text,
                provider_message_id=provider_message_id, authorized=True,
                structured_payload={"origem": "julia"},
                connection_id=self._c.id, chat_id=sender,
            )
        except DuplicateMessage:
            logger.info("lais: outbound echo already recorded (id=%s)", provider_message_id)
        except Exception:
            logger.exception("lais: outbound record failed conn=%s chat=%s", self._c.id, sender)
        try:
            summary = self._d.chat_store_factory(self._c.org_id).record_message(
                connection_id=self._c.id, chat_id=sender, direction="outbound", body=text, created_at=now,
            )
        except Exception:
            logger.exception("lais: chat row update failed conn=%s chat=%s", self._c.id, sender)
            summary = None
        if stored is not None:
            await publish_whatsapp_event(
                self._d.bus, connection_id=self._c.id, event=EVENT_MESSAGE_NEW,
                payload={"chat_id": sender, "message": stored.as_message_dto()},
            )
        if summary is not None:
            await publish_whatsapp_event(
                self._d.bus, connection_id=self._c.id, event=EVENT_CHAT_UPSERT,
                payload={**summary.as_dict(), "agente_pausado": False},
            )


async def publish_pause(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, pausado: bool) -> None:
    """`chat.upsert` carrying `agente_pausado`, so Conversas flips its chip live."""
    try:
        summary = deps.chat_store_factory(connection.org_id).get_chat(connection_id=connection.id, chat_id=chat_id)
    except Exception:
        logger.exception("lais: chat read for pause event failed conn=%s chat=%s", connection.id, chat_id)
        summary = None
    payload = {**summary.as_dict(), "agente_pausado": pausado} if summary else {"chat_id": chat_id, "agente_pausado": pausado}
    await publish_whatsapp_event(deps.bus, connection_id=connection.id, event=EVENT_CHAT_UPSERT, payload=payload)


# ── Lais foundation: contato / episode / contexto / actions (contract 2.2) ──
@dataclass
class LaisTurn:
    """What the foundation prepared BEFORE the turn and needs again AFTER it."""

    contato: dict[str, Any]
    contexto: dict[str, Any]
    #: Deterministic messages sent BEFORE Julia's reply on this turn (wave 1: the recesso notice on the
    #: first turn of an interacao inside the period). Empty = nothing extra.
    avisos: list[str] = field(default_factory=list)

    @property
    def perguntas(self) -> list[dict[str, Any]]:
        return list(self.contexto.get("perguntas") or [])


def _registrar_resposta_de_disparo(deps: LeadDeps, org_id: Any, contato: dict[str, Any], phone: Optional[str]) -> None:
    """Wave 12: an inbound from a disparo target flips its target `enviado -> respondido`; the message then
    runs through Julia's ordinary lead path (the remarketing re-entry). Best-effort: never blocks the turn."""
    tel = "".join(ch for ch in str(contato.get("telefone_e164") or phone or "") if ch.isdigit())
    if not tel:
        return
    try:
        from app.services import lais_disparos_service

        lais_disparos_service.registrar_resposta(deps.scoped, org_id, tel)
    except Exception:
        logger.exception("lais: disparo reply bookkeeping failed org=%s", org_id)


async def _preparar_lais(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, phone: Optional[str],
    display_name: Optional[str], state: Optional[dict[str, Any]], agents_client: Optional[AgentsClient],
) -> Optional[LaisTurn]:
    """Upsert the contato, bump `gen` for this inbound, settle the episode (24 h of silence
    closes the old one with a summary, then a new one opens), render the `contexto`.

    Best-effort by design: ANY failure is logged at ERROR and the turn runs with page-0
    behaviour (no contexto) -- the foundation must never stop Julia answering a lead."""
    org_id = connection.org_id
    try:
        contato = lais_contatos_service.obter_ou_criar_contato(
            deps.scoped, org_id=org_id, connection_id=connection.id, chat_id=chat_id,
            telefone_e164=phone, nome=display_name,
        )
        contato, anterior = lais_contatos_service.registrar_inbound(deps.scoped, contato)
        _registrar_resposta_de_disparo(deps, org_id, contato, phone)
        await lais_capi_service.registrar_resposta(deps.scoped, org_id, contato)  # wave 13 CAPI `resposta_cliente` (never raises)
        interacao = lais_contatos_service.interacao_aberta(deps.scoped, contato["id"])
        if interacao is not None and lais_contatos_service.episodio_vencido(anterior):
            perguntas = lais_contexto_service.montar(
                deps.scoped, org_id, contato, interacao=interacao, ferramentas_habilitadas=False,
            ).get("perguntas") or []
            await lais_acoes_service.fechar_interacao(
                deps.scoped, org_id=org_id, contato=contato, interacao=interacao, agents_client=agents_client,
                conversation_id=(state or {}).get("agente_conversation_id"), perguntas=perguntas,
            )
            interacao = None
        if interacao is None:
            interacao = lais_contatos_service.abrir_interacao(deps.scoped, org_id, contato)
        contexto = lais_contexto_service.montar(deps.scoped, org_id, contato, interacao=interacao)
        recesso = lais_conhecimento_service.mensagem_recesso_primeiro_turno(deps.scoped, org_id, contato, interacao)
        return LaisTurn(contato=contato, contexto=contexto, avisos=[recesso] if recesso else [])
    except Exception:
        logger.exception("lais: foundation prep failed conn=%s chat=%s -- turn runs without contexto", connection.id, chat_id)
        return None


def _registrar_inbound_pausado(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, phone: Optional[str]) -> None:
    """A human is handling the chat: no turn, but the inbound still counts (`gen + 1`, last inbound)."""
    try:
        contato = lais_contatos_service.obter_ou_criar_contato(
            deps.scoped, org_id=connection.org_id, connection_id=connection.id, chat_id=chat_id, telefone_e164=phone,
        )
        lais_contatos_service.registrar_inbound(deps.scoped, contato)
    except Exception:
        logger.exception("lais: inbound bookkeeping failed for the paused chat conn=%s chat=%s", connection.id, chat_id)


async def _pos_turno(
    deps: LeadDeps, *, lais_turn: Optional[LaisTurn], connection: WhatsAppConnectionRecord, chat_id: str,
    result: TurnResult, lote_hash: Optional[str], agents_client: Optional[AgentsClient], enviou: bool,
) -> None:
    """After the reply (or its deliberate silence): stamp the outbound, apply the actions.
    Never raises -- the reply is out and must not be undone by bookkeeping."""
    if lais_turn is None or lote_hash is None:
        return
    try:
        if enviou:
            lais_contatos_service.registrar_outbound(deps.scoped, lais_turn.contato["id"])
        await lais_acoes_service.aplicar(
            deps.scoped, org_id=connection.org_id, contato=lais_turn.contato, result=result, lote_hash=lote_hash,
            conversation_id=result.conversation_id, agents_client=agents_client, core_client=deps.core_client,
            perguntas=lais_turn.perguntas, connection_id=connection.id, chat_id=chat_id,
        )
    except Exception:
        logger.exception("lais: post-turn bookkeeping failed conn=%s chat=%s", connection.id, chat_id)
    if enviou:
        await _armar_reengajamento(deps, connection=connection, chat_id=chat_id)


async def _armar_reengajamento(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str) -> None:
    """After a Julia outbound AND its actions: arm the re-engagement timers against the contato's CURRENT
    `gen` (an `encerrar` / handoff in the same turn already bumped it and set `encerrado_at`). Never raises."""
    if deps.jobs is None:
        return
    try:
        from app.services import lais_reengajamento_service

        fresh = lais_contatos_service.buscar_contato(deps.scoped, connection.org_id, connection.id, chat_id)
        if fresh is not None:
            await lais_reengajamento_service.agendar_apos_outbound(deps.scoped, deps.jobs, connection.org_id, fresh)
    except Exception:
        logger.exception("lais: could not arm the re-engagement timers conn=%s chat=%s", connection.id, chat_id)


#: The system marker that stands in for the lead's message in a re-engagement turn (agents needs >= 1).
REENGAJAMENTO_MARCADOR = "[sistema] O lead não respondeu. Retome a conversa."


# ── the worker entry point ──────────────────────────────────────────────────
def _phone_e164(chat_id: str) -> Optional[str]:
    d = lais.phone_digits(chat_id)
    return f"+{d}" if d else None


def _retry_key(key: str) -> str:
    return f"lais:retry:{key}"


def _attempts(deps: LeadDeps, key: str) -> int:
    return len(deps.buffer.redis.lrange(_retry_key(key), 0, -1))


def _bump_attempts(deps: LeadDeps, key: str) -> None:
    deps.buffer.redis.rpush(_retry_key(key), "1")
    deps.buffer.redis.expire(_retry_key(key), _RETRY_TTL_S)


def _clear_attempts(deps: LeadDeps, key: str) -> None:
    deps.buffer.redis.delete(_retry_key(key))


def _requeue(deps: LeadDeps, key: str, delay_s: float) -> None:
    deps.buffer.redis.zadd(deps.buffer.due_set_key, {key: time.time() + delay_s})


async def process_lead_batch(key: str, memory: list[dict[str, Any]], *, deps: LeadDeps) -> None:
    """Run one lead batch. Never raises for an expected failure -- each row of the
    section 3.1 error table ends in a defined outcome (re-queue, link-health
    memory, or silence); the lead never sees an error (L2)."""
    parsed = lais.parse_lead_key(key)
    if parsed is None:
        logger.error("lais: not a lead key: %r", key)
        return
    connection_id, chat_id = parsed

    run = unprocessed_run(memory)
    if not run:
        logger.debug("lais: key=%s nothing unprocessed", key)
        return

    connection = deps.connection_lookup(connection_id)
    if connection is None or not connection.agente_leads_ativo:
        logger.info("lais: connection %s missing or Julia off -- batch dropped", connection_id)
        close_run(deps.buffer, key, run)
        return
    org_id = connection.org_id
    chat_store = deps.chat_store_factory(org_id)
    agent_key = connection.agente_leads_key or lais.DEFAULT_AGENT_KEY

    # Deletion on request (M5) is honoured before everything else -- even for a
    # paused chat: it is the data subject's right, not Julia's reply.
    if any(lais.is_deletion_request(str(i.get("text") or "")) for i in run):
        await _handle_deletion(deps, connection=connection, chat_id=chat_id, key=key, agent_key=agent_key, run=run)
        return

    # H3 re-check at routing time: fail closed, no reply.
    if not [n for n in (connection.authorized_numbers or []) if str(n).strip()]:
        logger.error("lais: connection %s has Julia on with no authorized_numbers -- fail closed", connection.id)
        close_run(deps.buffer, key, run)
        return

    # Conversas v2: a blocked number never gets a turn (defence in depth -- the webhook already drops it);
    # an archived contato is handed back to Julia (un-archived + un-paused) before the pause check below.
    try:
        politica = lais_conversas_service.aplicar_politica_inbound(
            deps.scoped, chat_store, org_id=org_id, connection_id=connection.id, chat_id=chat_id)
    except Exception:  # the foundation never stops Julia answering (page-0 contract); the webhook is the primary drop
        logger.exception("lais: block/archive policy check failed conn=%s chat=%s -- turn proceeds", connection.id, chat_id)
        politica = "ok"
    if politica == "bloqueado":
        logger.info("lais: chat %s is blocked -- batch dropped", chat_id)
        close_run(deps.buffer, key, run)
        return

    state = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)
    if state and state.get("agente_pausado"):
        logger.info("lais: chat %s paused (human handling) -- no turn", chat_id)
        _registrar_inbound_pausado(deps, connection=connection, chat_id=chat_id, phone=_phone_e164(chat_id))
        close_run(deps.buffer, key, run)
        return

    if not lais.permitir_turno(deps.buffer.redis, connection_id=connection.id, chat_id=chat_id, cfg=deps.cfg):
        logger.warning("lais: rate limit hit conn=%s chat=%s -- turn dropped (M4)", connection.id, chat_id)
        close_run(deps.buffer, key, run)
        return

    client = deps.agents_client_factory(org_id)
    if client is None:
        lais.registrar_erro_link(org_id, "nao_configurado", cfg=deps.cfg)
        logger.error("lais: agents not configured for org %s -- no reply sent", org_id)
        close_run(deps.buffer, key, run)
        return

    # A2: provider_message_id is unique within a batch (1..256 chars) -- first wins.
    seen_ids: set[str] = set()
    unique_run = []
    for item in run:
        pid = str(item.get("provider_message_id") or "")[:256]
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique_run.append({**item, "provider_message_id": pid})
    batch = trim_batch(unique_run, max_chars=deps.cfg.lais_agente_batch_max_chars)
    meta = next((i.get("metadata") or {} for i in reversed(run) if i.get("metadata")), {})
    phone = _phone_e164(chat_id)
    if phone is None and lais.is_lid(chat_id):
        phone = await _resolve_lid_phone(deps, connection, chat_id)
    lais_turn = await _preparar_lais(
        deps, connection=connection, chat_id=chat_id, phone=phone,
        display_name=(meta.get("push_name") or None), state=state, agents_client=client,
    )
    req = TurnRequest(
        agent_key=agent_key,
        connection_id=str(connection.id),
        chat_id=chat_id,
        phone_e164=phone,
        display_name=(meta.get("push_name") or None),
        contexto=lais_turn.contexto if lais_turn else None,
        messages=tuple(
            TurnMessage(texto=m["text"], provider_message_id=str(m["provider_message_id"]), at=_as_datetime(m.get("timestamp")))
            for m in batch if m.get("provider_message_id")
        ),
    )
    if not req.messages:
        logger.error("lais: batch for %s carries no provider_message_id -- dropped", chat_id)
        close_run(deps.buffer, key, run)
        return

    try:
        result = await asyncio.wait_for(client.run_turn(req), timeout=deps.turn_timeout_s)
    except asyncio.TimeoutError:
        logger.error("lais: agents turn timed out (>%ss) conn=%s chat=%s", deps.turn_timeout_s, connection.id, chat_id)
        _clear_attempts(deps, key)
        close_run(deps.buffer, key, run)
        return
    except AgentsClientError as exc:
        _handle_turn_error(deps, exc, key=key, run=run, org_id=org_id, connection_id=connection.id, chat_id=chat_id)
        return
    _clear_attempts(deps, key)
    lais.limpar_erro_link(org_id, cfg=deps.cfg)

    await _deliver(
        deps, connection=connection, chat_id=chat_id, key=key, run=run, result=result, state=state, chat_store=chat_store,
        lais_turn=lais_turn, agents_client=client,
        lote_hash=lais_acoes_service.lote_hash_de(result.conversation_id, [m.provider_message_id for m in req.messages]),
        fluxo=lais_envio_gate.Fluxo.RESPOSTA,
    )


def _handle_turn_error(
    deps: LeadDeps, exc: AgentsClientError, *, key: str, run: list[dict[str, Any]],
    org_id: UUID, connection_id: UUID, chat_id: str,
) -> None:
    """The section 3.1 error table, one branch per row. No branch sends the lead anything."""
    if isinstance(exc, TurnInProgress):
        if _attempts(deps, key) < MAX_REQUEUE_IN_PROGRESS:
            _bump_attempts(deps, key)
            _requeue(deps, key, REQUEUE_IN_PROGRESS_S)
            logger.info("lais: turn_in_progress -- batch re-queued once in %ss (chat=%s)", REQUEUE_IN_PROGRESS_S, chat_id)
            return
        logger.error("lais: turn_in_progress persisted after the re-queue -- batch dropped (chat=%s)", chat_id)
    elif isinstance(exc, CapacityExceeded):
        if _attempts(deps, key) < MAX_REQUEUE_CAPACITY:
            _bump_attempts(deps, key)
            _requeue(deps, key, exc.retry_after)
            logger.warning("lais: capacidade -- batch re-queued in %ss (chat=%s)", exc.retry_after, chat_id)
            return
        logger.error("lais: capacidade persisted after %s re-queues -- batch dropped (chat=%s)", MAX_REQUEUE_CAPACITY, chat_id)
    elif isinstance(exc, (AgentsTokenInvalid, AgentsNotConfigured)):
        lais.registrar_erro_link(org_id, "token_invalido" if isinstance(exc, AgentsTokenInvalid) else "nao_configurado", cfg=deps.cfg)
        logger.error("lais: agents token rejected (code=%s) org=%s -- no reply", exc.code, org_id)
    elif isinstance(exc, AgentNotFound):
        lais.registrar_erro_link(org_id, "agent_not_found", cfg=deps.cfg)
        logger.error("lais: agent not found org=%s -- no reply", org_id)
    elif isinstance(exc, AgentUnavailable):
        lais.registrar_erro_link(org_id, "agent_unavailable", cfg=deps.cfg)
        logger.error("lais: agent unavailable (%s) org=%s -- no reply", exc.code, org_id)
    elif isinstance(exc, LlmNotConfigured):
        lais.registrar_erro_link(org_id, "llm_not_configured", cfg=deps.cfg)
        logger.error("lais: LLM key missing in agents for org=%s -- no reply", org_id)
    elif isinstance(exc, (AgentsBadRequest, IdempotencyConflict)):
        logger.error("lais: agents rejected the turn as a client bug (%s: %s) conn=%s chat=%s", type(exc).__name__, exc.code, connection_id, chat_id)
    elif isinstance(exc, (AgentsUpstreamError, AgentsTimeout)):
        logger.error("lais: agents upstream failure (%s) conn=%s chat=%s -- no reply", type(exc).__name__, connection_id, chat_id)
    else:  # an AgentsClientError subclass we do not know: never reply, never loop
        logger.error("lais: unhandled agents error %s conn=%s chat=%s", type(exc).__name__, connection_id, chat_id)
    _clear_attempts(deps, key)
    close_run(deps.buffer, key, run)


async def _resolve_lid_phone(deps: LeadDeps, connection: WhatsAppConnectionRecord, lid: str) -> Optional[str]:
    try:
        waha = deps.waha_factory(base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name)
        pn = await waha.get_lid_phone(lid)
    except Exception:
        logger.warning("lais: LID->phone lookup failed for %s", lid, exc_info=True)
        return None
    d = lais.phone_digits(pn) if pn else None
    return f"+{d}" if d else None


async def _deliver(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, key: str,
    run: list[dict[str, Any]], result: TurnResult, state: Optional[dict[str, Any]], chat_store: Any,
    lais_turn: Optional[LaisTurn] = None, agents_client: Optional[AgentsClient] = None, lote_hash: Optional[str] = None,
    fluxo: lais_envio_gate.Fluxo, regua_id: Optional[str] = None,
) -> bool:
    """Send the reply; True when at least one bubble went out. Nothing leaves before `lais_envio_gate.exigir`
    passes for `fluxo` (Julia on for the line + the org's opt-in for that flow)."""
    pos = dict(lais_turn=lais_turn, connection=connection, chat_id=chat_id, result=result, lote_hash=lote_hash,
               agents_client=agents_client)
    # L3: a human may have taken over WHILE the turn was running -- re-check the
    # flag before sending anything.
    fresh = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)
    if fresh and fresh.get("agente_pausado"):
        logger.info("lais: chat %s paused during the turn -- reply discarded", chat_id)
        # The reply is dropped, but what the model extracted (slots, operacao) is still the lead's data.
        await _pos_turno(deps, enviou=False, **pos)
        close_run(deps.buffer, key, run)
        return False

    handoff = result.handoff
    primeira = not ((state or {}).get("agente_conversation_id") or (fresh or {}).get("agente_conversation_id"))
    partes = list(result.partes)
    if lais_turn is not None and lais_turn.avisos:
        # Wave 1: the deterministic recesso notice goes first (after the privacy disclosure, inserted below).
        partes[0:0] = lais_turn.avisos
    if not partes and handoff is None:
        await _pos_turno(deps, enviou=False, **pos)  # silence can still carry actions
        close_run(deps.buffer, key, run)  # status `silencio`: stay silent, nothing to disclose
        return False

    try:
        liberacao = lais_envio_gate.exigir(
            deps.scoped, connection.org_id, connection.id, fluxo,
            contato_id=lais_turn.contato.get("id") if lais_turn is not None else None, regua_id=regua_id,
        )
    except lais_envio_gate.EnvioBloqueado:  # already logged + `envio_bloqueado` event by the gate
        await _pos_turno(deps, enviou=False, **pos)
        close_run(deps.buffer, key, run)
        return False
    waha = deps.waha_factory(base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name)
    sender = LeadSender(connection=connection, waha=waha, deps=deps, liberacao=liberacao)
    delay = float(deps.cfg.whatsapp_paragraph_delay_seconds)

    if primeira:
        # 11.3: the disclosure is deterministic and goes BEFORE Julia's first reply.
        try:
            disclosure = lais.mensagem_inicial_pronta(
                lais_aviso_service.obter_ou_criar(deps.scoped, deps.core_client, connection.org_id)
            )
        except Exception:
            logger.exception("lais: cannot build the privacy disclosure for org=%s -- reply NOT sent", connection.org_id)
            close_run(deps.buffer, key, run)
            return False
        partes.insert(0, disclosure)

    lais.marcar_envio_em_curso(deps.redis, connection.id, chat_id)
    enviadas = 0
    try:
        for idx, parte in enumerate(partes):
            if idx:
                await deps.sleep(delay)
            await send_paragraphs(intake=sender, sender=chat_id, text=parte, delay_seconds=0, split=False)
            enviadas += 1
    except Exception:
        logger.exception("lais: WAHA send failed after %s/%s bubbles conn=%s chat=%s", enviadas, len(partes), connection.id, chat_id)
    finally:
        lais.encerrar_envio(deps.redis, connection.id, chat_id)

    if primeira and enviadas and result.conversation_id:
        chat_store.set_agente_conversation(connection_id=connection.id, chat_id=chat_id, conversation_id=result.conversation_id)
    if enviadas and fluxo is lais_envio_gate.Fluxo.RESPOSTA and lais_turn is not None:
        _registrar_primeira_resposta(deps, connection.org_id, lais_turn.contato)

    if handoff is not None:
        await _apply_handoff(deps, connection=connection, chat_id=chat_id, chat_store=chat_store, motivo=handoff.motivo)
    await _pos_turno(deps, enviou=bool(enviadas), **pos)
    close_run(deps.buffer, key, run)
    return bool(enviadas)


def _registrar_primeira_resposta(deps: LeadDeps, org_id: Any, contato: dict[str, Any]) -> None:
    """maya-blocks: Julia's first reply of the open episode stamps `primeira_resposta_at` (once). Only a reply to
    the lead's own message counts (a re-engagement is not a response). Bookkeeping: never undoes the reply."""
    try:
        lais_contatos_service.registrar_primeira_resposta(deps.scoped, org_id, contato["id"])
    except Exception:
        logger.exception("lais: primeira_resposta_at not stamped org=%s contato=%s (the reply IS out)", org_id, contato.get("id"))


async def run_reengajamento_turn(
    deps: LeadDeps, connection: WhatsAppConnectionRecord, chat_id: str, contato: dict[str, Any],
    estado_extra: dict[str, Any], marker_id: str,
) -> bool:
    """A re-engagement turn (wave 4): the ordinary lead turn with `contexto.estado.<estado_extra>`, no
    inbound from the lead. agents requires >= 1 message, so ONE system marker (never sent to the lead,
    unique per job through `marker_id`) stands in for it. Does NOT bump `gen` (nothing came in). Returns True
    when a message went out; an agents failure is logged and reads as False (the job still completes: a
    re-engagement is best-effort, a retry storm against a down agents is worse).

    `estado_extra["reengajamento"]` names the flow the outbound gate checks (`minutos` | `horas` | `regua`); a
    regua turn also carries `regua_id`, which goes to the gate and NOT into the agents context."""
    estado_extra = dict(estado_extra)
    regua_id = estado_extra.pop("regua_id", None)
    fluxo = lais_envio_gate.FLUXO_DO_TIER.get(str(estado_extra.get("reengajamento")))
    if fluxo is None:
        raise ValueError(f"re-engagement turn without a known tier: {estado_extra.get('reengajamento')!r}")
    org_id = connection.org_id
    client = deps.agents_client_factory(org_id)
    if client is None:
        lais.registrar_erro_link(org_id, "nao_configurado", cfg=deps.cfg)
        logger.error("lais: agents not configured for org %s -- re-engagement not sent", org_id)
        return False
    chat_store = deps.chat_store_factory(org_id)
    state = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)
    interacao = lais_contatos_service.abrir_interacao(deps.scoped, org_id, contato)
    contexto = lais_contexto_service.montar(deps.scoped, org_id, contato, interacao=interacao, estado_extra=estado_extra)
    phone = contato.get("telefone_e164") or _phone_e164(chat_id)
    req = TurnRequest(
        agent_key=connection.agente_leads_key or lais.DEFAULT_AGENT_KEY,
        connection_id=str(connection.id), chat_id=chat_id, phone_e164=phone, display_name=contato.get("nome"),
        contexto=contexto,
        messages=(TurnMessage(
            texto=REENGAJAMENTO_MARCADOR, provider_message_id=marker_id[:256], at=datetime.now(timezone.utc),
        ),),
    )
    try:
        result = await asyncio.wait_for(client.run_turn(req), timeout=deps.turn_timeout_s)
    except asyncio.TimeoutError:
        logger.error("lais: re-engagement turn timed out (>%ss) conn=%s chat=%s", deps.turn_timeout_s, connection.id, chat_id)
        return False
    except AgentsClientError as exc:
        logger.error("lais: re-engagement turn failed (%s) conn=%s chat=%s", type(exc).__name__, connection.id, chat_id)
        return False
    return await _deliver(
        deps, connection=connection, chat_id=chat_id, key=f"lead:{connection.id}:{chat_id}", run=[], result=result,
        state=state, chat_store=chat_store, lais_turn=LaisTurn(contato=contato, contexto=contexto),
        agents_client=client, lote_hash=lais_acoes_service.lote_hash_de(result.conversation_id, [marker_id]),
        fluxo=fluxo, regua_id=str(regua_id) if regua_id else None,
    )


async def _apply_handoff(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, chat_store: Any, motivo: str) -> None:
    """handoff => `agente_pausado=true` + `chat.upsert` + the in-app notification
    (contract 5 / 11.4). A notification failure is logged, never undoes the pause."""
    chat_store.set_agente_pausado(connection_id=connection.id, chat_id=chat_id, pausado=True)
    try:  # contract 0.2: a handoff invalidates every job queued for this contato
        lais_contatos_service.bump_gen_do_chat(deps.scoped, connection.org_id, connection.id, chat_id)
    except Exception:
        logger.exception("lais: gen bump on handoff failed conn=%s chat=%s (the chat IS paused)", connection.id, chat_id)
    await publish_pause(deps, connection=connection, chat_id=chat_id, pausado=True)
    responsavel: Optional[str] = None
    contato: Optional[dict[str, Any]] = None
    try:  # wave 11: pick the attendant BEFORE notifying so the notification reaches them
        contato = lais_contatos_service.buscar_contato(deps.scoped, connection.org_id, connection.id, chat_id)
        if contato is not None:
            atribuido = lais_equipes_service.atribuir_responsavel(deps.scoped, deps.core_client, connection.org_id, contato, "handoff")
            responsavel = atribuido["user_id"] if atribuido else None
    except Exception:
        logger.exception("lais: attendant distribution failed conn=%s chat=%s (the handoff proceeds unassigned)", connection.id, chat_id)
    # maya-blocks: the reason as a CLOSED code (never the model's free text) for Maya's sdr scorecard. `handoff` is
    # outside the notification fan-out, so this cannot double-notify; `emitir` never raises.
    lais_eventos_service.emitir(
        deps.scoped, connection.org_id, "handoff", (contato or {}).get("id"),
        {"motivo_codigo": lais.motivo_codigo_do_handoff(motivo)},
    )
    try:
        summary = chat_store.get_chat(connection_id=connection.id, chat_id=chat_id)
        lais.notificar_handoff(
            deps.core_client, connection=connection, chat_id=chat_id,
            titulo_chat=summary.title if summary else None, motivo=motivo, responsavel_user_id=responsavel,
        )
    except Exception:
        logger.exception("lais: handoff notification failed conn=%s chat=%s (the chat IS paused)", connection.id, chat_id)


async def _handle_deletion(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, key: str, agent_key: str, run: list[dict[str, Any]],
) -> None:
    client = deps.agents_client_factory(connection.org_id)
    res = await lais.apagar_dados_do_chat(
        client=deps.scoped, connection=connection, chat_id=chat_id,
        agents_client=client, agent_key=agent_key, buffer=deps.buffer,
    )
    # Confirm to the lead with the connection's own WAHA client -- NOT recorded
    # (the rows were just deleted; recording would re-create what was erased).
    try:
        lais_envio_gate.exigir(deps.scoped, connection.org_id, connection.id, lais_envio_gate.Fluxo.RESPOSTA)
        waha = deps.waha_factory(base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name)
        await waha.send_text(chat_id, lais.MENSAGEM_APAGADO if res.agents_ok else lais.MENSAGEM_APAGADO_PARCIAL)
    except lais_envio_gate.EnvioBloqueado:  # Julia switched off mid-batch: the gate logged it + left the event
        return
    except Exception:
        logger.exception("lais: deletion confirmation could not be sent chat=%s", chat_id)


__all__ = [
    "LeadDeps", "LeadSender", "close_run", "process_lead_batch", "publish_pause", "trim_batch",
    "unprocessed_run",
]
