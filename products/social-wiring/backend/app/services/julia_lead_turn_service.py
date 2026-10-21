"""The lead worker: one debounced batch of a lead's messages -> one agents turn (julia-v2: Julia is HOSTED in agents).

Called by `conversation_module._build_processor` for buffer keys `lead:<connection_id>:<chat_id>` (contract 10.2 B2). It
NEVER touches `ChatbotService`, the intake state machine or any operator tool (section 5 safety rules): the only things
it can do for a lead are `AgentsClient.run_turn`, send the returned bubbles, and the handoff side effects. It never deletes anything: no inbound message can trigger a destructive action.

SW does NOT decide whether Julia answers. Agents decides on EVERY turn, under its lock, before any model call (the
controls: ligado / drenando / desligado, the per-conversation pause, another agent's thread, the lead's opt-out) and
answers with a `status`:

  served      respondido | silencio | handoff | encerrado | concluido     -> send the bubbles, apply the actions
  not served  agente_desligado | novo_lead_recusado | conversa_pausada | conversa_com_outro_responsavel |
              conversa_com_outro_agente | controle_indisponivel | lead_opt_out | reengajamento_ignorado |
              limite_atingido | limite_taxa | novo_lead_limitado | loop_detectado
                                                                         -> NOTHING is sent, no action is applied
              (the last three LIMIT statuses are never silence for a real person: they are routed to the org's operators)

and any error or timeout is also "nothing sent" (fail closed). `whatsapp_chats.agente_pausado` is a display mirror, not a
gate. What a not-served turn leaves behind (Q5): the lead's messages are appended to the thread (idempotent) when the
thread exists; a lead agents refused to serve is not kept in SW either.

Everything the worker needs is injected through `LeadDeps` (Fake+Real+factory, DI-test-seam): the agents client factory,
the WAHA client factory, the stores and the buffer. Defaults wire the real thing.
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
    STATUS_LIMITE_PARA_HUMANO,
    GATILHO_REENGAJAMENTO,
    MAX_BATCH_MESSAGES,
    MAX_MESSAGE_CHARS,
    STATUS_SEM_ATENDIMENTO,
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
    ControleIndisponivel,
    HandoffRecord,
    IdempotencyConflict,
    LlmNotConfigured,
    TurnInProgress,
    TurnMessage,
    TurnRequest,
    TurnResult,
)
from app.config import settings as _default_settings
from app.modules.supervisao import alertas as supervisao_alertas
from app.services import julia_acoes_service, julia_conhecimento_service, julia_contatos_service, julia_contexto_service, julia_conversas_service
from app.services.identidade_mascara import ref as ref_log
from app.services import julia_protecao_service as protecao
from app.services import julia_equipes_service  # registers the `estado.atendente_nome` provider on import
from app.services import julia_espelho_service, julia_thread_service
from app.services import julia_agente_service as julia
from app.services import julia_aviso_service, julia_capi_service, julia_envio_gate, julia_envio_service, julia_eventos_service, julia_notificacoes_service
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
        logger.warning("julia: no admin client -- re-engagement timers will not be armed")
        return None
    try:
        return make_job_repository(supabase_client=admin, schema_name="social_wiring")
    except Exception as exc:
        logger.error("julia: could not build the job repository -- re-engagement timers will not be armed (%s)", type(exc).__name__)
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
            self.agents_client_factory = lambda org_id: julia.resolve_agents_client(org_id, cfg=self.cfg)
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
        and (str(i.get("text") or "").strip() or (i.get("metadata") or {}).get("midia"))
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
    """Newest-first: at most 20 messages, each cut to 2000 chars, total <= `max_chars` (agents' caps, GUARDRAILS B5: 2000 per
    message, 6000 per batch). Dropped ones are the OLDEST. SW cuts to agents' caps so the lead is never answered with a 422 (agents sets
    `truncado` itself)."""
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


def mensagem_do_turno(item: dict[str, Any]) -> TurnMessage:
    """One buffered inbound -> the wire message. The media the lead sent rides in the STRUCTURED `midia` field (GUARDRAILS B2),
    never as a bracketed prefix inside `texto`."""
    midia = (item.get("metadata") or {}).get("midia")
    return TurnMessage(
        texto=item["text"], provider_message_id=str(item["provider_message_id"]), at=_as_datetime(item.get("timestamp")),
        midia=dict(midia) if isinstance(midia, dict) and midia else None,
    )


def texto_para_anexar(item: dict[str, Any]) -> str:
    """What a lead message agents did NOT answer is appended to the thread as (plain `user` text, no `midia` on that route):
    the caption / typed text, else a short SW-owned label of the media kind. The extraction stays in SW's own inbox."""
    texto = str(item.get("text") or "").strip()
    if texto:
        return texto
    midia = (item.get("metadata") or {}).get("midia") or {}
    tipo = {"audio": "um áudio", "imagem": "uma imagem", "video": "um vídeo", "documento": "um documento"}.get(str(midia.get("tipo")), "um arquivo")
    return f"(o lead enviou {tipo})"


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

    def __init__(self, *, connection: WhatsAppConnectionRecord, waha: Any, deps: LeadDeps, liberacao: julia_envio_gate.Liberacao):
        self._c = connection
        self._waha = waha
        self._d = deps
        self._liberacao = liberacao

    async def send_reply(self, sender: str, text: str) -> None:
        from app.schemas.whatsapp import extract_waha_message_id

        julia_envio_gate.conferir(self._liberacao, self._c.id)  # the outbound gate (two gates) passed for this line
        result = await self._waha.send_text(sender, text)
        provider_message_id = extract_waha_message_id(result) if isinstance(result, dict) else None
        julia.registrar_envio_proprio(self._d.redis, provider_message_id)
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
            logger.info("julia: outbound echo already recorded (id=%s)", provider_message_id)
        except Exception as exc:
            logger.error("julia: outbound record failed conn=%s chat=%s (%s)", self._c.id, ref_log(sender), type(exc).__name__)
        try:
            summary = self._d.chat_store_factory(self._c.org_id).record_message(
                connection_id=self._c.id, chat_id=sender, direction="outbound", body=text, created_at=now,
            )
        except Exception as exc:
            logger.error("julia: chat row update failed conn=%s chat=%s (%s)", self._c.id, ref_log(sender), type(exc).__name__)
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
    except Exception as exc:
        logger.error("julia: chat read for pause event failed conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
        summary = None
    payload = {**summary.as_dict(), "agente_pausado": pausado} if summary else {"chat_id": chat_id, "agente_pausado": pausado}
    await publish_whatsapp_event(deps.bus, connection_id=connection.id, event=EVENT_CHAT_UPSERT, payload=payload)


# ── Julia foundation: contato / episode / contexto / actions (contract 2.2) ──
@dataclass
class JuliaTurn:
    """What the foundation prepared BEFORE the turn and needs again AFTER it."""

    contato: dict[str, Any]
    contexto: dict[str, Any]
    #: Deterministic messages sent BEFORE Julia's reply on this turn (wave 1: the recesso notice on the
    #: first turn of an interacao inside the period). Empty = nothing extra.
    avisos: list[str] = field(default_factory=list)
    #: True when this inbound is the contato's FIRST ever (the lead started the conversation: the opt-in moment).
    novo: bool = False


def _registrar_resposta_de_disparo(deps: LeadDeps, org_id: Any, contato: dict[str, Any], phone: Optional[str]) -> None:
    """Wave 12: an inbound from a disparo target flips its target `enviado -> respondido`; the message then
    runs through Julia's ordinary lead path (the remarketing re-entry). Best-effort: never blocks the turn."""
    tel = "".join(ch for ch in str(contato.get("telefone_e164") or phone or "") if ch.isdigit())
    if not tel:
        return
    try:
        from app.services import julia_disparos_service

        julia_disparos_service.registrar_resposta(deps.scoped, org_id, tel)
    except Exception as exc:
        logger.error("julia: disparo reply bookkeeping failed org=%s (%s)", org_id, type(exc).__name__)


async def _preparar_julia(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, phone: Optional[str],
    display_name: Optional[str], state: Optional[dict[str, Any]], agents_client: Optional[AgentsClient],
) -> Optional[JuliaTurn]:
    """Upsert the contato, bump `gen` for this inbound, settle the episode (24 h of silence
    closes the old one with a summary, then a new one opens), render the `contexto`.

    julia-v2: the contato id IS the lead identity agents keys the shared thread and the qualification by
    (`lead.ref`), so a failure here is NOT survivable -- ANY failure is logged at ERROR and returns None, and the
    caller sends no turn (fail closed). It used to run page-0 without a contexto; agents has no lead to attach then."""
    org_id = connection.org_id
    try:
        contato = julia_contatos_service.obter_ou_criar_contato(
            deps.scoped, org_id=org_id, connection_id=connection.id, chat_id=chat_id,
            telefone_e164=phone, nome=display_name,
        )
        contato, anterior = julia_contatos_service.registrar_inbound(deps.scoped, contato)
        _registrar_resposta_de_disparo(deps, org_id, contato, phone)
        await julia_capi_service.registrar_resposta(deps.scoped, org_id, contato)  # wave 13 CAPI `resposta_cliente` (never raises)
        interacao = julia_contatos_service.interacao_aberta(deps.scoped, contato["id"])
        if interacao is not None and julia_contatos_service.episodio_vencido(anterior):
            await julia_acoes_service.fechar_interacao(
                deps.scoped, org_id=org_id, contato=contato, interacao=interacao, agents_client=agents_client,
                conversation_id=julia_thread_service.thread_id_do_estado(state),
            )
            interacao = None
        if interacao is None:
            interacao = julia_contatos_service.abrir_interacao(deps.scoped, org_id, contato)
        contexto = julia_contexto_service.montar(deps.scoped, org_id, contato, interacao=interacao)
        recesso = julia_conhecimento_service.mensagem_recesso_primeiro_turno(deps.scoped, org_id, contato, interacao)
        return JuliaTurn(contato=contato, contexto=contexto, avisos=[recesso] if recesso else [], novo=anterior is None)
    except Exception as exc:
        logger.error("julia: foundation prep failed conn=%s chat=%s -- no turn is sent (no lead identity) (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
        return None


async def _pos_turno(
    deps: LeadDeps, *, julia_turn: Optional[JuliaTurn], connection: WhatsAppConnectionRecord, chat_id: str,
    result: TurnResult, lote_hash: Optional[str], agents_client: Optional[AgentsClient], enviou: bool,
) -> None:
    """After the reply (or its deliberate silence): stamp the outbound, apply the actions, refresh the qualification
    mirror and let the computed stage drive the CRM send (Q6). Never raises -- the reply is out and must not be undone
    by bookkeeping."""
    if julia_turn is None or lote_hash is None:
        return
    try:
        if enviou:
            julia_contatos_service.registrar_outbound(deps.scoped, julia_turn.contato["id"])
        await julia_acoes_service.aplicar(
            deps.scoped, org_id=connection.org_id, contato=julia_turn.contato, result=result, lote_hash=lote_hash,
            conversation_id=result.thread or result.conversation_id, agents_client=agents_client,
            core_client=deps.core_client, connection_id=connection.id, chat_id=chat_id,
        )
    except Exception as exc:
        logger.error("julia: post-turn bookkeeping failed conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
    try:
        # the mirror reads the contato fresh: an action above (encerrar) may have changed it
        fresco = julia_contatos_service.buscar_contato(deps.scoped, connection.org_id, connection.id, chat_id) or julia_turn.contato
        resumo = await julia_espelho_service.espelhar_apos_turno(
            deps.scoped, org_id=connection.org_id, contato=fresco, result=result, agents_client=agents_client,
            interacao=julia_contatos_service.interacao_aberta(deps.scoped, fresco["id"]),
        )
        await julia_envio_service.reagir_ao_estagio(
            deps.scoped, connection.org_id, fresco, resumo, agents_client=agents_client,
            ja_enviado_por_acao=any(a.type == "lead_pronto" for a in result.julia_actions),
        )
    except Exception as exc:
        logger.error("julia: qualification mirror / stage trigger failed conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
    if enviou:
        await _armar_reengajamento(deps, connection=connection, chat_id=chat_id)


async def _armar_reengajamento(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str) -> None:
    """After a Julia outbound AND its actions: arm the re-engagement timers against the contato's CURRENT
    `gen` (an `encerrar` / handoff in the same turn already bumped it and set `encerrado_at`). Never raises."""
    if deps.jobs is None:
        return
    try:
        from app.services import julia_reengajamento_service

        fresh = julia_contatos_service.buscar_contato(deps.scoped, connection.org_id, connection.id, chat_id)
        if fresh is not None:
            await julia_reengajamento_service.agendar_apos_outbound(deps.scoped, deps.jobs, connection.org_id, fresh)
    except Exception as exc:
        logger.error("julia: could not arm the re-engagement timers conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)


# ── the worker entry point ──────────────────────────────────────────────────
def _phone_e164(chat_id: str) -> Optional[str]:
    d = julia.phone_digits(chat_id)
    return f"+{d}" if d else None


def _retry_key(key: str) -> str:
    return f"julia:retry:{key}"


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
    parsed = julia.parse_lead_key(key)
    if parsed is None:
        logger.error("julia: not a lead key: %r", key)
        return
    connection_id, chat_id = parsed

    run = unprocessed_run(memory)
    if not run:
        logger.debug("julia: key=%s nothing unprocessed", key)
        return

    connection = deps.connection_lookup(connection_id)
    if connection is None or not connection.agente_leads_ativo:
        logger.info("julia: connection %s missing or Julia off -- batch dropped", connection_id)
        close_run(deps.buffer, key, run)
        return
    org_id = connection.org_id
    chat_store = deps.chat_store_factory(org_id)
    agent_key = connection.agente_leads_key or julia.DEFAULT_AGENT_KEY

    # H3 re-check at routing time: fail closed, no reply.
    if not [n for n in (connection.authorized_numbers or []) if str(n).strip()]:
        logger.error("julia: connection %s has Julia on with no authorized_numbers -- fail closed", connection.id)
        close_run(deps.buffer, key, run)
        return

    # Conversas v2: a blocked number never gets a turn (defence in depth -- the webhook already drops it);
    # an archived contato is handed back to Julia (un-archived + un-paused) before the pause check below.
    try:
        politica = julia_conversas_service.aplicar_politica_inbound(
            deps.scoped, chat_store, org_id=org_id, connection_id=connection.id, chat_id=chat_id)
    except Exception as exc:  # the foundation never stops Julia answering (page-0 contract); the webhook is the primary drop
        logger.error("julia: block/archive policy check failed conn=%s chat=%s -- turn proceeds (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
        politica = "ok"
    if politica == "bloqueado":
        logger.info("julia: chat %s is blocked -- batch dropped", ref_log(chat_id))
        close_run(deps.buffer, key, run)
        return
    if politica == "devolvido":
        # an archived contato is handed back: the agent must be RESUMED where the pause lives (agents), not only here
        await julia_thread_service.devolver_a_julia(
            deps.agents_client_factory(org_id), chat_store, connection_id=connection.id, chat_id=chat_id, agent_key=agent_key,
            ator_user_id=julia_thread_service.autor_humano(deps.scoped, deps.core_client, connection, chat_id),
        )

    # GUARDRAILS B5: a number on the org's blocklist (manual, or the automatic temporary one) never gets a turn, even for messages
    # buffered before the block landed. The webhook already drops its inbound; this is the defence in depth.
    try:
        chave = protecao.chave_numero(chat_id)
        if chave and protecao.bloqueio_ativo(deps.scoped, org_id, [chave]) is not None:
            logger.info("julia: number %s is on the org blocklist -- batch dropped", protecao.ref(chave))
            close_run(deps.buffer, key, run)
            return
    except Exception as exc:  # fail OPEN here on purpose: the webhook gate is the primary one and a lookup glitch must not silence leads
        logger.error("julia: blocklist check failed conn=%s (%s) -- turn proceeds", connection.id, type(exc).__name__)

    # julia-v2: NO local pause gate. `whatsapp_chats.agente_pausado` is a display mirror; agents decides on every turn
    # (controls, per-conversation pause, another agent's thread, opt-out) and a not-served status sends nothing.
    state = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)

    if not julia.permitir_turno(deps.buffer.redis, connection_id=connection.id, chat_id=chat_id, cfg=deps.cfg):
        logger.warning("julia: rate limit hit conn=%s chat=%s -- turn dropped (M4)", connection.id, ref_log(chat_id))
        close_run(deps.buffer, key, run)
        return

    client = deps.agents_client_factory(org_id)
    if client is None:
        julia.registrar_erro_link(org_id, "nao_configurado", cfg=deps.cfg)
        logger.error("julia: agents not configured for org %s -- no reply sent", org_id)
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
    batch = trim_batch(unique_run, max_chars=deps.cfg.julia_agente_batch_max_chars)
    meta = next((i.get("metadata") or {} for i in reversed(run) if i.get("metadata")), {})
    phone = _phone_e164(chat_id)
    if phone is None and julia.is_lid(chat_id):
        phone = await _resolve_lid_phone(deps, connection, chat_id)
    julia_turn = await _preparar_julia(
        deps, connection=connection, chat_id=chat_id, phone=phone,
        display_name=(meta.get("push_name") or None), state=state, agents_client=client,
    )
    if julia_turn is None:  # no lead identity => agents has nothing to attach the thread to: fail closed
        close_run(deps.buffer, key, run)
        return
    if julia_turn.novo:
        await _registrar_opt_in(client, julia_turn.contato["id"])
    req = TurnRequest(
        agent_key=agent_key,
        connection_id=str(connection.id),
        chat_id=chat_id,
        phone_e164=phone,
        display_name=(meta.get("push_name") or None),
        contexto=julia_turn.contexto,
        lead_ref=str(julia_turn.contato["id"]),
        crm_lead_id=str(julia_turn.contato["lead_id"]) if julia_turn.contato.get("lead_id") else None,
        messages=tuple(mensagem_do_turno(m) for m in batch if m.get("provider_message_id")),
    )
    if not req.messages:
        logger.error("julia: batch for %s carries no provider_message_id -- dropped", ref_log(chat_id))
        close_run(deps.buffer, key, run)
        return

    try:
        result = await asyncio.wait_for(client.run_turn(req), timeout=deps.turn_timeout_s)
    except asyncio.TimeoutError:
        logger.error("julia: agents turn timed out (>%ss) conn=%s chat=%s", deps.turn_timeout_s, connection.id, ref_log(chat_id))
        _clear_attempts(deps, key)
        close_run(deps.buffer, key, run)
        return
    except AgentsClientError as exc:
        await _handle_turn_error(
            deps, exc, key=key, run=run, org_id=org_id, connection_id=connection.id, chat_id=chat_id,
            connection=connection, contato=julia_turn.contato, chat_store=chat_store, agents_client=client,
        )
        return
    _clear_attempts(deps, key)
    julia.limpar_erro_link(org_id, cfg=deps.cfg)
    if result.atendeu:
        await _redigir_identificacao_guardada(
            deps, connection=connection, chat_id=chat_id, chat_store=chat_store, agents_client=client,
            lead_ref=str(julia_turn.contato["id"]), batch=batch,
        )

    if result.status in STATUS_SEM_ATENDIMENTO:
        await _tratar_sem_atendimento(
            deps, connection=connection, chat_id=chat_id, result=result, state=state, chat_store=chat_store,
            julia_turn=julia_turn, agents_client=client, mensagens=[
                (texto_para_anexar({"text": m.texto, "metadata": {"midia": m.midia}}), m.provider_message_id, m.at) for m in req.messages],
        )
        close_run(deps.buffer, key, run)
        return

    await _deliver(
        deps, connection=connection, chat_id=chat_id, key=key, run=run, result=result, state=state, chat_store=chat_store,
        julia_turn=julia_turn, agents_client=client,
        lote_hash=julia_acoes_service.lote_hash_de(result.thread or result.conversation_id, [m.provider_message_id for m in req.messages]),
        fluxo=julia_envio_gate.Fluxo.RESPOSTA,
    )


async def _redigir_identificacao_guardada(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, chat_store: Any, agents_client: AgentsClient,
    lead_ref: str, batch: list[dict[str, Any]],
) -> None:
    """GUARDRAILS B8.4: when this batch carried a CPF / RG / CNH number AND agents now holds the lead's identification (its
    masked read is non-empty), mask the numbers in SW's stored copy of those messages. Never raises: a failure is logged by type
    and the stored text simply stays as typed (the retention window still applies).

    Agents masks `agents.messages` itself (its own store); this is SW's half, including the realtime stream."""
    from app.services.identidade_mascara import mascarar_identificadores

    ids = [str(m["provider_message_id"]) for m in batch
           if m.get("provider_message_id") and mascarar_identificadores(str(m.get("text") or "")) != str(m.get("text") or "")]
    if not ids:
        return
    try:
        registrada = await agents_client.identificacao_mascarada(lead_ref)
        if not registrada:
            return
        n = deps.message_store_factory(connection.org_id).redigir_identificacao(
            connection_id=connection.id, chat_id=chat_id, provider_message_ids=ids)
        logger.info("julia: identity numbers masked in %s stored message(s) conn=%s", n, connection.id)
        await _purgar_stream_identificacao(deps, connection=connection, chat_id=chat_id)
    except Exception as exc:
        logger.error("julia: identity redaction failed conn=%s (%s)", connection.id, type(exc).__name__)


async def _purgar_stream_identificacao(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str) -> None:
    """The inbox stream retains (and replays on reconnect) the `message.new` / `chat.upsert` published with the raw number
    before it was masked: remove, from the connection's scope, this chat's events that still carry an identity number.
    Delete, not rewrite (a stream entry cannot be edited; clients re-fetch the masked row). Bounded to the retained window,
    never raises (type only in the log)."""
    from app.services.identidade_mascara import contem_identificadores
    from app.services.whatsapp_realtime import whatsapp_scope

    try:
        n = await deps.bus.redact(
            whatsapp_scope(connection.id),
            lambda e: e.payload.get("chat_id") == chat_id and contem_identificadores(e.payload),
        )
        if n:
            logger.info("julia: identity numbers purged from %s realtime event(s) conn=%s", n, connection.id)
    except Exception as exc:
        logger.error("julia: realtime purge failed conn=%s (%s)", connection.id, type(exc).__name__)


async def _registrar_opt_in(client: AgentsClient, contato_id: Any) -> None:
    """The lead started the conversation: the messaging-policy opt-in agents records (`lead_iniciou`). Best-effort: a
    failure is logged and never stops the turn (agents re-derives consent from the thread anyway)."""
    try:
        await client.opt_in(str(contato_id), origem="lead_iniciou")
    except AgentsClientError as exc:
        logger.warning("julia: opt-in not recorded (%s) contato=%s", type(exc).__name__, contato_id)


async def _tratar_sem_atendimento(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, result: TurnResult, state: Optional[dict[str, Any]],
    chat_store: Any, julia_turn: Optional[JuliaTurn], agents_client: Optional[AgentsClient],
    mensagens: list[tuple[str, str, Optional[datetime]]],
) -> None:
    """agents did NOT serve this turn (a control decision, or it could not read its control): nothing is sent, no action
    is applied. What SW does with it:

      * records the event (`agente_nao_atendeu`, the status only) so the team can see why Julia was silent;
      * mirrors the participant state agents reported (display only);
      * appends the lead's messages to the thread when it exists (Q5) -- idempotent;
      * `lead_opt_out`: bumps `gen`, so every queued re-engagement job for the contato is stale (the lead asked to stop);
      * a lead agents refused (`novo_lead_recusado` / `agente_desligado` with NO thread): the contato SW created for this
        very batch is erased -- a lead Julia never served is not kept (Q5, LGPD data minimisation)."""
    contato = julia_turn.contato if julia_turn else None
    logger.info("julia: agents did not serve the turn (%s) conn=%s chat=%s -- nothing sent", result.status, connection.id, ref_log(chat_id))
    if contato is not None:
        julia_eventos_service.emitir(deps.scoped, connection.org_id, "agente_nao_atendeu", contato.get("id"),
                                     {"status": result.status})
    if result.status == "controle_indisponivel":
        julia.registrar_erro_link(connection.org_id, "controle_indisponivel", cfg=deps.cfg)
        logger.error("julia: agents could not read its control (status) org=%s -- failing closed", connection.org_id)
    thread_id = result.thread
    if thread_id:
        julia_thread_service.espelhar(
            chat_store, connection_id=connection.id, chat_id=chat_id, thread_id=thread_id, estado=result.participante_estado,
        )
        if result.status in julia_thread_service.STATUS_ANEXAR_LEAD:
            await julia_thread_service.encaminhar_lead(agents_client, thread_id=thread_id, mensagens=mensagens)
    elif result.status in ("novo_lead_recusado", "agente_desligado") and contato is not None:
        if julia_thread_service.thread_id_do_estado(state) is None and not contato.get("ultimo_outbound_at"):
            try:
                removidos = julia_contatos_service.apagar_do_chat(
                    deps.scoped, connection.org_id, connection.id, sorted(julia.chat_aliases(chat_id)))
                logger.info("julia: lead refused by agents (%s) -- %s SW contato(s) not kept", result.status, removidos)
            except Exception as exc:
                logger.error("julia: could not drop the contato of a refused lead conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
    if result.status in STATUS_LIMITE_PARA_HUMANO:
        await _contar_abuso(deps, connection=connection, chat_id=chat_id, status=result.status)
        await _encaminhar_limite(deps, connection=connection, chat_id=chat_id, status=result.status, contato=contato,
                                 chat_store=chat_store, agents_client=agents_client)
    if result.status == "lead_opt_out" and contato is not None:
        try:
            julia_contatos_service.bump_gen(deps.scoped, contato["id"], encerrado_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            logger.error("julia: gen bump on opt-out failed conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)


async def _contar_abuso(deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, status: str) -> None:
    """GUARDRAILS B5: agents' `limite_taxa` / `loop_detectado` are abuse signals. Each counts toward the org's AUTOMATIC TEMPORARY
    BLOCK (threshold, window and duration are the org's data); a number that reaches it is blocked, the admins are notified and
    nothing more reaches agents or an AI call from it until an admin lifts it or it expires. `capacidade` / `novo_lead_limitado`
    are about OUR capacity, not the lead's behaviour, so they never count. Never raises."""
    if status not in protecao.GATILHOS_AUTO:
        return
    try:
        chave = protecao.chave_numero(chat_id)
        if not chave:
            return
        config = protecao.obter_config(deps.scoped, connection.org_id)
        protecao.registrar_infracao(
            deps.buffer.redis, deps.scoped, deps.core_client, config, org_id=connection.org_id, connection_id=connection.id,
            chave=chave, gatilho=status,
        )
    except Exception as exc:
        logger.error("julia: abuse counting failed conn=%s (%s)", connection.id, type(exc).__name__)


#: Operator-facing reason per limit status (the closed `motivo_codigo` is the status itself). UI copy for staff, never sent to
#: the lead.
MOTIVOS_LIMITE: dict[str, str] = {
    "limite_taxa": "O lead enviou mensagens rápido demais e o agente não respondeu (limite por lead).",
    "novo_lead_limitado": "O limite de novos leads do agente foi atingido: nada foi guardado no agente. As mensagens do lead estão aqui no SW, responda a ele.",
    "loop_detectado": "O agente detectou um loop de mensagens (flood/eco), pausou o atendimento e passou a conversa para uma pessoa.",
    "capacidade": "O agente estava sem capacidade para responder (limite de uso da organização) e a mensagem do lead não foi atendida: responda a ele.",
}
LIMITE_DEDUPE_S = 3600  # one operator notice per lead, per status, per hour: a flood must not flood the operators either


async def _encaminhar_limite(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, status: str, contato: Optional[dict[str, Any]],
    chat_store: Any, agents_client: Optional[AgentsClient],
) -> None:
    """A LIMIT (rate / new-lead cap / loop) stopped a real person: never silence. The org's operators are notified through
    the same in-app path a `handoff` uses (target = the chat's attendant, else the configured/owner target), a
    `limite_para_humano` timeline event is recorded, deduped per lead+status per hour. The lead's messages stay in SW (the
    webhook stored them; for `novo_lead_limitado` agents kept nothing, so SW's copy IS the only one -- the contato is
    NOT dropped). A failure here is logged, never raised. `status` is an agents limit status or `capacidade` (agents answered 429
    until SW's re-queues ran out)."""
    if status == "loop_detectado" and contato is not None:  # agents paused + handed off: every queued job is stale
        try:
            julia_contatos_service.bump_gen(deps.scoped, contato["id"])
        except Exception as exc:
            logger.error("julia: gen bump on loop_detectado failed conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
    try:
        novo = deps.buffer.redis.set(f"julia:limite:{connection.id}:{chat_id}:{status}", "1", nx=True, ex=LIMITE_DEDUPE_S)
    except Exception as exc:
        logger.error("julia: limit dedupe unavailable conn=%s chat=%s -- notifying (better twice than never) (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
        novo = True
    if not novo:
        logger.info("julia: %s for chat=%s already routed to the operators within the hour", status, ref_log(chat_id))
        return
    responsavel: Optional[str] = None
    try:
        if contato is not None:
            atribuido = julia_equipes_service.atribuir_responsavel(deps.scoped, deps.core_client, connection.org_id, contato, "handoff")
            responsavel = atribuido["user_id"] if atribuido else None
    except Exception as exc:
        logger.error("julia: attendant distribution failed for %s conn=%s chat=%s (%s)", status, connection.id, ref_log(chat_id), type(exc).__name__)
    notificado = False
    try:
        summary = chat_store.get_chat(connection_id=connection.id, chat_id=chat_id)
        nome_agente = await julia.nome_do_agente(agents_client) if agents_client is not None else None
        julia.notificar_handoff(
            deps.core_client, connection=connection, chat_id=chat_id, titulo_chat=summary.title if summary else None,
            motivo=MOTIVOS_LIMITE[status], responsavel_user_id=responsavel, registro=None, agente_nome=nome_agente,
        )
        notificado = True
    except Exception as exc:
        logger.error("julia: operator notice for %s failed conn=%s chat=%s (%s)", status, connection.id, ref_log(chat_id), type(exc).__name__)
    julia_eventos_service.emitir(
        deps.scoped, connection.org_id, "limite_para_humano", (contato or {}).get("id"),
        {"status": status, "motivo_codigo": status, "notificado": notificado},
    )


def _alertar_contrato_invalido(
    deps: LeadDeps, exc: AgentsClientError, *, org_id: UUID, connection_id: UUID, chat_id: str,
) -> None:
    """A 422 / replay-409 from agents is an integration bug on OUR side (we sent a shape its schema rejects), and
    the lead gets no reply: never a quiet log line. ERROR + an owner-visible `julia_eventos`/notification
    (`agents_contrato_invalido`, deduped per org/code/day). Ids only, no PII."""
    logger.error("julia: agents rejected the turn as a client bug (%s: %s) conn=%s chat=%s -- the lead got NO reply", type(exc).__name__, exc.code, connection_id, ref_log(chat_id))
    julia_eventos_service.emitir(
        deps.scoped, org_id, "agents_contrato_invalido", None,
        {"codigo": str(exc.code or type(exc).__name__), "dia": julia_notificacoes_service.dia_sp(),
         "ids": {"connection_id": str(connection_id)}},
    )


async def _handle_turn_error(
    deps: LeadDeps, exc: AgentsClientError, *, key: str, run: list[dict[str, Any]],
    org_id: UUID, connection_id: UUID, chat_id: str,
    connection: Optional[WhatsAppConnectionRecord] = None, contato: Optional[dict[str, Any]] = None,
    chat_store: Any = None, agents_client: Optional[AgentsClient] = None,
) -> None:
    """The section 3.1 error table, one branch per row. No branch sends the lead anything (fail closed). The capacity branch,
    once its re-queues are spent, is NEVER a drop: the conversation goes to a human (`motivo_codigo` `capacidade`)."""
    if isinstance(exc, ControleIndisponivel):
        # agents could not read its OWN control: it will not guess and neither does SW. One short retry (the read is
        # transient), then the batch is dropped -- a late reply to a lead is worse than none.
        julia.registrar_erro_link(org_id, "controle_indisponivel", cfg=deps.cfg)
        if _attempts(deps, key) < MAX_REQUEUE_IN_PROGRESS:
            _bump_attempts(deps, key)
            _requeue(deps, key, REQUEUE_IN_PROGRESS_S)
            logger.warning("julia: agents control unavailable -- batch re-queued once in %ss (chat=%s)", REQUEUE_IN_PROGRESS_S, ref_log(chat_id))
            return
        logger.error("julia: agents control unavailable after the re-queue -- batch dropped, nothing sent (chat=%s)", ref_log(chat_id))
    elif isinstance(exc, TurnInProgress):
        if _attempts(deps, key) < MAX_REQUEUE_IN_PROGRESS:
            _bump_attempts(deps, key)
            _requeue(deps, key, REQUEUE_IN_PROGRESS_S)
            logger.info("julia: turn_in_progress -- batch re-queued once in %ss (chat=%s)", REQUEUE_IN_PROGRESS_S, ref_log(chat_id))
            return
        logger.error("julia: turn_in_progress persisted after the re-queue -- batch dropped (chat=%s)", ref_log(chat_id))
    elif isinstance(exc, CapacityExceeded):
        if _attempts(deps, key) < MAX_REQUEUE_CAPACITY:
            _bump_attempts(deps, key)
            _requeue(deps, key, exc.retry_after)
            logger.warning("julia: capacidade -- batch re-queued in %ss (chat=%s)", exc.retry_after, ref_log(chat_id))
            return
        logger.error("julia: capacidade persisted after %s re-queues -- routed to a human (chat=%s)", MAX_REQUEUE_CAPACITY, ref_log(chat_id))
        if connection is not None:
            await _encaminhar_limite(
                deps, connection=connection, chat_id=chat_id, status="capacidade", contato=contato, chat_store=chat_store,
                agents_client=agents_client,
            )
    elif isinstance(exc, (AgentsTokenInvalid, AgentsNotConfigured)):
        julia.registrar_erro_link(org_id, "token_invalido" if isinstance(exc, AgentsTokenInvalid) else "nao_configurado", cfg=deps.cfg)
        logger.error("julia: agents token rejected (code=%s) org=%s -- no reply", exc.code, org_id)
    elif isinstance(exc, AgentNotFound):
        julia.registrar_erro_link(org_id, "agent_not_found", cfg=deps.cfg)
        logger.error("julia: agent not found org=%s -- no reply", org_id)
    elif isinstance(exc, AgentUnavailable):
        julia.registrar_erro_link(org_id, "agent_unavailable", cfg=deps.cfg)
        logger.error("julia: agent unavailable (%s) org=%s -- no reply", exc.code, org_id)
    elif isinstance(exc, LlmNotConfigured):
        julia.registrar_erro_link(org_id, "llm_not_configured", cfg=deps.cfg)
        logger.error("julia: LLM key missing in agents for org=%s -- no reply", org_id)
    elif isinstance(exc, (AgentsBadRequest, IdempotencyConflict)):
        _alertar_contrato_invalido(deps, exc, org_id=org_id, connection_id=connection_id, chat_id=chat_id)
    elif isinstance(exc, (AgentsUpstreamError, AgentsTimeout)):
        logger.error("julia: agents upstream failure (%s) conn=%s chat=%s -- no reply", type(exc).__name__, connection_id, ref_log(chat_id))
    else:  # an AgentsClientError subclass we do not know: never reply, never loop
        logger.error("julia: unhandled agents error %s conn=%s chat=%s", type(exc).__name__, connection_id, ref_log(chat_id))
    _clear_attempts(deps, key)
    close_run(deps.buffer, key, run)


async def _resolve_lid_phone(deps: LeadDeps, connection: WhatsAppConnectionRecord, lid: str) -> Optional[str]:
    try:
        waha = deps.waha_factory(base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name)
        pn = await waha.get_lid_phone(lid)
    except Exception:
        logger.warning("julia: LID->phone lookup failed for %s", protecao.ref(lid))
        return None
    d = julia.phone_digits(pn) if pn else None
    return f"+{d}" if d else None


async def _deliver(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, key: str,
    run: list[dict[str, Any]], result: TurnResult, state: Optional[dict[str, Any]], chat_store: Any,
    julia_turn: Optional[JuliaTurn] = None, agents_client: Optional[AgentsClient] = None, lote_hash: Optional[str] = None,
    fluxo: julia_envio_gate.Fluxo, regua_id: Optional[str] = None,
) -> bool:
    """Send the reply of a SERVED turn; True when at least one bubble went out. Nothing leaves before
    `julia_envio_gate.exigir` passes for `fluxo` (Julia routed on the line + the org's opt-in for that flow)."""
    pos = dict(julia_turn=julia_turn, connection=connection, chat_id=chat_id, result=result, lote_hash=lote_hash,
               agents_client=agents_client)
    # agents answered: its participant state lands on the chat row (display mirror, written only from agents' answers).
    # The thread id doubles as the "privacy disclosure already sent" marker, so it is mirrored only AFTER a bubble went out.
    julia_thread_service.espelhar(
        chat_store, connection_id=connection.id, chat_id=chat_id, thread_id=None, estado=result.participante_estado,
    )
    fresh = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)

    handoff = result.handoff
    primeira = not (julia_thread_service.thread_id_do_estado(state) or julia_thread_service.thread_id_do_estado(fresh))
    partes = list(result.partes)
    if julia_turn is not None and julia_turn.avisos:
        # Wave 1: the deterministic recesso notice goes first (after the privacy disclosure, inserted below).
        partes[0:0] = julia_turn.avisos
    if not partes and handoff is None:
        await _pos_turno(deps, enviou=False, **pos)  # silence can still carry actions
        close_run(deps.buffer, key, run)  # status `silencio`: stay silent, nothing to disclose
        return False

    # (only when agents' own answer left the agent ACTIVE: a hand-off / conclusion pauses it in this very turn, and that
    # turn's last words must still go out)
    if partes and handoff is None and result.participante_estado in (None, "ativo") and await _pausado_durante_o_turno(
        agents_client, thread_id=result.thread, agent_key=connection.agente_leads_key or julia.DEFAULT_AGENT_KEY,
        connection_id=connection.id,
    ):
        # L3: a human stepped in WHILE the turn was running (agents' pause landed after it decided): the reply is dropped.
        logger.info("julia: agent paused in the conversation during the turn -- reply discarded conn=%s", connection.id)
        await _pos_turno(deps, enviou=False, **pos)  # what the model recorded is still the lead's data
        close_run(deps.buffer, key, run)
        return False

    try:
        liberacao = julia_envio_gate.exigir(
            deps.scoped, connection.org_id, connection.id, fluxo,
            contato_id=julia_turn.contato.get("id") if julia_turn is not None else None, regua_id=regua_id,
        )
    except julia_envio_gate.EnvioBloqueado:  # already logged + `envio_bloqueado` event by the gate
        await _pos_turno(deps, enviou=False, **pos)
        close_run(deps.buffer, key, run)
        return False
    waha = deps.waha_factory(base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name)
    sender = LeadSender(connection=connection, waha=waha, deps=deps, liberacao=liberacao)
    delay = float(deps.cfg.whatsapp_paragraph_delay_seconds)

    if primeira:
        # 11.3: the disclosure is deterministic and goes BEFORE Julia's first reply. Its text is the org's row; the
        # agent's name comes from agents' own status (never a name in SW code).
        try:
            nome_agente = await julia.nome_do_agente(agents_client) if agents_client is not None else None
            disclosure = julia.mensagem_inicial_pronta(
                julia_aviso_service.obter_ou_criar(deps.scoped, deps.core_client, connection.org_id), nome_agente,
            )
        except Exception as exc:
            logger.error("julia: cannot build the privacy disclosure for org=%s -- reply NOT sent (%s)", connection.org_id, type(exc).__name__)
            close_run(deps.buffer, key, run)
            return False
        partes.insert(0, disclosure)

    julia.marcar_envio_em_curso(deps.redis, connection.id, chat_id)
    enviadas = 0
    try:
        for idx, parte in enumerate(partes):
            if idx:
                await deps.sleep(delay)
            await send_paragraphs(intake=sender, sender=chat_id, text=parte, delay_seconds=0, split=False)
            enviadas += 1
    except Exception as exc:
        logger.error("julia: WAHA send failed after %s/%s bubbles conn=%s chat=%s (%s)", enviadas, len(partes), connection.id, ref_log(chat_id), type(exc).__name__)
    finally:
        julia.encerrar_envio(deps.redis, connection.id, chat_id)

    if enviadas and result.thread:
        julia_thread_service.espelhar(
            chat_store, connection_id=connection.id, chat_id=chat_id, thread_id=result.thread, estado=None,
        )
    if enviadas and fluxo is julia_envio_gate.Fluxo.RESPOSTA and julia_turn is not None:
        _registrar_primeira_resposta(deps, connection.org_id, julia_turn.contato)

    if handoff is not None:
        await _apply_handoff(
            deps, connection=connection, chat_id=chat_id, chat_store=chat_store, handoff=handoff, result=result,
            agents_client=agents_client,
        )
    await _pos_turno(deps, enviou=bool(enviadas), **pos)
    close_run(deps.buffer, key, run)
    return bool(enviadas)


async def _pausado_durante_o_turno(
    client: Optional[AgentsClient], *, thread_id: Optional[str], agent_key: str, connection_id: Any,
) -> bool:
    """L3 re-check, LIVE (never the mirror): has a human paused the agent in this conversation since the turn decided?
    One `GET thread` right before the first bubble. The turn itself already passed agents' controls, so an unreadable
    thread here does not block the reply (logged) -- agents' decision stands."""
    if client is None or not thread_id:
        return False
    try:
        info = await client.obter_thread(thread_id)
    except AgentsClientError as exc:
        logger.warning("julia: pre-send pause re-check unavailable (%s) conn=%s -- sending on agents' decision", type(exc).__name__, connection_id)
        return False
    return info.pausado(agent_key)


def _registrar_primeira_resposta(deps: LeadDeps, org_id: Any, contato: dict[str, Any]) -> None:
    """maya-blocks / julia-v2 G1: Julia's first reply of the open episode stamps `primeira_resposta_agente_at`
    (once). Only a reply to the lead's own message counts (a re-engagement is not a response). Bookkeeping: never
    undoes the reply -- a failure raises a visible `supervisao_falha` alert (G4), not just a log line."""
    try:
        julia_contatos_service.registrar_primeira_resposta(deps.scoped, org_id, contato["id"], por="agente")
    except Exception as exc:
        logger.error("julia: primeira_resposta_agente_at not stamped org=%s contato=%s (the reply IS out) (%s)", org_id, contato.get("id"), type(exc).__name__)
        supervisao_alertas.alertar(deps.scoped, org_id, "primeira_resposta_agente", {"contato_id": contato.get("id")})


async def run_reengajamento_turn(
    deps: LeadDeps, connection: WhatsAppConnectionRecord, chat_id: str, contato: dict[str, Any],
    estado_extra: dict[str, Any], marker_id: str,
) -> bool:
    """A re-engagement turn: `gatilho="reengajamento"` with the flavour as DATA in `contexto.estado` (`reengajamento` = the
    tier, and for a regua text `reescrever` + `texto_base` + `tentativa`) -- agents renders its own instruction from its DB
    texts. There is NO fake lead message (the old `[sistema] ...` marker is gone). Returns True when a message went out; an
    agents failure, or a status that means "not served" (`reengajamento_ignorado`: the agent is off / paused / not the
    active participant), is logged and reads as False (the job still completes: a re-engagement is best-effort, a retry
    storm against a down agents is worse). Does NOT bump `gen` (nothing came in).

    `estado_extra["reengajamento"]` names the flow the outbound gate checks (`minutos` | `horas` | `regua`); a regua turn
    also carries `regua_id`, which goes to the gate and NOT to agents. `marker_id` (unique per job) keys the action ledger."""
    estado_extra = dict(estado_extra)
    regua_id = estado_extra.pop("regua_id", None)
    tier = str(estado_extra.get("reengajamento"))
    fluxo = julia_envio_gate.FLUXO_DO_TIER.get(tier)
    if fluxo is None:
        raise ValueError(f"re-engagement turn without a known tier: {estado_extra.get('reengajamento')!r}")
    if not str(estado_extra.get("texto_base") or "").strip():
        estado_extra.pop("texto_base", None)  # agents' schema: a base text is >= 1 char or absent
        estado_extra.pop("reescrever", None)
    else:
        estado_extra["texto_base"] = str(estado_extra["texto_base"]).strip()[:2000]  # agents' cap
    org_id = connection.org_id
    client = deps.agents_client_factory(org_id)
    if client is None:
        julia.registrar_erro_link(org_id, "nao_configurado", cfg=deps.cfg)
        logger.error("julia: agents not configured for org %s -- re-engagement not sent", org_id)
        return False
    chat_store = deps.chat_store_factory(org_id)
    state = chat_store.get_agente_state(connection_id=connection.id, chat_id=chat_id)
    interacao = julia_contatos_service.abrir_interacao(deps.scoped, org_id, contato)
    contexto = julia_contexto_service.montar(deps.scoped, org_id, contato, interacao=interacao, estado_extra=estado_extra)
    phone = contato.get("telefone_e164") or _phone_e164(chat_id)
    req = TurnRequest(
        agent_key=connection.agente_leads_key or julia.DEFAULT_AGENT_KEY,
        connection_id=str(connection.id), chat_id=chat_id, phone_e164=phone, display_name=contato.get("nome"),
        contexto=contexto, lead_ref=str(contato["id"]),
        crm_lead_id=str(contato["lead_id"]) if contato.get("lead_id") else None,
        gatilho=GATILHO_REENGAJAMENTO,
        messages=(),
    )
    try:
        result = await asyncio.wait_for(client.run_turn(req), timeout=deps.turn_timeout_s)
    except asyncio.TimeoutError:
        logger.error("julia: re-engagement turn timed out (>%ss) conn=%s chat=%s", deps.turn_timeout_s, connection.id, ref_log(chat_id))
        return False
    except AgentsClientError as exc:
        if isinstance(exc, (AgentsBadRequest, IdempotencyConflict)):
            _alertar_contrato_invalido(deps, exc, org_id=org_id, connection_id=connection.id, chat_id=chat_id)
        else:
            logger.error("julia: re-engagement turn failed (%s) conn=%s chat=%s", type(exc).__name__, connection.id, ref_log(chat_id))
        return False
    julia_turn = JuliaTurn(contato=contato, contexto=contexto)
    if result.status in STATUS_SEM_ATENDIMENTO:
        await _tratar_sem_atendimento(
            deps, connection=connection, chat_id=chat_id, result=result, state=state, chat_store=chat_store,
            julia_turn=julia_turn, agents_client=client, mensagens=[],
        )
        return False
    return await _deliver(
        deps, connection=connection, chat_id=chat_id, key=f"lead:{connection.id}:{chat_id}", run=[], result=result,
        state=state, chat_store=chat_store, julia_turn=julia_turn,
        agents_client=client, lote_hash=julia_acoes_service.lote_hash_de(result.conversation_id, [marker_id]),
        fluxo=fluxo, regua_id=str(regua_id) if regua_id else None,
    )


async def _apply_handoff(
    deps: LeadDeps, *, connection: WhatsAppConnectionRecord, chat_id: str, chat_store: Any, handoff: Any, result: TurnResult,
    agents_client: Optional[AgentsClient],
) -> None:
    """The agent handed the conversation to a human. agents already set the participant `pausado`/`transferido` and
    recorded the hand-off note SERVER-SIDE; SW:

      * mirrors that state onto the chat (`chat.upsert`, display only -- it is NOT a local pause, nothing reads it as one);
      * bumps `gen` (contract 0.2: a handoff invalidates every job queued for this contato);
      * picks the attendant (wave 11 teams) and records the closed `motivo_codigo` event;
      * renders the agents HAND-OFF NOTE (profile + atendimento summary + masked identity) to the human target -- the org
        owner by default (owner decision, julia-v2 0.4) -- through the in-app notification path.

    A failure of any leg is logged and never undoes the others (the conversation IS handed over in agents)."""
    estado = result.participante_estado or "pausado"
    julia_thread_service.espelhar(
        chat_store, connection_id=connection.id, chat_id=chat_id, thread_id=result.thread, estado=estado)
    try:  # contract 0.2: a handoff invalidates every job queued for this contato
        julia_contatos_service.bump_gen_do_chat(deps.scoped, connection.org_id, connection.id, chat_id)
    except Exception as exc:
        logger.error("julia: gen bump on handoff failed conn=%s chat=%s (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
    await publish_pause(deps, connection=connection, chat_id=chat_id, pausado=estado == "pausado")
    responsavel: Optional[str] = None
    contato: Optional[dict[str, Any]] = None
    try:  # wave 11: pick the attendant BEFORE notifying so the notification reaches them
        contato = julia_contatos_service.buscar_contato(deps.scoped, connection.org_id, connection.id, chat_id)
        if contato is not None:
            atribuido = julia_equipes_service.atribuir_responsavel(deps.scoped, deps.core_client, connection.org_id, contato, "handoff")
            responsavel = atribuido["user_id"] if atribuido else None
    except Exception as exc:
        logger.error("julia: attendant distribution failed conn=%s chat=%s (the handoff proceeds unassigned) (%s)", connection.id, ref_log(chat_id), type(exc).__name__)
    # maya-blocks: the reason as a CLOSED code. agents now sends a typed `motivo_codigo` (labels live in its DB); an older
    # build sends free text, mapped by the legacy matcher. `handoff` is outside the notification fan-out, so this cannot
    # double-notify; `emitir` never raises.
    codigo = handoff.motivo_codigo or julia.motivo_codigo_do_handoff(handoff.motivo)
    julia_eventos_service.emitir(
        deps.scoped, connection.org_id, "handoff", (contato or {}).get("id"), {"motivo_codigo": codigo},
    )
    registro: Optional[HandoffRecord] = None
    nome_agente: Optional[str] = None
    if agents_client is not None and result.thread:
        try:
            registros = await agents_client.listar_handoffs(result.thread)
            registro = registros[-1] if registros else None
        except AgentsClientError as exc:
            logger.error("julia: hand-off note not readable (%s) thread=%s -- notifying with the reason only", type(exc).__name__, result.thread)
        nome_agente = await julia.nome_do_agente(agents_client)
    try:
        summary = chat_store.get_chat(connection_id=connection.id, chat_id=chat_id)
        julia.notificar_handoff(
            deps.core_client, connection=connection, chat_id=chat_id,
            titulo_chat=summary.title if summary else None, motivo=handoff.motivo, responsavel_user_id=responsavel,
            registro=registro, agente_nome=nome_agente,
        )
        julia_eventos_service.emitir(deps.scoped, connection.org_id, "handoff_recebido", (contato or {}).get("id"),
                                     {"handoff_id": registro.id if registro else None, "motivo_codigo": codigo})
    except Exception as exc:
        logger.error("julia: handoff notification failed conn=%s chat=%s (the conversation IS handed over) (%s)", connection.id, ref_log(chat_id), type(exc).__name__)


__all__ = [
    "LeadDeps", "LeadSender", "close_run", "process_lead_batch", "publish_pause", "trim_batch",
    "unprocessed_run",
]
